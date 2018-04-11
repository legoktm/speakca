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

from flask import Flask
from flask_ask import Ask, question, statement, audio

app = Flask(__name__)
ask = Ask(app, '/')
logging.getLogger('flask_ask').setLevel(logging.INFO)
STATIC = os.path.join(os.path.dirname(__file__), 'static')
s3 = boto3.resource('s3')

bucket = s3.Bucket('alexa-speakca')


def s3_url(obj):
    # TODO this should really be something that boto provides
    return 'https://s3.amazonaws.com/%s/%s' % (obj.bucket_name, obj.key)


files = sorted(
    bucket.objects.all(),
    reverse=True,
    key=lambda obj: obj.last_modified
)

# TODO will this automatically be reloaded whenever a
# new request is made?
playlist = [s3_url(obj) for obj in files]


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
def grab_question():
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
def launch():
    card_title = 'California Speaks'
    text = 'Ask me to play this week\'s episode or what this week\'s question is.'
    prompt = 'You can ask me to play this week\'s episode or what this week\'s question is.'
    return question(text).reprompt(prompt).simple_card(card_title, text)


@ask.intent('DemoIntent')
def start_playlist():
    speech = 'Enjoy this episode'
    stream_url = queue.start()
    return audio(speech).play(stream_url)


# QueueManager object is not stepped forward here.
# This allows for Next Intents and on_playback_finished requests to trigger the step
@ask.on_playback_nearly_finished()
def nearly_finished():
    if queue.up_next:
        next_stream = queue.up_next
        return audio().enqueue(next_stream)


@ask.on_playback_finished()
def play_back_finished():
    if queue.up_next:
        queue.step()
    else:
        return statement('No more episodes')


@ask.on_playback_started()
def started(offset, token, url):
    pass


@ask.on_playback_stopped()
def stopped(offset, token):
    pass


@ask.intent('AMAZON.PauseIntent')
def pause():
    msg = 'Paused'
    return audio(msg).stop().simple_card(msg)


@ask.intent('AMAZON.ResumeIntent')
def resume():
    msg = 'Resuming'
    return audio(msg).resume().simple_card(msg)


@ask.session_ended
def session_ended():
    return "{}", 200


def lambda_handler(event, _context):
    return ask.run_aws_lambda(event)
