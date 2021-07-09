#!/bin/sh
export PYTHONWARNINGS="ignore:Unverified HTTPS request"
cd /apiv2
python3 start.py &
cd /api
python3 startv3.py