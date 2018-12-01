#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3
import pytest
import rethinkdb as r

users = [
    {
        "id": "nefix",
        "name": "Néfix Estrada",
        "password": "P4$$w0rd! ",
        "role": "admin",
        "category": "admin",
        "group": "admin",
        "mail": "nefix@domain.com",
        "quota": None,
        "active": True,
    }
]


@pytest.fixture(scope="session")
def conn():
    """
    connects with the DB server
    :return: returns the DB connection
    """
    return r.connect("localhost", 28015)


@pytest.fixture(scope="function")
def drop_database(conn):
    """
    Deletes the DB
    :return: returns the DB connection
    """
    try:
        r.db_drop("isard").run(conn)

    except r.ReqlRuntimeError:
        pass

    return conn


@pytest.fixture(scope="function")
def create_database(drop_database):
    """
    Creates the DB
    :return: returns the DB connection
    """
    r.db_create("isard").run(drop_database)
    drop_database.use("isard")

    return drop_database


@pytest.fixture(scope="function")
def create_tables(create_database):
    """
    Creates the tables
    :return: returns the DB connection
    """
    r.table_create("users").run(create_database)

    return create_database


@pytest.fixture(scope="function")
def create_users(create_tables):
    """
    Creates the users inside the users table
    :return: returns the DB connection
    """
    r.table("users").insert(users).run(create_tables)

    return create_tables
