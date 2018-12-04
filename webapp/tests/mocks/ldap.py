#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

import pytest
from ldap3 import Connection, MOCK_SYNC


@pytest.fixture()
def ldap_create_everything():
    """
    Creates the users, groups and categories inside the mock LDAP
    :return: returns the mock connection
    """
    conn = Connection("mock-server", client_strategy=MOCK_SYNC)
    conn.bind()

    # Create all the categories
    conn.strategy.add_entry(
        "ou=employees,dc=domain,dc=com",
        {
            "ou": "employees",
            "objectClass": "organizationalUnit",
            "description": "Employees",
        },
    )
    conn.strategy.add_entry(
        "ou=users,ou=employees,dc=domain,dc=com",
        {
            "ou": "users",
            "objectClass": "organizationalUnit",
            "description": "All the employeers",
        },
    )

    # Create all the groups
    conn.strategy.add_entry(
        "cn=group1,ou=employees,dc=domain,dc=com",
        {
            "cn": "group1",
            "objectClass": "posixGroup",
            "memberUid": "nefix",
            "description": "Description for Group 1",
        },
    )
    conn.strategy.add_entry(
        "cn=group2,cn=group1,ou=employees,dc=domain,dc=com",
        {
            "cn": "group2",
            "objectClass": "posixGroup",
            "memberUid": "nefix",
            "description": "Description for Group 2",
        },
    )

    # Create all the users
    conn.strategy.add_entry(
        "uid=nefix,cn=group2,cn=group1,ou=users,ou=employees,dc=domain,dc=com",
        {
            "uid": "nefix",
            "cn": "Néfix Estrada",
            "objectclass": "person",
            "userPassword": "P4$$w0rd! ",
            "displayName": "Néfix Estrada",
            "mail": "nefix@domain.com",
        },
    )
    conn.strategy.add_entry(
        "uid=individual,dc=domain,dc=com",
        {
            "uid": "individual",
            "cn": "Individual User",
            "objectclass": "person",
            "userPassword": "P4$$w0rd! ",
            "displayName": "Individual User",
            "mail": "individual@domain.com",
        },
    )

    return conn
