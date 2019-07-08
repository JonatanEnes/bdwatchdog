#!/usr/bin/env bash
pip3 install pymongo

export PYTHONUNBUFFERED="yes"
export POST_DOC_BUFFER_TIMEOUT=5
export TURBOSTAT_SAMPLING_FREQUENCY=5

python3 ../Powerapi/G5000/metagenomics/mongod_reader.py | python3 ./src/pipelines/json_to_TSDB_json.py | python2 ./src/pipelines/send_to_OpenTSDB.py
