#!/usr/bin/env python3
import isardvdi_common.log
from waitress import serve

from notifier import app

if __name__ == "__main__":
    serve(app, listen="*:5000")
