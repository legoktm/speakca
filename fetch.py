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


import feedparser
import os
import re
import requests
import soundcloud
import subprocess
from scdl import scdl

FEED = 'https://speakca.net/feed/'
SCDL = os.path.abspath(os.path.join(os.path.dirname(__file__), 'venv/bin/scdl'))
STATIC = os.path.join(os.path.dirname(__file__), 'static')
# Grab the track ID out of the <iframe> via regex
TRACK_RE = re.compile(r'api\.soundcloud\.com/tracks/([0-9]*?)&amp;')
session = requests.Session()


def main():
    parsed = feedparser.parse(FEED)
    for entry in parsed['entries']:
        print('Downloading from ' + entry['link'])
        r = session.get(entry['link'])
        r.raise_for_status()
        found = TRACK_RE.search(r.text)
        if not found:
            print('Unable to extract soundcloud :(')
            continue
        permalink = get_permalink_url(found.group(1))
        subprocess.check_call([SCDL, '-l', permalink], cwd=STATIC)


def get_permalink_url(track_id):
    client = soundcloud.Client(client_id=scdl.CLIENT_ID)
    track = client.get('/tracks/' + track_id)
    return track.permalink_url


if __name__ == '__main__':
    main()
