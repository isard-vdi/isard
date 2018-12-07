#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

ldap_users = [
    {
        "id": "professor",
        "password": "professor",
        "kind": "ldap",
        "name": "Professor Farnsworth",
        "mail": "professor@planetexpress.com",
        "role": None,
        "category": "people",
        "group": "admin_staff",
        "active": True,
        "accessed": 0,
        "quota": None,
    },
    {
        "id": "fry",
        "password": "fry",
        "kind": "ldap",
        "name": "Fry",
        "mail": "fry@planetexpress.com",
        "role": None,
        "category": "people",
        "group": "ship_crew",
        "active": True,
        "accessed": 0,
        "quota": None,
    },
    {
        "id": "zoidberg",
        "password": "zoidberg",
        "kind": "ldap",
        "name": "Zoidberg",
        "mail": "zoidberg@planetexpress.com",
        "role": None,
        "category": "people",
        "group": "default_ldap",
        "active": True,
        "accessed": 0,
        "quota": None,
    },
    {
        "id": "hermes",
        "password": "hermes",
        "kind": "ldap",
        "name": "Hermes",
        "mail": "hermes@planetexpress.com",
        "role": None,
        "category": "people",
        "group": "admin_staff",
        "active": True,
        "accessed": 0,
        "quota": None,
    },
    {
        "id": "leela",
        "password": "leela",
        "kind": "ldap",
        "name": "Leela",
        "mail": "leela@planetexpress.com",
        "role": None,
        "category": "people",
        "group": "ship_crew",
        "active": True,
        "accessed": 0,
        "quota": None,
    },
    {
        "id": "bender",
        "password": "bender",
        "kind": "ldap",
        "name": "Bender",
        "mail": "bender@planetexpress.com",
        "role": None,
        "category": "people",
        "group": "ship_crew",
        "active": True,
        "accessed": 0,
        "quota": None,
    },
]

ldap_users_dn = {
    "professor": "cn=Hubert J. Farnsworth,ou=people,dc=planetexpress,dc=com",
    "fry": "cn=Philip J. Fry,ou=people,dc=planetexpress,dc=com",
    "zoidberg": "cn=John A. Zoidberg,ou=people,dc=planetexpress,dc=com",
    "hermes": "cn=Hermes Conrad,ou=people,dc=planetexpress,dc=com",
    "leela": "cn=Turanga Leela,ou=people,dc=planetexpress,dc=com",
    "bender": "cn=Bender Bending Rodríguez,ou=people,dc=planetexpress,dc=com",
}

ldap_default_category = {
    "id": "default_ldap",
    "name": "Default LDAP",
    "description": "This is the default LDAP category",
    "kind": "ldap",
    "role": None,
    "quota": None,
}

ldap_default_group = {
    "id": "default_ldap",
    "name": "Default LDAP",
    "description": "This is the default LDAP group",
    "kind": "ldap",
    "role": None,
    "quota": None,
}

ldap_categories = [
    {
        "id": "people",
        "name": "People",
        "description": "Planet Express crew",
        "kind": "ldap",
        "role": None,
        "quota": None,
    }
]

ldap_groups = [
    {
        "id": "ship_crew",
        "name": "Ship_Crew",
        "description": None,
        "kind": "ldap",
        "role": None,
        "quota": None,
    },
    {
        "id": "admin_staff",
        "name": "Admin_Staff",
        "description": None,
        "kind": "ldap",
        "role": None,
        "quota": None,
    },
]
