#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2018 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
#      Néfix Estrada Campañá
# License: AGPLv3

import rethinkdb as r

from ..lib.db import DB


# is None DB migration: LDAP
class Config:
    """
    Config is the class that contains all the actions related with the configuration
    """

    def __init__(self, cfg=None):
        self.conn = DB().conn

        if cfg is None:
            cfg = {
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

        self.id = cfg["id"]
        self.version = cfg["version"]

        self.auth = cfg["auth"]
        self.resources = cfg["resources"]

        self.engine = cfg["engine"]
        self.grafana = cfg["grafana"]

        self.disposable_desktops = cfg["disposable_desktops"]
        self.voucher_access = cfg["voucher_access"]

    def get(self):
        cfg = r.table("config").get(1).run(self.conn)

        if cfg is None:
            raise self.NotFound

        self.id = cfg["id"]
        self.version = cfg["version"]

        self.auth = cfg["auth"]
        self.resources = cfg["resources"]

        self.engine = cfg["engine"]
        self.grafana = cfg["grafana"]

        self.disposable_desktops = cfg["disposable_desktops"]
        self.voucher_access = cfg["voucher_access"]

    class NotFound(Exception):
        """
        This exception is raised when the configuration isn't found in the DB
        """

        pass
