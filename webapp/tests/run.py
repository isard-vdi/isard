#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3
import subprocess
import os
import pytest
from sys import argv
import shutil

# Start the DB
p = subprocess.Popen("rethinkdb", stdout=open(os.devnull, "w"))

# Run the tests
pytest.main(
    ["-v", "--cov-report=term-missing", "--cov=../models", "--cov=../auth"] + argv[1:]
)

# Stop the DB
p.kill()

# Remove the DB files
shutil.rmtree("rethinkdb_data")
