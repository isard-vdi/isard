#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3
import pytest
import bcrypt
import time
import rethinkdb as r

generated_users_passwords = ["P4$$w0rd! "]

generated_users = [
    {
        "id": "nefix",
        "password": bcrypt.hashpw(
            generated_users_passwords[0].encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8"),
        "kind": "local",
        "name": "Néfix Estrada",
        "mail": "nefix@domain.com",
        "role": None,
        "category": "admin",
        "group": "admin",
        "active": True,
        "accessed": time.time(),
        "quota": None,
    }
]

empty_user = {
    "id": "",
    "password": "",
    "kind": "local",
    "name": "",
    "mail": "",
    "role": None,
    "category": "",
    "group": "",
    "active": False,
    "accessed": 0,
    "quota": None,
}

generated_cfg = {
    "id": 1,
    "version": 0,
    "auth": {
        "local": {"active": True},
        "ldap": {
            "active": False,
            "ldap_server": "localhost",
            "bind_dn": "dc=planetexpress,dc=com",
            "query_dn": "",
            "query_password": "",
            "category_attribute": "ou",
            "group_objectclass": "Group",
            "group_attribute": "member",
            "selected_categories": ["people"],
            "selected_groups": ["admin_staff", "ship_crew"],
        },
    },
    "resources": {"code": False, "url": "http://www.isardvdi.com:5050"},
    "engine": {
        "intervals": {
            "status_polling": 10,
            "time_between_polling": 5,
            "test_hyp_fail": 20,
            "background_polling": 10,
            "transitional_states_polling": 2,
        },
        "ssh": {"paramiko_host_key_policy_check": False},
        "stats": {
            "active": True,
            "max_queue_domains_status": 10,
            "max_queue_hyps_status": 10,
            "hyp_stats_interval": 5,
        },
        "log": {"log_name": "isard", "log_level": "DEBUG", "log_file": "msg.log"},
        "timeouts": {
            "ssh_paramiko_hyp_test_connection": 4,
            "timeout_trying_ssh": 2,
            "timeout_trying_hyp_and_ssh": 10,
            "timeout_queues": 2,
            "timeout_hypervisor": 10,
            "libvirt_hypervisor_timeout_connection": 3,
            "timeout_between_retries_hyp_is_alive": 1,
            "retries_hyp_is_alive": 3,
        },
    },
    "grafana": {
        "active": False,
        "url": "http://isard-grafana",
        "web_port": 80,
        "carbon_port": 2003,
        "graphite_port": 3000,
    },
    "disposable_desktops": {"active": False},
    "voucher_access": {"active": False},
}

empty_cfg = {
    "id": 1,
    "version": 0,
    "auth": {
        "local": {"active": False},
        "ldap": {
            "active": False,
            "ldap_server": "",
            "bind_dn": "",
            "query_dn": "",
            "query_password": "",
            "category_attribute": "",
            "group_objectclass": "",
            "group_attribute": "",
            "selected_groups": [],
            "selected_categories": [],
        },
    },
    "resources": {"code": False, "url": ""},
    "engine": {
        "intervals": {
            "status_polling": 0,
            "time_between_polling": 0,
            "test_hyp_fail": 0,
            "background_polling": 0,
            "transitional_states_polling": 0,
        },
        "ssh": {"paramiko_host_key_policy_check": False},
        "stats": {
            "active": False,
            "max_queue_domains_status": 0,
            "max_queue_hyps_status": 0,
            "hyp_stats_interval": 0,
        },
        "log": {"log_name": "", "log_level": "", "log_file": ""},
        "timeouts": {
            "ssh_paramiko_hyp_test_connection": 0,
            "timeout_trying_ssh": 0,
            "timeout_trying_hyp_and_ssh": 0,
            "timeout_queues": 0,
            "timeout_hypervisor": 0,
            "libvirt_hypervisor_timeout_connection": 0,
            "timeout_between_retries_hyp_is_alive": 0,
            "retries_hyp_is_alive": 0,
        },
    },
    "grafana": {
        "active": False,
        "url": "",
        "web_port": 0,
        "carbon_port": 0,
        "graphite_port": 0,
    },
    "disposable_desktops": {"active": False},
    "voucher_access": {"active": False},
}

generated_categories = [
    {
        "id": "admin",
        "name": "Admin",
        "description": "Administrators",
        "kind": "local",
        "role": None,
        "quota": None,
    }
]

empty_category = {
    "id": "",
    "name": "",
    "description": "",
    "kind": "",
    "role": None,
    "quota": None,
}

generated_groups = [
    {
        "id": "advanced",
        "name": "Advanced",
        "description": "Advanced users",
        "kind": "local",
        "role": None,
        "quota": None,
    },
    {
        "id": "default_ldap",
        "name": "Default LDAP",
        "description": "This is the default LDAP group",
        "kind": "ldap",
        "role": None,
        "quota": None,
    },
]

empty_group = {
    "id": "",
    "name": "",
    "description": "",
    "kind": "",
    "role": None,
    "quota": None,
}

generated_roles = [
    {
        "id": "admin",
        "name": "Administrator",
        "description": "Is God",
        "permissions": [{"id": "media", "view": True, "edit": True}],
        "quota": {
            "domains": {
                "desktops": 99,
                "desktops_disk_max": 999999999,
                "templates": 99,
                "templates_disk_max": 999999999,
                "running": 99,
                "isos": 99,
                "isos_disk_max": 999999999,
            },
            "hardware": {"vcpus": 8, "memory": 20000000},
        },
    },
    {
        "id": "advanced",
        "name": "Advanced user",
        "description": "Can create desktops and templates and start them",
        "permissions": [{"id": "media", "view": True, "edit": True}],
        "quota": {
            "domains": {
                "desktops": 99,
                "desktops_disk_max": 999999999,
                "templates": 99,
                "templates_disk_max": 999999999,
                "running": 99,
                "isos": 99,
                "isos_disk_max": 999999999,
            },
            "hardware": {"vcpus": 8, "memory": 20000000},
        },
    },
    {
        "id": "user",
        "name": "User",
        "description": "Can create desktops and start them",
        "permissions": [{"id": "media", "view": False, "edit": False}],
        "quota": {
            "domains": {
                "desktops": 99,
                "desktops_disk_max": 999999999,
                "templates": 99,
                "templates_disk_max": 999999999,
                "running": 99,
                "isos": 99,
                "isos_disk_max": 999999999,
            },
            "hardware": {"vcpus": 8, "memory": 20000000},
        },
    },
]

empty_role = {
    "id": "",
    "name": "",
    "description": "",
    "permissions": [{"id": "media", "view": False, "edit": False}],
    "quota": {
        "domains": {
            "desktops": 0,
            "desktops_disk_max": 0,
            "templates": 0,
            "templates_disk_max": 0,
            "running": 0,
            "isos": 0,
            "isos_disk_max": 0,
        },
        "hardware": {"vcpus": 0, "memory": 0},
    },
}


@pytest.fixture()
def conn():
    """
    connects with the DB server
    :return: returns the DB connection
    """
    return r.connect("localhost", 28015)


@pytest.fixture()
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


@pytest.fixture()
def create_database(drop_database):
    """
    Creates the DB
    :return: returns the DB connection
    """
    r.db_create("isard").run(drop_database)
    drop_database.use("isard")

    return drop_database


@pytest.fixture()
def create_tables(create_database):
    """
    Creates the tables
    :return: returns the DB connection
    """
    r.table_create("users").run(create_database)
    r.table_create("config").run(create_database)
    r.table_create("categories").run(create_database)
    r.table_create("groups").run(create_database)
    r.table_create("roles").run(create_database)

    return create_database


@pytest.fixture()
def create_config(create_tables):
    """
    Creates the default configuration
    :return: returns de DB connection
    """
    r.table("config").insert(generated_cfg).run(create_tables)

    return create_tables


@pytest.fixture()
def create_users(create_config):
    """
    Creates the users inside the users table
    :return: returns the DB connection
    """
    r.table("users").insert(generated_users).run(create_config)

    return create_config


@pytest.fixture()
def create_admin(create_config):
    """
    Creates the admin inside the users table
    :return: returns the DB connection
    """
    admin = generated_users[0].copy()
    admin["id"] = "admin"
    admin["name"] = "Administrator"
    admin["mail"] = "admin@isard.io"
    admin["kind"] = "ldap"

    r.table("users").insert(admin).run(create_config)

    return create_config


@pytest.fixture()
def create_categories(create_config):
    """
    Creates the categories inside the categories table
    :return: returns the DB connection
    """
    r.table("categories").insert(generated_categories).run(create_config)

    return create_config


@pytest.fixture()
def create_groups(create_config):
    """
    Creates the groups inside the groups table
    :return: returns the DB connection
    """
    r.table("groups").insert(generated_groups).run(create_config)

    return create_config


@pytest.fixture()
def create_roles(create_config):
    """
    Creates the roles inside the roles table
    :return: returns the DB connection
    """
    r.table("roles").insert(generated_roles).run(create_config)

    return create_config
