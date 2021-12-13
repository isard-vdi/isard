#!/bin/sh
export PYTHONWARNINGS="ignore:Unverified HTTPS request"
cd /api
python3 -u startv3.py
