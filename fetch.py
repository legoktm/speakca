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
import feedparser
import os
import re
import requests
import soundcloud
import subprocess
from scdl import scdl
import tempfile

FEED = 'https://speakca.net/feed/'
SCDL = os.path.abspath(os.path.join(os.path.dirname(__file__), 'venv/bin/scdl'))
STATIC = os.path.join(os.path.dirname(__file__), 'static')
# Grab the track ID out of the <iframe> via regex
TRACK_RE = re.compile(r'api\.soundcloud\.com/tracks/([0-9]*?)&amp;')
session = requests.Session()
s3 = boto3.resource('s3')
bucket = s3.Bucket('alexa-speakca')


def main():
    downloaded = set()

    for obj in bucket.objects.all():
        full_obj = s3.Object(obj.bucket_name, obj.key)
        if 'url' in full_obj.metadata:
            downloaded.add(full_obj.metadata.get('url'))

    i = 1
    do = []
    while True:
        r = requests.get(FEED, params={'paged': i})
        if not r.ok:
            break
        parsed = feedparser.parse(r.text)
        for entry in parsed['entries']:
            if entry['link'] in downloaded:
                print('Skipping %s, already fetched' % entry['link'])
                continue
            print('Downloading from ' + entry['link'])
            r = session.get(entry['link'])
            r.raise_for_status()
            found = TRACK_RE.search(r.text)
            if not found:
                print('Unable to extract soundcloud :(')
                continue
            permalink = get_permalink_url(found.group(1))
            do.append([permalink, entry['link']])
        i += 1

    print(do)
    # Reverse so they get uploaded in reverse order
    for permalink, link in reversed(do):
        with tempfile.TemporaryDirectory() as tmpdirname:
            # scdl will download into the cwd with the episode's filename
            subprocess.check_call([SCDL, '-l', permalink], cwd=tmpdirname)
            print(os.listdir(tmpdirname))
            # It's a temporary directory, there should only be one file
            basename = os.listdir(tmpdirname)[0]
            fname = os.path.join(tmpdirname, basename)
            # Sanity check
            assert fname.endswith('.mp3')
            # Preserve the mtime
            finalname = os.path.join(STATIC, basename)
            # Send it through ffmpeg per Amazon's requirements:
            # https://developer.amazon.com/docs/custom-skills/speech-synthesis-markup-language-ssml-reference.html
            subprocess.check_call([
                'ffmpeg', '-i', fname,
                '-ac', '2',
                '-codec:2', 'libmp3lame',
                '-b:a', '48k',
                '-ar', '16000',
                finalname
            ])
            print('Uploading to S3...')
            bucket.upload_file(finalname, basename, ExtraArgs={
                'ACL': 'public-read',
                'Metadata': {
                    'url': link
                }
            })


def get_permalink_url(track_id: str) -> str:
    client = soundcloud.Client(client_id=scdl.CLIENT_ID)
    track = client.get('/tracks/' + track_id)
    return track.permalink_url


if __name__ == '__main__':
    main()
