speakca is a custom Alexa skill for `California Speaks <https://speakca.net/>`_.

California Speaks is a radio program that invites listeners to hear a question each week,
call in their response, and then listen to selected responses the next week.

There are three main features to the skill: hearing the question, listening to previous
answers, and searching through previous responses.

User experience
===============

Question
--------
We use regexes to get the question out of the HTML of the California Speaks website. While
this might appear hacky, it has been rather reliable so far, and should be reasonable to
maintain.

A future optimization might be to add caching here, since the question is only going to
change once a week.

Answers
-------
The ``fetch.py`` script downloads episodes out of soundcloud and into an S3 bucket. We use the
AudioPlayer interface to turn the S3 files into a playlist for Alexa to go through.

Search
------
We depend upon WordPress's search functionality to search through the recorded transcripts.
Then we are able to match each WordPress post back to the audio file that we put into S3.

Backend
=======
The custom skill is powered by the fantastic Flask-Ask library, and is designed to run as
an AWS Lamba function. The ``fetch.py`` script currently requires ffmpeg to be installed,
so it's not easily run in AWS Lambda yet. You'll also need to set it to run on a cron.

The ``bundle`` shell script will create a zip file that can be uploaded to the AWS Lambda
web interface with all dependencies included for deployment. It currently is around 7MB.
It should always stay under 10MB.

License
=======
(C) 2018 Kunal Mehta <kunal.mehta@sjsu.edu> under the terms of the AGPL, v3 or any later
version. See COPYING for more details.
