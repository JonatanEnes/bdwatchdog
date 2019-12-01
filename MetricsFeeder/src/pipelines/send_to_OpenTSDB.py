# Copyright (c) 2019 Universidade da Coruna
# Authors:
#     - Jonatan Enes [main](jonatan.enes@udc.es, jonatan.enes.alvarez@gmail.com)
#     - Roberto R. Exposito
#     - Juan Tourino
#
# This file is part of the ServerlessContainers framework, from
# now on referred to as ServerlessContainers.
#
# ServerlessContainers is free software: you can redistribute it
# and/or modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation, either version 3
# of the License, or (at your option) any later version.
#
# ServerlessContainers is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ServerlessContainers. If not, see <http://www.gnu.org/licenses/>.


from __future__ import print_function

import fileinput
import sys
import json
import requests
import gzip

# TODO FIX, this should support python3
try:
    import StringIO  # for Python 2
except ImportError:
    from io import StringIO  # for Python 3

import time
import os

from requests.exceptions import ReadTimeout


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


# ENVIRONMENT VARIABLES #
POST_ENDPOINT_VARIABLE = "POST_ENDPOINT_PATH"
POST_DOC_BUFFER_LENGTH = "POST_DOC_BUFFER_LENGTH"
POST_DOC_BUFFER_TIMEOUT = "POST_DOC_BUFFER_TIMEOUT"
POST_SEND_DOCS_TIMEOUT = "POST_SEND_DOCS_TIMEOUT"
POST_SEND_DOCS_FAILED_TRIES = "POST_SEND_DOCS_FAILED_TRIES"

post_endpoint = os.getenv(POST_ENDPOINT_VARIABLE, 'http://opentsdb:4242/api/put')
post_doc_buffer_length = int(os.getenv(POST_DOC_BUFFER_LENGTH, 700))
post_doc_buffer_timeout = int(os.getenv(POST_DOC_BUFFER_TIMEOUT, 5))
post_send_docs_timeout = int(os.getenv(POST_SEND_DOCS_TIMEOUT, 3))
post_send_docs_failed_tries = int(os.getenv(POST_SEND_DOCS_FAILED_TRIES, 3))


def send_json_documents(json_documents, requests_Session=None):
    headers = {"Content-Type": "application/json", "Content-Encoding": "gzip"}

    #TODO Test this does not break with Python3
    out = StringIO.StringIO()
    with gzip.GzipFile(fileobj=out, mode="w") as f:
        f.write(json.dumps(json_documents))

    try:
        if requests_Session:
            r = requests_Session.post(post_endpoint, headers=headers, data=out.getvalue(),
                                      timeout=post_send_docs_timeout)
        else:
            r = requests.post(post_endpoint, headers=headers, data=out.getvalue(),
                              timeout=post_send_docs_timeout)
        if r.status_code != 204 and r.status_code != 400:
            return False, {"error": r.json()}
        else:
            if r.status_code == 400:
                return True, {}
                # return False, {"error": r.json()}
            return True, {}
    except ReadTimeout:
        return False, {"error": "Server timeout"}
    except Exception as e:
        return False, {"error": str(e)}


def behave_like_pipeline():
    # PROGRAM VARIABLES #
    last_timestamp = time.time() - post_doc_buffer_timeout + 1
    failed_connections = 0
    fails = 0
    MAX_FAILS = 10
    abort = False
    json_documents = []
    requests_Session = requests.Session()
    try:
        # for line in sys.stdin:
        while True:
            line = sys.stdin.readline()
            # for line in fileinput.input():
            try:
                new_doc = json.loads(line)
                json_documents = json_documents + [new_doc]
                fails = 0
            except ValueError as e:
                eprint("[TSDB SENDER] Error with document " + str(line))
                eprint(e)
                fails += 1
                if fails >= MAX_FAILS:
                    eprint("[TSDB SENDER] terminated due to too many read pipeline errors")
                    exit(1)
                continue

            current_timestamp = time.time()
            time_diff = current_timestamp - last_timestamp
            length_docs = len(json_documents)
            if length_docs >= post_doc_buffer_length or time_diff >= post_doc_buffer_timeout:
                last_timestamp = current_timestamp
                try:
                    success, info = send_json_documents(json_documents, requests_Session)
                    if not success:
                        eprint(
                            "[TSDB SENDER] couldn't properly post documents to address " + post_endpoint + " error: " + str(
                                info))
                        failed_connections += 1
                    else:
                        print("Post was done at: " + time.strftime("%D %H:%M:%S", time.localtime()) + " with " + str(
                            length_docs) + " documents")
                        failed_connections = 0  # Reset failed connections, at least this one was successfull now
                        json_documents = []  # Empty document buffer
                except requests.exceptions.ConnectTimeout:
                    failed_connections += 1
                    eprint(
                        "[TSDB SENDER] couldn't send documents to address " + post_endpoint + " and tried for " + str(
                            failed_connections) + " times")
                    if failed_connections >= post_send_docs_failed_tries:
                        abort = True

                if abort:
                    eprint("[TSDB SENDER] terminated due to too connection errors")
                    exit(1)
                sys.stdout.flush()
    except (KeyboardInterrupt, IOError):
        # Exit silently
        pass
    except Exception as e:
        eprint("[TSDB SENDER] terminated with error: " + str(e))


def main():
    behave_like_pipeline()


if __name__ == "__main__":
    main()
