#!/usr/bin/env python3
"""
Alexa skill for California Speaks (<https://speakca.net/>)

Copyright (C) 2018 Kunal Mehta <kunal.mehta@sjsu.edu>

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
import boto3
import collections
import logging
import os
from copy import copy
import re
import requests
from typing import Optional, Union

import feedparser
from flask import Flask
from flask_ask import Ask, question, statement, audio

app = Flask(__name__)
ask = Ask(app, '/')
logging.getLogger('flask_ask').setLevel(logging.INFO)
STATIC = os.path.join(os.path.dirname(__file__), 'static')
s3 = boto3.resource('s3')

bucket = s3.Bucket('alexa-speakca')


def s3_url(obj) -> str:
    """
    Given an S3 object, get the public URL for it
    :param obj: S3 object
    :return: public URL
    """
    return 'https://s3.amazonaws.com/%s/%s' % (obj.bucket_name, obj.key)


files = sorted(
    bucket.objects.all(),
    reverse=True,
    key=lambda obj: obj.last_modified
)

# TODO will this automatically be reloaded whenever a
# new request is made?
playlist = [s3_url(obj) for obj in files]

known_stuff = {}
for obj in bucket.objects.all():
    full_obj = s3.Object(obj.bucket_name, obj.key)
    if 'url' in full_obj.metadata:
        known_stuff[full_obj.metadata.get('url')] = obj


class QueueManager(object):
    """Manages queue data in a seperate context from current_stream.

    The flask-ask Local current_stream refers only to the current data from Alexa requests and Skill Responses.
    Alexa Skills Kit does not provide enqueued or stream-histroy data and does not provide a session attribute
    when delivering AudioPlayer Requests.

    This class is used to maintain accurate control of multiple streams,
    so that the user may send Intents to move throughout a queue.
    """

    def __init__(self, urls):
        self._urls = urls
        self._queued = collections.deque(urls)
        self._history = collections.deque()
        self._current = None

    @property
    def status(self):
        status = {
            'position': self.current_position,
            'current': self.current,
            'next': self.up_next,
            'previous': self.previous,
            'history': list(self.history)
        }
        return status

    @property
    def up_next(self):
        """Returns the url at the front of the queue"""
        qcopy = copy(self._queued)
        try:
            return qcopy.popleft()
        except IndexError:
            return None

    @property
    def current(self):
        return self._current

    @current.setter
    def current(self, url):
        self._save_to_history()
        self._current = url

    @property
    def history(self):
        return self._history

    @property
    def previous(self):
        history = copy(self.history)
        try:
            return history.pop()
        except IndexError:
            return None

    def add(self, url):
        self._urls.append(url)
        self._queued.append(url)

    def extend(self, urls):
        self._urls.extend(urls)
        self._queued.extend(urls)

    def _save_to_history(self):
        if self._current:
            self._history.append(self._current)

    def end_current(self):
        self._save_to_history()
        self._current = None

    def step(self):
        self.end_current()
        self._current = self._queued.popleft()
        return self._current

    def step_back(self):
        self._queued.appendleft(self._current)
        self._current = self._history.pop()
        return self._current

    def reset(self):
        self._queued = collections.deque(self._urls)
        self._history = []

    def start(self):
        self.__init__(self._urls)
        return self.step()

    @property
    def current_position(self):
        return len(self._history) + 1


queue = QueueManager(playlist)


@ask.intent('QuestionIntent')
def grab_question() -> statement:
    """
    QuestionIntent handler

    Fetches the question from the CA Speaks website, and
    reads it to the user

    :return: Statement
    """
    # TODO: Add caching
    r = requests.get('https://speakca.net/')
    if not r.ok:
        return statement('Sorry, I\'m having a little bit of trouble'
                         ' right now, please try again later')
    question = re.findall(r'<span style="font-size: x-large;">(.*?)</span>', r.text)
    if not question:
        return statement('Sorry, I\'m having a little bit of trouble'
                         ' right now, please try again later')

    # XXX: What if someone adds markup to the HTML?
    # We break up the phone number so that Alexa will
    # pronounce it properly.
    say = 'Here\'s this week\'s question: {} ' \
          'To respond, call 1 8 3 3 SPEAK-CA.'.format(question[0])
    return statement(say)


@ask.launch
def launch() -> question:
    """
    Launch handler

    Says intro text

    :return: Question
    """
    card_title = 'California Speaks'
    # FIXME: Better help text here?
    # parallelism
    text = 'Ask me to play this week\'s episode, what this week\'s question is or search for something.'
    return question(text).simple_card(card_title, text)


@ask.intent('AMAZON.StopIntent')
def stop() -> statement:
    """
    AMAZON.StopIntent handler (see `Amazon documentation <https://developer.amazon.com/docs/custom-skills/standard-built-in-intents.html>`_)

    Says goodbye message

    :return: Statement
    """
    return statement('Thanks for using the California Speaks skill')


@ask.intent('AMAZON.CancelIntent')
def cancel() -> statement:
    """
    AMAZON.CancelIntent handler (see `Amazon documentation <https://developer.amazon.com/docs/custom-skills/standard-built-in-intents.html>`_)

    Says goodbye message

    :return: Statement
    """
    return statement('Thanks for using the California Speaks skill')


@ask.intent('AMAZON.FallbackIntent')
def fallback():
    """
    AMAZON.FallbackIntent handler (see `Amazon documentation <https://developer.amazon.com/docs/custom-skills/standard-built-in-intents.html>`_)

    :return: Question
    """
    card_title = 'California Speaks'
    text = """Sorry, I didn't understand that. You can ask the skill to play this week's episode,
    to read out this week's question. You can also search through past episodes for specific topics.
    For example, try asking Alexa to search for water.
    """
    return question(text).simple_card(card_title, text)


@ask.intent('AMAZON.HelpIntent')
def help_() -> question:
    """
    AMAZON.HelpIntent handler (see `Amazon documentation <https://developer.amazon.com/docs/custom-skills/standard-built-in-intents.html>`_)

    :return: Question
    """
    card_title = 'California Speaks'
    # FIXME: Better help text here?
    # parallelism
    text = """California Speaks is an opportunity for Californians to make their voices heard
by responding to a new question each week. You can ask the skill to play this week's episode,
to read out this week's question. You can also search through past episodes for specific topics.
For example, try asking Alexa to search for water.
"""
    return question(text).simple_card(card_title, text)


@ask.intent('SearchIntent')
def search(term: str) -> Union[question, statement, audio]:
    """
    SearchIntent handler

    Allows users to search for episodes that match a specific term. Uses
    WordPress's search over RSS to get results.

    :param term: Search query
    """
    r = requests.get('https://speakca.net/', params={'s': term, 'feed': 'rss2'})
    if not r.ok:
        return statement('Sorry, we\'re experiencing technical difficulties. Please try again later.')
    parsed = feedparser.parse(r.text)
    for entry in parsed['entries']:
        if entry['link'] in known_stuff:
            # play it
            return audio().play(s3_url(known_stuff[entry['link']]))
    text = 'Sorry, unable to find anything related to "%s". Try searching again?' % term
    return question(text).simple_card('California Speaks', text)


@ask.intent('DemoIntent')
def start_playlist() -> audio:
    """
    DemoIntent handler (TODO: this should be renamed to something more sensible
    like AnswersIntent).

    Starts a playlist of previous episodes.

    :return: Audio
    """
    speech = 'Enjoy this episode'
    stream_url = queue.start()
    return audio(speech).play(stream_url)


# QueueManager object is not stepped forward here.
# This allows for Next Intents and on_playback_finished requests to trigger the step
@ask.on_playback_nearly_finished()
def nearly_finished() -> Optional[audio]:
    if queue.up_next:
        next_stream = queue.up_next
        return audio().enqueue(next_stream)

    return None


@ask.on_playback_finished()
def play_back_finished() -> Optional[statement]:
    if queue.up_next:
        queue.step()
        return None
    else:
        return statement('No more episodes')


@ask.on_playback_started()
def started(offset, token, url):
    pass


@ask.on_playback_stopped()
def stopped(offset, token):
    pass


@ask.intent('AMAZON.PauseIntent')
def pause() -> audio:
    """
    AMAZON.PauseIntent handler (see `Amazon documentation <https://developer.amazon.com/docs/custom-skills/standard-built-in-intents.html>`_)

    :return: Question
    """
    msg = 'Paused'
    return audio(msg).stop().simple_card(msg)


@ask.intent('AMAZON.ResumeIntent')
def resume() -> audio:
    """
    AMAZON.ResumeIntent handler (see `Amazon documentation <https://developer.amazon.com/docs/custom-skills/standard-built-in-intents.html>`_)

    :return: Question
    """
    msg = 'Resuming'
    return audio(msg).resume().simple_card(msg)


@ask.session_ended
def session_ended() -> tuple:
    return "{}", 200


def lambda_handler(event, _context):
    """
    Main entry point for AWS Lambda. Proxies to Flask-Ask's
    Lambda handler
    """
    return ask.run_aws_lambda(event)
