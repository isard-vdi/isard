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

# TODO: Check if the configuration was existing
# Copy the default configuration as the main configuration during the tests
shutil.copy("../../isard.conf.default", "../../isard.conf")

# Start the DB
p = subprocess.Popen("rethinkdb", stdout=open(os.devnull, "w"))

# Run the tests
os.environ["TESTING_WEBAPP"] = "true"
pytest.main(
    ["-v", "--cov-report=term-missing", "--cov=../models", "--cov=../auth"] + argv[1:]
)

# Stop the DB
p.kill()

# Cleanup
os.unsetenv("TESTING_WEBAPP")
os.remove(".coverage")
os.remove("../../isard.conf")
shutil.rmtree("rethinkdb_data")
