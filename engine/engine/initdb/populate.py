# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import sys
import time
import traceback
import uuid

from rethinkdb import r

from .lib import *
from .log import *


class Populate(object):
    def __init__(self):
        cfg = loadConfig()
        self.cfg = cfg.cfg()
        self.check_db()
        self.p = Password()
        self.passwd = self.p.encrypt(self.cfg["WEBAPP_ADMIN_PWD"])
        if self.is_database_created() is True:
            log.info("Database engine already present...")
            Certificates().get_viewer(update_db=True)
        else:
            log.error("Something went wrong when initially populating db")
            exit

    def check_db(self):
        ready = False
        while not ready:
            try:
                self.conn = r.connect(
                    host=self.cfg["RETHINKDB_HOST"],
                    port=self.cfg["RETHINKDB_PORT"],
                    db=self.cfg["RETHINKDB_DB"],
                ).repl()
                print("Database server OK")
                ready = True
            except Exception as e:
                print(
                    "Populate error: Database server "
                    + self.cfg["RETHINKDB_HOST"]
                    + ":"
                    + self.cfg["RETHINKDB_PORT"]
                    + " not present. Waiting to be ready"
                )
                time.sleep(0.5)
        ready = False

    """
    DATABASE
    """

    def is_database_created(self):
        self.update_virtinstalls()
        try:
            if not r.db_list().contains(self.cfg["RETHINKDB_DB"]).run(self.conn):
                log.warning(
                    "Database {} not found, creating new one.".format(
                        self.cfg["RETHINKDB_DB"]
                    )
                )
                r.db_create(self.cfg["RETHINKDB_DB"]).run(self.conn)
                log.info("Populating database with tables and initial data")
                self.check_integrity()
                return True
            log.info("Database {} found.".format(self.cfg["RETHINKDB_DB"]))
            self.check_integrity()
            return True
        except Exception as e:
            log.error(traceback.format_exc())
            return False

    # ~ def defaults(self):
    # ~ return self.check_integrity()

    def check_integrity(self, commit=True):
        log.info(
            "------------ CHECKING DATABASE VERSION, TABLES AND INDEXES ------------"
        )
        dbtables = r.table_list().run(self.conn)
        newtables = [
            "roles",
            "categories",
            "groups",
            "users",
            "vouchers",
            "hypervisors",
            "hypervisors_pools",
            "interfaces",
            "graphics",
            "videos",
            "desktops_priority",
            "domains",
            "virt_install",
            "media",
            "boots",
            "scheduler_jobs",
            "backups",
            "engine",
            "qos_net",
            "qos_disk",
            "disk_bus",
            "remotevpn",
            "deployments",
            "secrets",
            "bookings",
            "bookings_resources",
            "bookings_priority",
            "resource_planner",
            "gpu_profiles",
            "gpus",
            "reservables_vgpus",
            "vgpus",
            "storage",
            "storage_pool",
            "logs_desktops",
            "logs_users",
            "usage_consumption",
            "usage_credit",
            "usage_parameter",
            "usage_grouping",
            "usage_limit",
            "usage_reset_dates",
            "user_storage",
            "recycle_bin",
            "authentication",
            "analytics",
            "notification_tmpls",
            "system_events",
            "targets",
            "users_migrations",
            "users_migrations_exceptions",
            "notifications",
            "notifications_data",
            "notifications_action",
            # "recycle_bin_archive",
            # config should be the last table to be created
            # api waits for config table to start
            "config",
        ]
        tables_to_create = list(set(newtables) - set(dbtables))
        d = {k: v for v, k in enumerate(newtables)}
        tables_to_create.sort(key=d.get)
        tables_to_delete = list(set(dbtables) - set(newtables))
        print("TABLES TO BE CREATED: " + ",".join(tables_to_create))
        log.info("TABLES TO BE CREATED: " + ",".join(tables_to_create))
        log.info("TABLES TO BE DELETED: " + ",".join(tables_to_delete))
        if not commit:
            return {
                "tables_to_create": tables_to_create,
                "tables_to_delete": tables_to_delete,
            }
        else:
            for t in tables_to_create:
                try:
                    table = t
                    log.info("Creating new table: " + t)
                    # CREATING TABLES WITH eval self.{name_of_table}
                    log.info("  Result: " + str(eval("self." + table + "()")))
                except Exception as e:
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                    log.error(exc_type, fname, exc_tb.tb_lineno)
                    return False
            for t in tables_to_delete:
                try:
                    log.info("Deleting old table: " + t)
                    log.info("  Result: " + str(r.table_drop(t).run(self.conn)))
                except Exception as e:
                    exc_type, exc_obj, exc_tb = sys.exc_info()
                    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
                    log.error(exc_type, fname, exc_tb.tb_lineno)
                    return False
        return True

    def create_table(self, table_name):
        exists = r.table_list().contains(table_name).run(self.conn)
        if not exists:
            log.info(f"Table {table_name} not found, creating...")
            r.table_create(table_name, primary_key="id").run(self.conn)
        return exists

    """
    CONFIG
    """

    def config(self):
        if not self.create_table("config"):
            self.result(
                r.table("config")
                .insert(
                    [
                        {
                            "id": 1,
                            "auth": {
                                "local": {"active": True},
                                "ldap": {
                                    "active": False,
                                    "ldap_server": "ldap://ldap.domain.org",
                                    "bind_dn": "dc=domain,dc=org",
                                },
                            },
                            "disposable_desktops": {"active": False},
                            "voucher_access": {"active": False},
                            "engine": {
                                "intervals": {
                                    "status_polling": 10,
                                    "time_between_polling": 5,
                                    "test_hyp_fail": 20,
                                    "background_polling": 10,
                                    "transitional_states_polling": 10,
                                },
                                "ssh": {"paramiko_host_key_policy_check": False},
                                "stats": {
                                    "active": True,
                                    "max_queue_domains_status": 10,
                                    "max_queue_hyps_status": 10,
                                    "hyp_stats_interval": 5,
                                },
                                "log": {
                                    "log_name": "isard",
                                    "log_level": "WARNING",
                                },
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
                                "url": "",
                                "hostname": "isard-grafana",
                                "carbon_port": 2004,
                                "interval": 5,
                            },
                            "version": 0,
                            "shares": {"templates": False, "isos": False},
                            "resources": {
                                "code": False,
                                "url": "https://repository.isardvdi.com",
                            },
                        }
                    ],
                    conflict="update",
                )
                .run(self.conn)
            )
            log.info("Table config populated with defaults.")
            return True
        else:
            return False

    """
    BACKUPS
    """

    def backups(self):
        self.create_table("backups")
        return True

    """
    USERS
    Updated in Domains for
    """

    def users(self):
        if not self.create_table("users"):
            if r.table("users").get("admin").run(self.conn) is None:
                usr = [
                    {
                        "id": "local-default-admin-admin",
                        "name": "Administrator",
                        "provider": "local",
                        "category": "default",
                        "uid": "admin",
                        "username": "admin",
                        "active": True,
                        "accessed": int(time.time()),
                        "password": self.passwd,
                        "role": "admin",
                        "group": "default-default",
                        "email": "admin@isard.io",
                        "photo": "",
                        "quota": False,
                    }
                ]
                self.result(
                    r.table("users").insert(usr, conflict="update").run(self.conn)
                )
                log.info(
                    "  Inserted default admin  username with password defined in isardvdi.cfg"
                )
        self.index_create("users", ["provider", "uid", "category", "group"])
        return True

    """
    VOUCHERS
    Grant access on new voucher
    """

    def vouchers(self):
        self.create_table("vouchers")
        return True

    """
    ROLES
    """

    def roles(self):
        if not self.create_table("roles"):
            self.result(
                r.table("roles")
                .insert(
                    [
                        {
                            "id": "user",
                            "name": "User",
                            "description": "Can create desktops and start it",
                            "sortorder": 1,
                        },
                        {
                            "id": "advanced",
                            "name": "Advanced",
                            "description": "Can create desktops and templates and start desktops",
                            "sortorder": 2,
                        },
                        {
                            "id": "manager",
                            "name": "Manager",
                            "description": "Can manage users, desktops, templates and media in a category",
                            "sortorder": 3,
                        },
                        {
                            "id": "admin",
                            "name": "Administrator",
                            "description": "Is God",
                            "sortorder": 4,
                        },
                    ]
                )
                .run(self.conn)
            )
        return True

    """
    CATEGORIES
    """

    def categories(self):
        if not self.create_table("categories"):
            if r.table("categories").get("admin").run(self.conn) is None:
                self.result(
                    r.table("categories")
                    .insert(
                        [
                            {
                                "id": "default",
                                "name": "Default",
                                "description": "Default category",
                                "frontend": True,
                                "quota": False,
                                "limits": False,
                            }
                        ]
                    )
                    .run(self.conn)
                )
        return True

    """
    GROUPS
    """

    def groups(self):
        if not self.create_table("groups"):
            if r.table("groups").get("default").run(self.conn) is None:
                self.result(
                    r.table("groups")
                    .insert(
                        [
                            {
                                "id": "default-default",
                                "uid": "default",
                                "parent_category": "default",
                                "enrollment": {
                                    "manager": False,
                                    "advanced": False,
                                    "user": False,
                                },
                                "name": "Default",
                                "description": "[Default] Default group",
                                "quota": False,
                                "limits": False,
                            }
                        ]
                    )
                    .run(self.conn)
                )
        return True

    """
    REMOTE_VPN
    """

    def remotevpn(self):
        self.create_table("remotevpn")
        return True

    """
    DEPLOYMENTS
    """

    def deployments(self):
        if not self.create_table("deployments"):
            self.index_create("deployments", ["user"])
        return True

    """
    SECRETS
    """

    def secrets(self):
        self.create_table("secrets")
        return True

    # {'allowed': {'groups': [], 'users': False},
    #  'description': '',
    #  'forced_hyp': ['false'],
    #  'hardware': {'boot_order': ['disk'],
    #               'disk_bus': 'virtio',
    #               'graphics': ['default'],
    #               'interfaces': ['default'],
    #               'memory': 524288,
    #               'qos_id': 'unlimited',
    #               'vcpus': 1,
    #               'videos': ['default']},
    #  'hypervisors_pools': ['default'],
    #  'name': 'asdfasdf',
    #  'tag': 'asdfasdf',
    #  'tag_visible': False,

    """
    QOS_NETWORK
    """

    def qos_net(self):
        if not self.create_table("qos_net"):
            self.result(
                r.table("qos_net")
                .insert(
                    [
                        {
                            "id": "unlimited",
                            "name": "Unlimited",
                            "description": "Unlimited network throughput",
                            "bandwidth": {
                                "inbound": {
                                    "@average": 0,
                                    "@peak": 0,
                                    "@floor": 0,
                                    "@burst": 0,
                                },
                                "outbound": {"@average": 0, "@peak": 0, "@burst": 0},
                            },
                            "allowed": {
                                "roles": ["admin"],
                                "categories": False,
                                "groups": False,
                                "users": False,
                            },
                        }
                    ]
                )
                .run(self.conn)
            )
            self.result(
                r.table("qos_net")
                .insert(
                    [
                        {
                            "id": "limit1M",
                            "name": "limit up and down to 1Mbps",
                            "description": "limit upstream and downstream to 1Mbps(125KBytes/s) and burst of 10Mbps for a max 100MB transfer.",
                            "bandwidth": {
                                "inbound": {
                                    "@average": 125,
                                    "@peak": 1250,
                                    "@floor": 0,
                                    "@burst": 12500,
                                },
                                "outbound": {
                                    "@average": 125,
                                    "@peak": 1250,
                                    "@burst": 12500,
                                },
                            },
                            "allowed": {
                                "roles": ["admin"],
                                "categories": False,
                                "groups": False,
                                "users": False,
                            },
                        }
                    ]
                )
                .run(self.conn)
            )

    """
    QOS_DISK
    """

    def qos_disk(self):
        if not self.create_table("qos_disk"):
            self.result(
                r.table("qos_disk")
                .insert(
                    [
                        {
                            "id": "unlimited",
                            "name": "Unlimited",
                            "description": "Unlimited BW/IO to disk",
                            "iotune": {
                                # throughput limit in bytes per second.
                                "read_bytes_sec": 0,
                                "write_bytes_sec": 0,
                                # maximum throughput limit in bytes per second.
                                "read_bytes_sec_max": 0,
                                "write_bytes_sec_max": 0,
                                # maximum duration in seconds for the write_bytes_sec_max burst period.
                                # Only valid when the bytes_sec_max is set.
                                "read_bytes_sec_max_length": 0,
                                "write_bytes_sec_max_length": 0,
                                # I/O operations per second.
                                "read_iops_sec": 0,
                                "write_iops_sec": 0,
                                # maximum read I/O operations per second.
                                "write_iops_sec_max": 0,
                                "size_iops_sec": 0,
                                # maximum duration in seconds for the read_iops_sec_max burst period.
                                # Only valid when the iops_sec_max is set.
                                "read_iops_sec_max_length": 0,
                                "write_iops_sec_max_length": 0,
                            },
                            "allowed": {
                                "roles": ["admin"],
                                "categories": False,
                                "groups": False,
                                "users": False,
                            },
                        }
                    ]
                )
                .run(self.conn)
            )
            self.result(
                r.table("qos_disk")
                .insert(
                    [
                        {
                            "id": "limit50MBps",
                            "name": "BW:50MBps/IOPS:10K",
                            "description": "limit write and read to 50Mbps and IOPs to 10K",
                            "iotune": {
                                # throughput limit in bytes per second.
                                "read_bytes_sec": 50 * 1e6,
                                "write_bytes_sec": 50 * 1e6,
                                # maximum throughput limit in bytes per second.
                                "read_bytes_sec_max": 0,
                                "write_bytes_sec_max": 0,
                                # maximum duration in seconds for the write_bytes_sec_max burst period.
                                # Only valid when the bytes_sec_max is set.
                                "read_bytes_sec_max_length": 0,
                                "write_bytes_sec_max_length": 0,
                                # I/O operations per second.
                                "read_iops_sec": 10 * 1e3,
                                "write_iops_sec": 10 * 1e3,
                                # maximum read I/O operations per second.
                                "write_iops_sec_max": 0,
                                "size_iops_sec": 0,
                                # maximum duration in seconds for the read_iops_sec_max burst period.
                                # Only valid when the iops_sec_max is set.
                                "read_iops_sec_max_length": 0,
                                "write_iops_sec_max_length": 0,
                            },
                            "allowed": {
                                "roles": ["admin"],
                                "categories": False,
                                "groups": False,
                                "users": False,
                            },
                        }
                    ]
                )
                .run(self.conn)
            )

    """
    DISK BUS
    """

    def disk_bus(self):
        if not self.create_table("disk_bus"):
            self.result(
                r.table("disk_bus")
                .insert(
                    [
                        {
                            "id": "default",
                            "name": "Default",
                            "description": "",
                            "allowed": {
                                "roles": [],
                                "categories": [],
                                "groups": [],
                                "users": [],
                            },
                        },
                        {
                            "id": "virtio",
                            "name": "Virtio",
                            "description": "",
                            "allowed": {
                                "roles": [],
                                "categories": False,
                                "groups": False,
                                "users": False,
                            },
                        },
                        {
                            "id": "ide",
                            "name": "IDE",
                            "description": "",
                            "allowed": {
                                "roles": [],
                                "categories": False,
                                "groups": False,
                                "users": False,
                            },
                        },
                        {
                            "id": "sata",
                            "name": "SATA",
                            "description": "",
                            "allowed": {
                                "roles": [],
                                "categories": False,
                                "groups": False,
                                "users": False,
                            },
                        },
                    ]
                )
                .run(self.conn)
            )
        return True

    """
    INTERFACE
    """

    def interfaces(self):
        if not self.create_table("interfaces"):
            self.result(
                r.table("interfaces")
                .insert(
                    [
                        {
                            "id": "default",
                            "name": "Default",
                            "description": "Virtio isolated desktop network with dhcp",
                            "ifname": "default",
                            "kind": "network",
                            "model": "virtio",
                            "net": "default",
                            "qos_id": False,
                            "allowed": {
                                "roles": [],
                                "categories": [],
                                "groups": [],
                                "users": [],
                            },
                        }
                    ]
                )
                .run(self.conn)
            )
            self.result(
                r.table("interfaces")
                .insert(
                    [
                        {
                            "id": "e1000_isolated",
                            "name": "Intel PRO/1000 isolated",
                            "description": "Compatible Intel PRO/1000 (e1000) isolated desktop network with dhcp",
                            "ifname": "default",
                            "kind": "network",
                            "model": "e1000",
                            "net": "default",
                            "qos_id": False,
                            "allowed": {
                                "roles": [],
                                "categories": [],
                                "groups": [],
                                "users": [],
                            },
                        }
                    ]
                )
                .run(self.conn)
            )
            self.result(
                r.table("interfaces")
                .insert(
                    [
                        {
                            "id": "virtio_shared",
                            "name": "Virtio shared",
                            "description": "Virtio shared desktop network with dhcp.",
                            "ifname": "shared",
                            "kind": "network",
                            "model": "virtio",
                            "net": "shared",
                            "qos_id": False,
                            "allowed": {
                                "roles": ["admin"],
                                "categories": False,
                                "groups": False,
                                "users": False,
                            },
                        }
                    ]
                )
                .run(self.conn)
            )
            for i in range(1, 6):
                self.result(
                    r.table("interfaces")
                    .insert(
                        [
                            {
                                "id": "private" + str(i),
                                "name": "Private " + str(i),
                                "description": "Private Virtio non isolated network without dhcp nor gateway",
                                "ifname": "private" + str(i),
                                "kind": "network",
                                "model": "virtio",
                                "net": "private" + str(i),
                                "qos_id": "unlimited",
                                "allowed": {
                                    "roles": ["admin"],
                                    "categories": False,
                                    "groups": False,
                                    "users": False,
                                },
                            }
                        ]
                    )
                    .run(self.conn)
                )

        self.index_create("interfaces", ["roles", "categories", "groups", "users"])
        return True

    """
    GRAPHICS
    """

    def graphics(self):
        if not self.create_table("graphics"):
            self.result(
                r.table("graphics")
                .insert(
                    [
                        {
                            "id": "default",
                            "name": "Default",
                            "description": "Spice viewer with compression and vnc",
                            "allowed": {
                                "roles": [],
                                "categories": [],
                                "groups": [],
                                "users": [],
                            },
                            "types": {
                                "spice": {
                                    "options": {
                                        "image": {"compression": "auto_glz"},
                                        "jpeg": {"compression": "always"},
                                        "playback": {"compression": "off"},
                                        "streaming": {"mode": "all"},
                                        "zlib": {"compression": "always"},
                                    },
                                },
                                "vnc": {"options": {}},
                            },
                        }
                    ]
                )
                .run(self.conn)
            )
        return True

    """
    VIDEOS
    """

    def videos(self):
        if not self.create_table("videos"):
            self.result(
                r.table("videos")
                .insert(
                    [
                        {
                            "id": "qxl32",
                            "name": "QXL 32MB",
                            "description": "QXL 32MB",
                            "ram": 32768,
                            "vram": 32768,
                            "model": "qxl",
                            "heads": 1,
                            "allowed": {
                                "roles": ["admin"],
                                "categories": False,
                                "groups": False,
                                "users": False,
                            },
                        },
                        {
                            "id": "default",
                            "name": "Default",
                            "description": "Default video card",
                            "ram": 65536,
                            "vram": 65536,
                            "model": "qxl",
                            "heads": 1,
                            "allowed": {
                                "roles": [],
                                "categories": [],
                                "groups": [],
                                "users": [],
                            },
                        },
                        {
                            "id": "vga",
                            "name": "VGA",
                            "description": "For old OSs",
                            "ram": 16384,
                            "vram": 16384,
                            "model": "vga",
                            "heads": 1,
                            "allowed": {
                                "roles": ["admin"],
                                "categories": False,
                                "groups": False,
                                "users": False,
                            },
                        },
                    ]
                )
                .run(self.conn)
            )
        return True

    """
    BOOTS
    """

    def boots(self):
        if not self.create_table("boots"):
            self.result(
                r.table("boots")
                .insert(
                    [
                        {
                            "id": "disk",
                            "name": "Hard Disk",
                            "description": "Boot based on hard disk list order",
                            "allowed": {
                                "roles": [],
                                "categories": [],
                                "groups": [],
                                "users": [],
                            },
                        },
                        {
                            "id": "iso",
                            "name": "CD/DVD",
                            "description": "Boot based from ISO",
                            "allowed": {
                                "roles": ["admin"],
                                "categories": False,
                                "groups": False,
                                "users": False,
                            },
                        },
                        {
                            "id": "pxe",
                            "name": "PXE",
                            "description": "Boot from network",
                            "allowed": {
                                "roles": ["admin"],
                                "categories": False,
                                "groups": False,
                                "users": False,
                            },
                        },
                        {
                            "id": "floppy",
                            "name": "Floppy",
                            "description": "Boot from floppy disk",
                            "allowed": {
                                "roles": ["admin"],
                                "categories": False,
                                "groups": False,
                                "users": False,
                            },
                        },
                    ]
                )
                .run(self.conn)
            )
            return True

    """
    ISOS and FLOPPY:
    """

    def media(self):
        self.create_table("media")
        self.index_create("media", ["status", "user", "kind"])
        return True

    """
    APPSCHEDULER JOBS:
    """

    def scheduler_jobs(self):
        self.create_table("scheduler_jobs")
        return True

    """
    HYPERVISORS
    """

    def hypervisors(self):
        """
        Read RethinkDB configuration from file
        """
        self.create_table("hypervisors")
        return True
        # old configuration when hypers not auto-register in databsae
        # rhyper = r.table('hypervisors')
        # return self.result(rhyper.insert([{'id': 'isard-hypervisor',
        #                                  'hostname': 'isard-hypervisor',
        #                                  'viewer_hostname': 'localhost',
        #                                  'viewer_nat_hostname': 'localhost',
        #                                  'viewer_nat_offset': 0,
        #                                  'user': 'root',
        #                                  'port': '2022',
        #                                  'uri': '',
        #                                  'capabilities': {'disk_operations': True,
        #                                                   'hypervisor': True},
        #                                  'hypervisors_pools': ['default'],
        #                                  'enabled': True,
        #                                  'status': 'Offline',
        #                                  'status_time': False,
        #                                  'prev_status': [],
        #                                  'detail': '',
        #                                  'description': 'Default hypervisor',
        #                                  'info': []},
        #                                 ]).run(self.conn))
        # self.hypervisors_pools(disk_operations=[key])
        self.hypervisors_pools()

    """
    HYPERVISORS POOLS
    """

    def hypervisors_pools(self, disk_operations=["isard-hypervisor"]):
        if not self.create_table("hypervisors_pools"):
            rpools = r.table("hypervisors_pools")

            # self.result(rpools.delete().run(self.conn))
            cert = Certificates()
            viewer = cert.get_viewer()
            log.info("Table hypervisors_pools found, populating...")
            self.result(
                rpools.insert(
                    [
                        {
                            "id": "default",
                            "name": "Default",
                            "description": "",
                            "paths": {
                                "bases": [
                                    {
                                        "path": "/isard/bases",
                                        "disk_operations": [],
                                        "weight": 100,
                                    }
                                ],
                                "groups": [
                                    {
                                        "path": "/isard/groups",
                                        "disk_operations": [],
                                        "weight": 100,
                                    }
                                ],
                                "templates": [
                                    {
                                        "path": "/isard/templates",
                                        "disk_operations": [],
                                        "weight": 100,
                                    }
                                ],
                                "media": [
                                    {
                                        "path": "/isard/media",
                                        "disk_operations": [],
                                        "weight": 100,
                                    }
                                ],
                                "volatile": [
                                    {
                                        "path": "/isard/volatile",
                                        "disk_operations": [],
                                        "weight": 100,
                                    }
                                ],
                            },
                            "viewer": viewer,
                            "interfaces": [],
                            "cpu_host_model": "host-passthrough",
                            "allowed": {
                                "roles": [],
                                "categories": [],
                                "groups": [],
                                "users": [],
                            },
                        }
                    ],
                    conflict="update",
                ).run(self.conn)
            )
        return True

    """
    DOMAINS
    """

    def domains(self):
        self.create_table("domains")
        self.index_create(
            "domains", ["status", "hyp_started", "user", "group", "category", "kind"]
        )
        return True

    """
    DISK_OPERATIONS
    """

    def disk_operations(self):
        self.create_table("disk_operations")
        return True

    """
    HELPERS
    """

    def result(self, res):
        if res["errors"]:
            log.error(res["first_error"])
            exit(0)

    def _parseString(self, txt):
        import locale
        import re
        import unicodedata

        if type(txt) is not str:
            txt = txt.decode("utf-8")
        # locale.setlocale(locale.LC_ALL, 'ca_ES')
        prog = re.compile("[-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$")
        if not prog.match(txt):
            return False
        else:
            # ~ Replace accents
            txt = "".join(
                (
                    c
                    for c in unicodedata.normalize("NFD", txt)
                    if unicodedata.category(c) != "Mn"
                )
            )
            return txt.replace(" ", "_")

    def _hypervisor_viewer_hostname(self, viewer_hostname):
        hostname_file = "install/host_name"
        try:
            with open(hostname_file, "r") as hostFile:
                return hostFile.read().strip()
        except Exception as e:
            return viewer_hostname

        return

    """
    VIRT INSTALL
    """

    def virt_install(self):
        if not self.create_table("virt_install"):
            self.result(
                r.table("virt_install")
                .insert(self.update_virtinstalls())
                .run(self.conn)
            )
        return True

    def update_virtinstalls(self):
        from os import getcwd, path

        __location__ = path.realpath(path.join(getcwd(), path.dirname(__file__)))
        f = open("./initdb/default_xmls/osinfo.txt")
        data = f.read()
        f.close()

        installs = []
        for l in data.split("\n")[2:]:
            if l.find("|") > 1:
                v = [a.strip() for a in l.split("|")]
                xml = self.get_virtinstall_xml(v[0])
                if xml is not False:
                    icon = self.get_icon(v[1])
                    installs.append(
                        {
                            "id": v[0].strip(),
                            "name": v[1].strip(),
                            "vers": v[2].strip(),
                            "www": v[3].strip(),
                            "icon": icon,
                            "xml": xml,
                        }
                    )
        return installs

    def get_virtinstall_xml(self, id):
        from os import listdir
        from os.path import isfile, join

        try:
            f = open("./initdb/default_xmls/" + id + ".xml")
            data = f.read()
            f.close()
        except:
            return False
        return data

    def get_icon(self, name):
        osname = name.replace("®", "").split(" ")[0].lower()
        if "win" in osname:
            icon = "windows"
        elif "rhel" in osname or "rhl" in osname:
            icon = "redhat"
        elif "alt" in osname or "openbsd" in osname or "netbsd" in osname:
            icon = "linux"
        elif "suse" in osname:
            icon = "opensuse"
        else:
            icon = osname
        return icon

    """
    ENGINE
    """

    def engine(self):
        if not self.create_table("engine"):
            if r.table("engine").get("admin").run(self.conn) is None:
                self.result(
                    r.table("engine")
                    .insert(
                        [
                            {
                                "id": "engine",
                                "threads": {"changes": "on"},
                                "status_all_threads": "on",
                            }
                        ]
                    )
                    .run(self.conn)
                )

    def storage(self):
        self.create_table("storage")

    def storage_pool(self):
        self.create_table("storage_pool")

    def user_storage(self):
        self.create_table("user_storage")

    def index_create(self, table, indexes):
        indexes_ontable = r.table(table).index_list().run(self.conn)
        apply_indexes = [mi for mi in indexes if mi not in indexes_ontable]
        for i in apply_indexes:
            r.table(table).index_create(i).run(self.conn)
            r.table(table).index_wait(i).run(self.conn)

    ### disk_operations table not used anymore (delete if exists and remove creation)

    """ def enrollment_gen(self, length=6):
        chars = digits + ascii_lowercase
        dict = {}
        for key in ['manager','advanced','user']:
            code = False
            while code == False:
                code = "".join([random.choice(chars) for i in range(length)]) 
                if self.enrollment_code_check(code) == False:
                    dict[key]=code
                else:
                    code = False

        return dict  

    def enrollment_code_check(self, code):
        found=list(r.table('groups').filter({'enrollment':{'manager':code}}).run(self.conn))
        if len(found) > 0:
            category = found[0]['id'].split('_')[0]
            return {'code':code,'role':'manager', 'category':category, 'group':found[0]['id']}
        found=list(r.table('groups').filter({'enrollment':{'advanced':code}}).run(self.conn))
        if len(found) > 0:
            category = found[0]['id'].split('_')[0]
            return {'code':code,'role':'advanced', 'category':category, 'group':found[0]['id']}
        found=list(r.table('groups').filter({'enrollment':{'user':code}}).run(self.conn))
        if len(found) > 0:
            category = found[0]['id'].split('_')[0]
            return {'code':code,'role':'user', 'category':category, 'group':found[0]['id']}  
        return False """

    """ RESERVABLES & BOOKINGS"""

    def bookings(self):
        try:
            log.info("Table bookings not found, creating...")
            r.table_create("bookings", primary_key="id").run(self.conn)
        except:
            None
        try:
            self.index_create("bookings", ["item_id"])
        except:
            None
        try:
            r.table("bookings").index_create(
                "item_type-id",
                [r.row["item_type"], r.row["item_id"]],
            ).run(self.conn)
        except:
            None
        try:
            self.index_create("bookings", ["user_id"])
        except:
            None
        try:
            r.table("bookings").index_create(
                "reservables_vgpus", r.row["reservables"]["vgpus"]
            ).run(self.conn)
        except:
            None

    def bookings_resources(self):
        try:
            log.info("Table bookings_resources not found, creating...")
            r.table_create("bookings_resources", primary_key="id").run(self.conn)
        except:
            None

    def bookings_priority(self):
        try:
            log.info("Table bookings_priority not found, creating...")
            r.table_create("bookings_priority", primary_key="id").run(self.conn)
        except:
            None
        try:
            self.index_create("bookings_priority", ["rule_id"])
        except:
            None
        try:
            priority = [
                {
                    "id": "default",
                    "rule_id": "default",
                    "name": "default",
                    "description": "Applied to non matching users",
                    "allowed": {
                        "roles": [],
                        "categories": None,
                        "groups": None,
                        "users": None,
                    },
                    "priority": 1,
                    "forbid_time": 0,
                    "max_time": 60,
                    "max_items": 1,
                },
                {
                    "id": "default admins",
                    "rule_id": "default",
                    "name": "default admins",
                    "description": "Applied to all admin users",
                    "allowed": {
                        "roles": ["admin"],
                        "categories": None,
                        "groups": None,
                        "users": None,
                    },
                    "priority": 999,
                    "forbid_time": 1,
                    "max_time": 999999,
                    "max_items": 999999,
                },
            ]
            r.table("bookings_priority").insert(priority).run(self.conn)
        except:
            None

    def resource_planner(self):
        try:
            log.info("Table resource_planner not found, creating...")
            r.table_create("resource_planner", primary_key="id").run(self.conn)
        except:
            None
        try:
            self.index_create(
                "resource_planner", ["item_type", "item_id", "subitem_id", "start"]
            )
        except:
            None
        try:
            r.table("resource_planner").index_create(
                "default_order", [r.row["item_type"], r.row["item_id"], r.row["start"]]
            ).run(self.conn)
        except:
            None
        try:
            r.table("resource_planner").index_create(
                "type-item",
                [r.row["item_type"], r.row["item_id"]],
            ).run(self.conn)
        except:
            None
        try:
            r.table("resource_planner").index_create(
                "type-item-subitem",
                [r.row["item_type"], r.row["item_id"], r.row["subitem_id"]],
            ).run(self.conn)
        except:
            None
        try:
            r.table("resource_planner").index_create(
                "item-subitem",
                [r.row["item_id"], r.row["subitem_id"]],
            ).run(self.conn)
        except:
            None

    def gpu_profiles(self):
        ## List of gpus
        try:
            log.info("Table gpu_profiles not found, creating...")
            r.table_create("gpu_profiles", primary_key="id").run(self.conn)
        except:
            None
        try:
            r.table("gpu_profiles").index_create(
                "brand-model", [r.row["brand"], r.row["model"]]
            ).run(self.conn)
        except:
            None
        try:
            r.table("gpu_profiles").index_create(
                "brand-model-profile",
                [r.row["brand"], r.row["model"], r.row["profiles"]["profile"]],
            ).run(self.conn)
        except:
            None
        try:
            r.table("gpu_profiles").index_create(
                "profile", r.row["profiles"]["profile"]
            ).run(self.conn)
        except:
            None
        try:
            r.table("gpu_profiles").index_create(
                "profile_id", r.row["profiles"]["id"]
            ).run(self.conn)
        except:
            None
        try:
            self.index_create("gpu_profiles", ["brand", "model"])
        except:
            None

        f = open("./initdb/profiles/gpu_profiles.json")
        gpu_profiles = json.loads(f.read())
        f.close()
        r.table("gpu_profiles").insert(gpu_profiles, conflict="update").run(self.conn)

    def gpus(self):
        ## Gpus administrator activated in system
        try:
            log.info("Table gpus not found, creating...")
            r.table_create("gpus", primary_key="id").run(self.conn)
        except:
            None
        try:
            r.table("gpus").index_create(
                "brand-model", [r.row["brand"], r.row["model"]]
            ).run(self.conn)
        except:
            None
        try:
            self.index_create("gpus", ["brand", "model"])
        except:
            None

    def vgpus(self):
        ## Engine detected VGPUS
        try:
            log.info("Table vgpus not found, creating...")
            r.table_create("vgpus", primary_key="id").run(self.conn)
        except:
            None
        try:
            r.table("vgpus").index_create(
                "brand-model", [r.row["brand"], r.row["model"]]
            ).run(self.conn)
        except:
            None
        try:
            self.index_create("vgpus", ["brand", "model"])
        except:
            None

    def reservables_vgpus(self):
        try:
            log.info("Table reservables_vgpus not found, creating...")
            r.table_create("reservables_vgpus", primary_key="id").run(self.conn)
        except:
            None
        try:
            default_reservable_vgpu = {
                "allowed": {
                    "categories": False,
                    "groups": False,
                    "roles": [],
                    "users": False,
                },
                "brand": "None",
                "description": "None",
                "heads": 0,
                "id": "None",
                "model": "None",
                "name": "No GPU",
                "profile": "None",
                "ram": 0,
                "vram": 0,
                "units": 0,
            }
            r.table("reservables_vgpus").insert(
                default_reservable_vgpu, conflict="update"
            ).run(self.conn)
        except:
            None

    def desktops_priority(self):
        try:
            log.info("Table desktops_priority not found, creating...")
            r.table_create("desktops_priority", primary_key="id").run(self.conn)
        except:
            None
        try:
            priority = [
                {
                    "id": str(uuid.uuid4()),
                    "name": "default",
                    "op": "shutdown",
                    "description": "Applied to non matching users",
                    "allowed": {
                        "roles": [],  ## Matches all
                        "categories": False,
                        "groups": False,
                        "users": False,
                        "desktops": False,
                    },
                    "priority": 0,
                    "shutdown": False,
                    # {
                    #     "server": False,
                    #     "max": 240,
                    #     "notify_intervals": [{"time":0,"type":"info"}, {"time":-1,"type":"alert"},{"time":-2,"type":"warning"}],
                    # },
                },
            ]
            r.table("desktops_priority").insert(priority).run(self.conn)
        except:
            None

    def logs_desktops(self):
        try:
            log.info("Table logs_desktops not found, creating...")
            r.table_create("logs_desktops", primary_key="id").run(self.conn)
            r.table("logs_desktops").index_create("desktop_id").run(self.conn)
            r.table("logs_desktops").index_create("deployment_id").run(self.conn)
            r.table("logs_desktops").index_create("owner_user_id").run(self.conn)
            r.table("logs_desktops").index_create("owner_category_id").run(self.conn)
            r.table("logs_desktops").index_create("owner_group_id").run(self.conn)
            r.table("logs_desktops").index_create("started_by").run(self.conn)
            r.table("logs_desktops").index_create("stopped_by").run(self.conn)
            r.table("logs_desktops").index_create("started_time").run(self.conn)
            r.table("logs_desktops").index_create("stopped_time").run(self.conn)
            r.table("logs_desktops").index_create("stopped_status").run(self.conn)
            r.table("logs_desktops").index_create(
                "desktop_template_hierarchy",
                multi=True,
            ).run(self.conn)
        except:
            None

    def logs_users(self):
        try:
            log.info("Table logs_users not found, creating...")
            r.table_create("logs_users", primary_key="id").run(self.conn)
            r.table("logs_users").index_create("started_time").run(self.conn)
            r.table("logs_users").index_create("stopped_time").run(self.conn)
        except:
            None

    def usage_consumption(self):
        try:
            log.info("Table usage_consumption not found, creating...")
            r.table_create("usage_consumption", primary_key="pk").run(self.conn)
            r.table("usage_consumption").index_create("item_id").run(self.conn)
            r.table("usage_consumption").index_create("item_type").run(self.conn)
            r.table("usage_consumption").index_create("item_consumer").run(self.conn)

        except:
            None

    def usage_credit(self):
        # Credits per category and range start/end
        # Each entry will be related to a grouping and a limit
        # If no entry for the given category and range, None will
        try:
            log.info("Table usage_credit not found, creating...")
            r.table_create("usage_credit", primary_key="id").run(self.conn)
            r.table("usage_credit").index_create(
                "item_id-item_type-grouping",
                [r.row["item_id"], r.row["item_type"], r.row["grouping_id"]],
            ).run(self.conn)
        except:
            None

    def usage_parameter(self):
        try:
            log.info("Table usage_parameter not found, creating...")
            r.table_create("usage_parameter", primary_key="id").run(self.conn)
            r.table("usage_parameter").index_create(
                "custom_type", [r.row["custom"], r.row["item_type"]]
            ).run(self.conn)
            r.table("usage_parameter").insert(
                [  # DESKTOP PARAMETERS
                    {
                        "id": "dsk_starts",
                        "name": "Desktops started",
                        "desc": "Number of desktops started",
                        "units": "",
                        "item_type": "desktop",
                        "custom": False,
                        "default": 0,
                        "formula": None,
                    },
                    {
                        "id": "dsk_hours",
                        "name": "Desktop hours",
                        "desc": "Number of desktop hours used",
                        "units": "Desktop/hour",
                        "item_type": "desktop",
                        "custom": False,
                        "default": 0,
                        "formula": None,
                    },
                    {
                        "id": "dsk_gpu_mem",
                        "name": "GPU desktop memory",
                        "desc": "GPU desktop memory per hour",
                        "units": "MB/hour",
                        "item_type": "desktop",
                        "custom": False,
                        "default": 0,
                        "formula": None,
                    },
                    {
                        "id": "dsk_gpu_hours",
                        "name": "GPU hours",
                        "desc": "Number of GPU desktop hours used",
                        "units": "GPU/hour",
                        "item_type": "desktop",
                        "custom": False,
                        "default": 0,
                        "formula": None,
                    },
                    {
                        "id": "dsk_vcpus",
                        "name": "Desktop vCPUs",
                        "desc": "Desktop vCPUs per hour",
                        "units": "vCPU/hour",
                        "item_type": "desktop",
                        "custom": False,
                        "default": 0,
                        "formula": None,
                    },
                    {
                        "id": "dsk_mem",
                        "name": "Desktop memory",
                        "desc": "Desktop memory per hour",
                        "units": "MB/hour",
                        "item_type": "desktop",
                        "custom": False,
                        "default": 0,
                        "formula": None,
                    },  # STORAGE PARAMETERS
                    {
                        "id": "str_size",
                        "name": "Storage size",
                        "desc": "Storage size",
                        "units": "GB",
                        "item_type": "storage",
                        "custom": False,
                        "default": 0,
                        "formula": None,
                    },
                    {
                        "id": "str_created",
                        "name": "Storage created",
                        "desc": "Storage created",
                        "units": "",
                        "item_type": "storage",
                        "custom": False,
                        "default": 0,
                        "formula": None,
                    },  # MEDIA PARAMETERS
                    {
                        "id": "mda_created",
                        "name": "Media created",
                        "desc": "Number of media created",
                        "units": "",
                        "item_type": "media",
                        "custom": False,
                        "default": 0,
                        "formula": None,
                    },
                    {
                        "id": "mda_size",
                        "name": "Media size",
                        "desc": "Media size",
                        "units": "GB",
                        "item_type": "media",
                        "custom": False,
                        "default": 0,
                        "formula": None,
                    },  # USER PARAMETERS
                    {
                        "id": "usr_created",
                        "name": "Users created",
                        "desc": "Number of users created",
                        "units": "",
                        "item_type": "user",
                        "custom": False,
                        "default": 0,
                        "formula": None,
                    },
                    {
                        "id": "usr_hours",
                        "name": "User hours",
                        "desc": "Number of user hours used",
                        "units": "User/hour",
                        "item_type": "user",
                        "custom": False,
                        "default": 0,
                        "formula": None,
                    },
                    {
                        "id": "usr_active",
                        "name": "Users active",
                        "desc": "Number of users active",
                        "units": "",
                        "item_type": "user",
                        "custom": False,
                        "default": 0,
                        "formula": None,
                    },  # CUSTOM PARAMETERS
                    {
                        "id": "DHN",
                        "name": "Desktop hours normalized",
                        "desc": "vCPU normalized to 4th and memory to 6GB. It weights more for memory than vcpus.",
                        "units": "DH/N",
                        "item_type": "desktop",
                        "custom": True,
                        "default": 0,
                        "formula": "0.2 * dsk_vcpus / 4 + 0.8 * dsk_mem / 6",
                    },
                ]
            ).run(self.conn)
        except:
            None

    def usage_grouping(self):
        try:
            log.info("Table usage_grouping not found, creating...")
            r.table_create("usage_grouping", primary_key="id").run(self.conn)
        except:
            None

    def usage_limit(self):
        try:
            log.info("Table usage_limit not found, creating...")
            r.table_create("usage_limit", primary_key="id").run(self.conn)
        except Exception as e:
            log.error(e)
            None

    def usage_reset_dates(self):
        try:
            log.info("Table usage_reset_dates not found, creating...")
            r.table_create("usage_reset_dates", primary_key="id").run(self.conn)
        except Exception as e:
            log.error(e)

    def recycle_bin(self):
        try:
            log.info("Table recycle_bin not found, creating...")
            r.table_create("recycle_bin", primary_key="id").run(self.conn)
        except:
            None

    """
    AUTHENTICATION POLICIES
    """

    def authentication(self):
        try:
            log.info("Table authentication not found, creating...")
            r.table_create("authentication", primary_key="id").run(self.conn)
            self.index_create("authentication", ["type"])
            self.index_create("authentication", ["subtype"])
            self.index_create("authentication", ["provider"])

            r.table("authentication").index_create(
                "category-role-subtype",
                [r.row["category"], r.row["role"], r.row["subtype"]],
            ).run(self.conn)
            r.table("authentication").index_create(
                "type-subtype",
                [r.row["type"], r.row["subtype"]],
            ).run(self.conn)

            r.table("authentication").insert(
                [
                    {
                        "type": "local",  # provider
                        "category": "all",
                        "role": "all",
                        "subtype": "password",  # policy kind
                        "digits": 0,
                        "length": 8,
                        "lowercase": 0,
                        "uppercase": 0,
                        "special_characters": 0,
                        "not_username": False,
                        "expire": 0,
                        "old_passwords": 0,
                    },
                ]
            ).run(self.conn)
        except Exception as e:
            log.error(e)

    """
    ANALYTICS
    """

    def analytics(self):
        try:
            log.info("Table analytics not found, creating...")
            r.table_create("analytics", primary_key="id").run(self.conn)
        except Exception as e:
            log.error(e)

    """
    NOTIFICATION TEMPLATES
    """

    def notification_tmpls(self):
        try:
            log.info("Table notification_tmpls not found, creating...")
            r.table_create("notification_tmpls", primary_key="id").run(self.conn)
            # self.index_create("notification_tmpls", ["kind"])

            r.table("notification_tmpls").insert(
                [
                    {
                        "name": "Email verification",
                        "description": "Email verification that will be sent when user logs in for the first time and/or admin forces email verification at new logins",
                        "kind": "email",
                        "vars": {
                            "email": "your@domain.com",
                            "user_id": "jdoe",
                            "user_name": "John Doe",
                            "url": "https://your.domain.com/email_verify/1234567890",
                        },
                        "default": "system",
                        "system": {
                            "title": "Verify IsardVDI email",
                            "body": """<p>Please verify your email address by clicking on the following button:</p>\n<a href="{url}" class="btn btn-primary">Verify email</a>\n<p>This button can only be used once and it's valid for 1 hour.</p>""",
                            "footer": "Please do not answer since this email has been automatically generated.",
                        },
                        "lang": {
                            "en": {
                                "title": "Verify IsardVDI email",
                                "body": """<p>Please verify your email address by clicking on the following button:</p>\n<a href="{url}" class="btn btn-primary">Verify email</a>\n<p>This button can only be used once and it's valid for 1 hour.</p>""",
                                "footer": "Please do not answer since this email has been automatically generated.",
                            },
                            "es": {
                                "title": "Verificación del correo electrónico de IsardVDI",
                                "body": """<p>Verifique su dirección de correo electrónico haciendo clic en el siguiente botón:</p>\n<a href="{url}" class="btn btn-primary">Verificar correo</a>\n<p>Este botón solo se puede usar una vez y es válido durante 1 hora.</p>""",
                                "footer": "Por favor, no responda a este correo electrónico, ya que es un envío automático.",
                            },
                            "ca": {
                                "title": "Verifica el correu electrònic IsardVDI",
                                "body": """<p>Si us plau, confirmeu la vostra adreça electrònica clicant al següent botó:</p><a href='{url}' class='btn btn-primary'>Verifica el correu electrònic</a><p>Aquest botó només es pot utilitzar una vegada i té una validesa de 1 hora.</p>""",
                                "footer": "Si us plau, no respongueu a aquest correu electrònic, ja que ha estat generat automàticament.",
                            },
                        },
                    },
                    {
                        "name": "Password recovery",
                        "description": "Password recovery message that will be sent when user requests password recovery",
                        "kind": "password",
                        "vars": {
                            "user_name": "John Doe",
                            "user_id": "jdoe",
                            "url": "https://your.domain.com/password_recovery/1234567890",
                        },
                        "default": "system",
                        "system": {
                            "title": "Reset IsardVDI password",
                            "body": """<p>We've received your password reset request to access IsardVDI. Click on the following button to set a new password:</p>\n<a href="{url}" class="btn btn-primary">Set password</a>\n<p>This button can only be used once and it's valid for 24 hours.</p><p>If you did not initiate this request, you may safely ignore this message.</p>""",
                            "footer": "Please do not answer since this email has been automatically generated.",
                        },
                        "lang": {
                            "en": {
                                "title": "Reset IsardVDI password",
                                "body": """<p>We've received your password reset request to access IsardVDI. Click on the following button to set a new password:</p>\n<a href="{url}" class="btn btn-primary">Set password</a>\n<p>This button can only be used once and it's valid for 24 hours.</p><p>If you did not initiate this request, you may safely ignore this message.</p>""",
                                "footer": "Please do not answer since this email has been automatically generated.",
                            },
                            "es": {
                                "title": "Restablecer contraseña de IsardVDI",
                                "body": """<p>Hemos recibido su solicitud de restablecimiento de contraseña para acceder a IsardVDI. Haga clic en el siguiente botón para establecer una nueva contraseña:</p>\n<a href="{url}" class="btn btn-primary">Configurar contraseña</a>\n<p>Este botón solo se puede usar una vez y es válido durante 24 horas.</p><p>Si no inició esta solicitud, puede ignorar este mensaje.</p>""",
                                "footer": "Por favor, no responda a este correo electrónico, ya que es un envío automático.",
                            },
                            "ca": {
                                "title": "Restableix la contrasenya IsardVDI",
                                "body": "<p>Hem rebut la vostra sol·licitud de restabliment de contrasenya per accedir a IsardVDI. Si us plau, cliqueu al següent botó per establir una nova contrasenya:</p><a href='{url}' class='btn btn-primary'>Estableix la contrasenya</a><p>Aquest botó només es pot utilitzar una vegada i té una validesa de 24 hores.</p><p>Si no heu iniciat aquesta sol·licitud, podeu ignorar aquest missatge.</p>",
                                "footer": "Si us plau, no respongueu a aquest correu electrònic, ja que ha estat generat automàticament.",
                            },
                        },
                    },
                ]
            ).run(self.conn)
        except Exception as e:
            log.error(e)

    """
    NOTIFICATIONS
    """

    def notifications(self):
        try:
            log.info("Table notifications not found, creating...")
            r.table_create("notifications", primary_key="id").run(self.conn)
            r.table("notifications").index_create(
                "trigger_enabled",
                [r.row["trigger"], r.row["enabled"]],
            ).run(self.conn)
            r.table("notifications").index_create("action_id").run(self.conn)
            r.table("notifications").insert(
                [
                    {
                        "name": "User unused desktops have been sent to the recycle bin",
                        "action_id": "unused_desktops",
                        "allowed": {
                            "roles": False,
                            "categories": False,
                            "groups": False,
                            "users": False,
                        },
                        "trigger": "login",
                        "item_type": "desktop",
                        "template_id": "",
                        "display": ["fullpage"],
                        "order": 0,
                        "force_accept": False,
                        "enabled": False,
                        "ignore_after": r.epoch_time(
                            0
                        ),  # Defines the time the notification data will be ignored. In this case it will be specified in each notification_data entry
                        "keep_time": 0,  # Defines the amount of hours the notification data will be kept
                    }
                ]
            ).run(self.conn)
        except Exception as e:
            log.error(e)

    def notifications_data(self):
        try:
            log.info("Table notifications_data not found, creating...")
            r.table_create("notifications_data", primary_key="id").run(self.conn)
            r.table("notifications_data").index_create("notification_id").run(self.conn)
            r.table("notifications_data").index_create(
                "user_id_status_notification_id",
                [r.row["user_id"], r.row["status"], r.row["notification_id"]],
            ).run(self.conn)
            r.table("notifications_data").index_create("user_id").run(self.conn)
        except Exception as e:
            log.error(e)

    def notifications_action(self):
        try:
            log.info("Table notifications_action not found, creating...")
            r.table_create("notifications_action", primary_key="id").run(self.conn)
            r.table("notifications_action").insert(
                [
                    {
                        "description": "Unused desktops are automatically recycled by the system",
                        "id": "unused_desktops",
                        "kwargs": ["name", "accessed"],
                        "compute": None,
                    },
                    {
                        "description": "The owner hasn't shut down the desktops",
                        "id": "shutdown",
                        "kwargs": ["name"],
                        "compute": None,
                    },
                    {
                        "description": "Custom",
                        "id": "custom",
                        "kwargs": [],
                        "compute": None,
                    },
                ]
            ).run(self.conn)
        except Exception as e:
            log.error(e)

    """
    SYSTEM EVENTS
    """

    def system_events(self):
        try:
            log.info("Table system_events not found, creating...")
            r.table_create("system_events", primary_key="id").run(self.conn)
            templates = list(
                r.table("notification_tmpls").pluck("id", "kind").run(self.conn)
            )
            r.table("system_events").insert(
                [
                    {
                        "event": "email-verify",
                        "tmpl_id": [
                            template["id"]
                            for template in templates
                            if template["kind"] == "email"
                        ][0],
                        "channels": ["mail"],
                    },
                    {
                        "event": "password-reset",
                        "tmpl_id": [
                            template["id"]
                            for template in templates
                            if template["kind"] == "password"
                        ][0],
                        "channels": ["mail"],
                    },
                ]
            ).run(self.conn)
        except Exception as e:
            log.error(e)

    """
    TARGETS
    """

    def targets(self):
        try:
            log.info("Table targets not found, creating...")
            r.table_create("targets", primary_key="id").run(self.conn)
            r.table("targets").index_create("desktop_id").run(self.conn)
            r.table("targets").index_create("user_id").run(self.conn)
        except Exception as e:
            log.error(e)

    """
    RECYCLE BIN ARCHIVE
    """

    # def recycle_bin_archive(self):
    #     try:
    #         log.info("Table recycle_bin_archive not found, creating...")
    #         r.table_create("recycle_bin_archive", primary_key="id").run(self.conn)
    #     except Exception as e:
    #         log.error(e)

    """
    USERS MIGRATIONS
    """

    def users_migrations(self):
        try:
            log.info("Table users_migrations not found, creating...")
            r.table_create("users_migrations", primary_key="id").run(self.conn)
        except Exception as e:
            log.error(e)
        try:
            r.table("users_migrations").index_create("token").run(self.conn)
        except Exception as e:
            log.error(e)
        try:
            r.table("users_migrations").index_create("status").run(self.conn)
        except Exception as e:
            log.error(e)
        try:
            r.table("users_migrations").index_create("origin_user").run(self.conn)
        except Exception as e:
            log.error(e)
        try:
            r.table("users_migrations").index_create("target_user").run(self.conn)
        except Exception as e:
            log.error(e)

    """
    USERS_MIGRATIONS_EXCEPTIONS
    """

    def users_migrations_exceptions(self):
        try:
            log.info("Table users_migrations_exceptions not found, creating...")
            r.table_create("users_migrations_exceptions", primary_key="id").run(
                self.conn
            )
            r.table("users_migrations_exceptions").index_create("item_id").run(
                self.conn
            )
            r.table("users_migrations_exceptions").insert(
                {
                    "created_at": r.now(),
                    "item_id": "admin",
                    "item_type": "roles",
                }
            ).run(self.conn)
        except Exception as e:
            log.error(e)
