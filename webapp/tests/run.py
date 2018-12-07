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

# Copy the default configuration as the main configuration during the tests
shutil.copy("../../isard.conf.default", "../../isard.conf")

# Start the DB and the LDAP server
subprocess.call(
    [
        "sudo",
        "docker",
        "run",
        "-d",
        "-p",
        "28015:28015",
        "--name=testing-webapp-rethink",
        "rethinkdb",
    ]
)

subprocess.call(
    [
        "sudo",
        "docker",
        "run",
        "--privileged",
        "-d",
        "-p",
        "389:389",
        "--name=testing-webapp-ldap",
        "rroemhild/test-openldap",
    ]
)

# Run the tests
os.environ["TESTING_WEBAPP"] = "true"
pytest.main(
    ["-v", "--cov-report=term-missing", "--cov=../models", "--cov=../auth"] + argv[1:]
)

# Stop the DB and the LDAP server
subprocess.call(["sudo", "docker", "rm", "-vf", "testing-webapp-rethink"])
subprocess.call(["sudo", "docker", "rm", "-vf", "testing-webapp-ldap"])

# Cleanup
os.unsetenv("TESTING_WEBAPP")
os.remove(".coverage")
os.remove("../../isard.conf")
