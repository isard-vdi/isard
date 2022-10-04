# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

# !/usr/bin/env python
# coding=utf-8

import sys
import time

import requests
import rethinkdb as r

from .lib import *
from .log import *

""" 
Update to new database release version when new code version release
"""
release_version = 59

# release 59: Remove whitespaces in uids and usernames
# release 58: Add new field 'virtualization_nested' into every created domain
# release 57: Addded serverstostart index to domains
# release 56: Remove hyp_started from non started domains
# release 55: Added more secondary indices for domains queries
# release 54: Add status time info to storage disks
# release 53: Add secondary_groups users multi index
# release 52: Add sortorder field to roles table
# release 51: Add support for external apps
# release 50: Added secondary indices for domains and users tables
# release 49: Replace dots in media ids
# release 48: Replace bookings_priority table null value to false
# release 47: resolve parent error in storage table for templates
# release 46: Upgraded users secondary_groups field
# release 45: Remove physical storage domains and media data to use uuid as id
# release 44: Added type index to scheduler_jobs
# release 43: Added media_ids domains index
# release 42: Added disk_paths and storage_ids domains index
# release 41: Added user_id and status indexes to storage table
# release 40: Added linked groups to groups
# release 39: Added secondary groups to users
# release 38: Replace create_dict diskbus to disk_bus
# release 37: Fix upgrade bug in version 36
# release 36: Fix typo VLC for VNC
# release 35: Fix media with missing owner
# release 34: Fix missing media upload roles and categories keys
# release 33: Fix missing media upload roles and categories keys
# release 32: Remove reservables bug when updating desktop
# release 31: Removed all nvidia video types and added none type
# release 30: Moved domain options to guest_properties
# release 29: Add volatile path to hypervisors_pools
# release 28: Added jumperurl token index in domains table
# release 27: Fix interface qos_id value from false to "unlimited"
# release 26: Added a parents index to domains
# release 25: Replaced user_template/public_template/base to template
# release 24: Add missing domains created from qcow2 media disk image field
# release 23: Added enabled to templates
# release 22: Upgrade domains image field
# release 21: Added secondary wg_client_ip index to users.
#             Added secondary wg_client_ip index to remotevpn
# release 20: forced_hyp should be a list if not False
# release 19: Update hypervisors_pools based on actual hypervisors in db
# release 18: Replace deployment id # to = (and also to domains)
# release 16: Added secondary wg_mac index to domains

tables = [
    "config",
    "hypervisors",
    "hypervisors_pools",
    "domains",
    "media",
    "videos",
    "graphics",
    "users",
    "roles",
    "groups",
    "interfaces",
    "deployments",
    "remotevpn",
    "storage",
    "storage_physical_domains",
    "storage_physical_media",
    "scheduler_jobs",
    "bookings_priority",
]


class Upgrade(object):
    def __init__(self):
        cfg = loadConfig()
        self.conf = cfg.cfg()

        self.conn = False
        self.cfg = False
        try:
            self.conn = r.connect(
                self.conf["RETHINKDB_HOST"],
                self.conf["RETHINKDB_PORT"],
                self.conf["RETHINKDB_DB"],
            ).repl()
        except Exception as e:
            log.error(
                "Database not reacheable at "
                + self.conf["RETHINKDB_HOST"]
                + ":"
                + self.conf["RETHINKDB_PORT"]
            )
            sys.exit()

        if self.conn is not False and r.db_list().contains(
            self.conf["RETHINKDB_DB"]
        ).run(self.conn):
            if r.table_list().contains("config").run(self.conn):
                ready = False
                while not ready:
                    try:
                        self.cfg = r.table("config").get(1).run(self.conn)
                        ready = True
                    except Exception as e:
                        log.info("Waiting for database to be ready...")
                        time.sleep(1)
                log.info("Your actual database version is: " + str(self.cfg["version"]))
                if release_version > self.cfg["version"]:
                    log.warning(
                        "Database upgrade needed! You have version "
                        + str(self.cfg["version"])
                        + " and source code is for version "
                        + str(release_version)
                        + "!!"
                    )
                else:
                    log.info("No database upgrade needed.")
        self.upgrade_if_needed()

    def do_backup(self):
        None

    def upgrade_if_needed(self):

        print(release_version)
        print(self.cfg["version"])
        if not release_version > self.cfg["version"]:
            return False
        apply_upgrades = [
            i for i in range(self.cfg["version"] + 1, release_version + 1)
        ]
        log.info("Now will upgrade database versions: " + str(apply_upgrades))
        for version in apply_upgrades:
            for table in tables:
                eval("self." + table + "(" + str(version) + ")")

        r.table("config").get(1).update({"version": release_version}).run(self.conn)

    """
    CONFIG TABLE UPGRADES
    """

    def config(self, version):
        table = "config"
        d = r.table(table).get(1).run(self.conn)
        log.info("UPGRADING " + table + " TABLE TO VERSION " + str(version))
        if version == 1:

            """CONVERSION FIELDS PRE CHECKS"""
            try:
                if not self.check_done(d, ["grafana"], [["engine", "carbon"]]):
                    ##### CONVERSION FIELDS
                    cfg["grafana"] = {
                        "active": d["engine"]["carbon"]["active"],
                        "url": d["engine"]["carbon"]["server"],
                        "web_port": 80,
                        "carbon_port": d["engine"]["carbon"]["port"],
                        "graphite_port": 3000,
                    }
                    r.table(table).update(cfg).run(self.conn)
            except Exception as e:
                log.error(
                    "Could not update table "
                    + table
                    + " conversion fields for db version "
                    + str(version)
                    + "!"
                )
                log.error("Error detail: " + str(e))

            """ NEW FIELDS PRE CHECKS """
            try:
                if not self.check_done(
                    d, ["resources", "voucher_access", ["engine", "api", "token"]], []
                ):
                    ##### NEW FIELDS
                    self.add_keys(
                        table,
                        [
                            {
                                "resources": {
                                    "code": False,
                                    "url": "http://www.isardvdi.com:5050",
                                }
                            },
                            {"voucher_access": {"active": False}},
                            {
                                "engine": {
                                    "api": {
                                        "token": "fosdem",
                                        "url": "http://isard-engine",
                                        "web_port": 5555,
                                    }
                                }
                            },
                        ],
                    )
            except Exception as e:
                log.error(
                    "Could not update table "
                    + table
                    + " new fields for db version "
                    + str(version)
                    + "!"
                )
                log.error("Error detail: " + str(e))

            """ REMOVE FIELDS PRE CHECKS """
            try:
                if not self.check_done(d, [], [["engine", "carbon"]]):
                    #### REMOVE FIELDS
                    self.del_keys(table, [{"engine": {"carbon"}}])
            except Exception as e:
                log.error(
                    "Could not update table "
                    + table
                    + " remove fields for db version "
                    + str(version)
                    + "!"
                )
                log.error("Error detail: " + str(e))

        if version == 5:
            d["engine"]["log"]["log_level"] = "WARNING"
            r.table(table).update(d).run(self.conn)

        if version == 6:

            """CONVERSION FIELDS PRE CHECKS"""
            try:
                url = d["engine"]["grafana"]["url"]
            except:
                url = ""
            try:
                if not self.check_done(d, [], ["engine"]):
                    ##### CONVERSION FIELDS
                    d["engine"]["grafana"] = {
                        "active": False,
                        "carbon_port": 2004,
                        "interval": 5,
                        "hostname": "isard-grafana",
                        "url": url,
                    }
                    r.table(table).update(d).run(self.conn)
            except Exception as e:
                log.error(
                    "Could not update table "
                    + table
                    + " conversion fields for db version "
                    + str(version)
                    + "!"
                )
                log.error("Error detail: " + str(e))

            # ~ ''' NEW FIELDS PRE CHECKS '''
            # ~ try:
            # ~ if not self.check_done( d,
            # ~ ['resources','voucher_access',['engine','api','token']],
            # ~ []):
            # ~ ##### NEW FIELDS
            # ~ self.add_keys(table, [
            # ~ {'resources':  {    'code':False,
            # ~ 'url':'http://www.isardvdi.com:5050'}},
            # ~ {'voucher_access':{'active':False}},
            # ~ {'engine':{'api':{  "token": "fosdem",
            # ~ "url": 'http://isard-engine',
            # ~ "web_port": 5555}}}])
            # ~ except Exception as e:
            # ~ log.error('Could not update table '+table+' new fields for db version '+str(version)+'!')
            # ~ log.error('Error detail: '+str(e))

            """ REMOVE FIELDS PRE CHECKS """
            try:
                if not self.check_done(d, [], ["grafana"]):
                    #### REMOVE FIELDS
                    self.del_keys(table, ["grafana"])
            except Exception as e:
                log.error(
                    "Could not update table "
                    + table
                    + " remove fields for db version "
                    + str(version)
                    + "!"
                )
                log.error("Error detail: " + str(e))

        if version == 10:
            try:
                d["resources"]["url"] = "https://repository.isardvdi.com"
                r.table(table).update(d).run(self.conn)
            except Exception as e:
                log.error(
                    "Could not update table "
                    + table
                    + " conversion fields for db version "
                    + str(version)
                    + "!"
                )
                log.error("Error detail: " + str(e))

        return True

    """
    HYPERVISORS TABLE UPGRADES
    """

    def hypervisors(self, version):
        table = "hypervisors"
        data = list(r.table(table).run(self.conn))
        log.info("UPGRADING " + table + " VERSION " + str(version))
        if version == 1:
            for d in data:
                id = d["id"]
                d.pop("id", None)

                """ CONVERSION FIELDS PRE CHECKS """
                # ~ try:
                # ~ if not self.check_done( d,
                # ~ [],
                # ~ []):
                ##### CONVERSION FIELDS
                # ~ cfg['field']={}
                # ~ r.table(table).update(cfg).run(self.conn)
                # ~ except Exception as e:
                # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
                # ~ log.error('Error detail: '+str(e))

                """ NEW FIELDS PRE CHECKS """
                try:
                    if not self.check_done(
                        d, ["viewer_hostname", "viewer_nat_hostname"], []
                    ):
                        ##### NEW FIELDS
                        self.add_keys(
                            table,
                            [
                                {"viewer_hostname": d["hostname"]},
                                {"viewer_nat_hostname": d["hostname"]},
                            ],
                            id=id,
                        )
                except Exception as e:
                    log.error(
                        "Could not update table "
                        + table
                        + " remove fields for db version "
                        + str(version)
                        + "!"
                    )
                    log.error("Error detail: " + str(e))

                """ REMOVE FIELDS PRE CHECKS """
                # ~ try:
                # ~ if not self.check_done( d,
                # ~ [],
                # ~ []):
                #### REMOVE FIELDS
                # ~ self.del_keys(TABLE,[])
                # ~ except Exception as e:
                # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
                # ~ log.error('Error detail: '+str(e))

        if version == 2:
            for d in data:
                id = d["id"]
                d.pop("id", None)

                """ CONVERSION FIELDS PRE CHECKS """
                # ~ try:
                # ~ if not self.check_done( d,
                # ~ [],
                # ~ []):
                ##### CONVERSION FIELDS
                # ~ cfg['field']={}
                # ~ r.table(table).update(cfg).run(self.conn)
                # ~ except Exception as e:
                # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
                # ~ log.error('Error detail: '+str(e))

                """ NEW FIELDS PRE CHECKS """
                try:
                    if not self.check_done(d, ["viewer_nat_offset"], []):
                        ##### NEW FIELDS
                        self.add_keys(table, [{"viewer_nat_offset": 0}], id=id)
                except Exception as e:
                    log.error(
                        "Could not update table "
                        + table
                        + " add fields for db version "
                        + str(version)
                        + "!"
                    )
                    log.error("Error detail: " + str(e))

                """ REMOVE FIELDS PRE CHECKS """
                # ~ try:
                # ~ if not self.check_done( d,
                # ~ [],
                # ~ []):
                #### REMOVE FIELDS
                # ~ self.del_keys(TABLE,[])
                # ~ except Exception as e:
                # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
                # ~ log.error('Error detail: '+str(e))

        if version == 8:
            for d in data:
                id = d["id"]
                d.pop("id", None)

                """ CONVERSION FIELDS PRE CHECKS """
                # ~ try:
                # ~ if not self.check_done( d,
                # ~ [],
                # ~ []):
                ##### CONVERSION FIELDS
                # ~ cfg['field']={}
                # ~ r.table(table).update(cfg).run(self.conn)
                # ~ except Exception as e:
                # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
                # ~ log.error('Error detail: '+str(e))

                """ NEW FIELDS PRE CHECKS """
                try:
                    if not self.check_done(d, ["viewer"], []):
                        ##### NEW FIELDS
                        self.add_keys(
                            table,
                            [
                                {
                                    "viewer": {
                                        "static": d["viewer_hostname"],
                                        "proxy_video": d["viewer_hostname"],
                                        "proxy_hyper_host": d["hostname"],
                                    }
                                }
                            ],
                            id=id,
                        )
                except Exception as e:
                    log.error(
                        "Could not update table "
                        + table
                        + " add fields for db version "
                        + str(version)
                        + "!"
                    )
                    log.error("Error detail: " + str(e))

                """ REMOVE FIELDS PRE CHECKS """
                try:
                    if not self.check_done(
                        d,
                        [],
                        ["viewer_hostname", "viewer_nat_hostname", "viewer_nat_offset"],
                    ):
                        # ~ #### REMOVE FIELDS
                        self.del_keys(
                            table,
                            [
                                "viewer_hostname",
                                "viewer_nat_hostname",
                                "viewer_nat_offset",
                            ],
                        )
                        # ~ self.del_keys(TABLE,['viewer_hostname'])
                        # ~ self.del_keys(TABLE,['viewer_nat_hostname'])
                        # ~ self.del_keys(TABLE,['viewer_nat_offset'])
                except Exception as e:
                    log.error(
                        "Could not update table "
                        + table
                        + " remove fields for db version "
                        + str(version)
                        + "!"
                    )
                    log.error("Error detail: " + str(e))

        if version == 11:
            for d in data:
                id = d["id"]
                d.pop("id", None)

                """ CONVERSION FIELDS PRE CHECKS """
                # ~ try:
                # ~ if not self.check_done( d,
                # ~ [],
                # ~ []):
                ##### CONVERSION FIELDS
                # ~ cfg['field']={}
                # ~ r.table(table).update(cfg).run(self.conn)
                # ~ except Exception as e:
                # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
                # ~ log.error('Error detail: '+str(e))

                """ NEW FIELDS PRE CHECKS """
                try:
                    if id == "isard-hypervisor":
                        if not self.check_done(d, ["hypervisor_number"], []):
                            ##### NEW FIELDS
                            self.add_keys(table, [{"hypervisor_number": 0}], id=id)
                except Exception as e:
                    log.error(
                        "Could not update table "
                        + table
                        + " add fields for db version "
                        + str(version)
                        + "!"
                    )
                    log.error("Error detail: " + str(e))

                """ REMOVE FIELDS PRE CHECKS """

        if version == 13:
            for d in data:
                id = d["id"]
                d.pop("id", None)

                """ CONVERSION FIELDS PRE CHECKS """
                # ~ try:
                # ~ if not self.check_done( d,
                # ~ [],
                # ~ []):
                ##### CONVERSION FIELDS
                # ~ cfg['field']={}
                # ~ r.table(table).update(cfg).run(self.conn)
                # ~ except Exception as e:
                # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
                # ~ log.error('Error detail: '+str(e))

                """ NEW FIELDS PRE CHECKS """
                try:
                    if not self.check_done(d, [], [{"viewer": {"html5_ext_port"}}]):
                        ##### NEW FIELDS
                        self.add_keys(
                            table,
                            [
                                {
                                    "viewer": {
                                        "html5_ext_port": "443",
                                        "spice_ext_port": "80",
                                    }
                                }
                            ],
                            id=id,
                        )
                except Exception as e:
                    log.error(
                        "Could not update table "
                        + table
                        + " add fields for db version "
                        + str(version)
                        + "!"
                    )
                    log.error("Error detail: " + str(e))

                """ REMOVE FIELDS PRE CHECKS """

        if version == 21:
            try:
                r.table(table).index_create(
                    "wg_client_ip", r.row["vpn"]["wireguard"]["Address"]
                ).run(self.conn)
            except:
                log.error(
                    "Could not update table "
                    + table
                    + " index creation for db version "
                    + str(version)
                    + "!"
                )
                log.error("Error detail: " + str(e))

        return True

    """
    HYPERVISORS_POOLS TABLE UPGRADES
    """

    def _hypervisors_with_disk_operations_in_pool(self, hypervisor_pool):
        hypervisors = [
            hypervisor
            for hypervisor in r.table("hypervisors")
            .pluck("id", "hypervisors_pools", {"capabilities": "disk_operations"})
            .run(self.conn)
            if hypervisor["capabilities"]["disk_operations"]
        ]
        return [
            hypervisor["id"]
            for hypervisor in hypervisors
            if hypervisor_pool["id"] in hypervisor["hypervisors_pools"]
        ]

    def hypervisors_pools(self, version):
        table = "hypervisors_pools"
        data = list(r.table(table).run(self.conn))
        log.info("UPGRADING " + table + " VERSION " + str(version))
        if version == 1 or version == 3:
            for d in data:
                id = d["id"]
                d.pop("id", None)
                try:
                    """CONVERSION FIELDS PRE CHECKS"""
                    # ~ if not self.check_done( d,

                    # ~ [],
                    # ~ []):
                    ##### CONVERSION FIELDS
                    # ~ cfg['field']={}
                    # ~ r.table(table).update(cfg).run(self.conn)

                    """ NEW FIELDS PRE CHECKS """
                    if not self.check_done(d, [["paths", "media"]], []):
                        ##### NEW FIELDS
                        media = d["paths"]["groups"]  # .copy()
                        # ~ print(media)
                        medialist = []
                        for m in media:
                            m["path"] = m["path"].split("groups")[0] + "media"
                            medialist.append(m)
                        d["paths"]["media"] = medialist
                        self.add_keys(table, [{"paths": d["paths"]}], id=id)

                    """ REMOVE FIELDS PRE CHECKS """
                    if not self.check_done(d, [], [["paths", "isos"]]):
                        #### REMOVE FIELDS
                        self.del_keys(table, [{"paths": {"isos"}}])

                except Exception as e:
                    log.error("Something went wrong while upgrading hypervisors!")
                    log.error(e)
                    exit(1)

        if version == 4:
            for d in data:
                id = d["id"]
                d.pop("id", None)
                try:
                    """CONVERSION FIELDS PRE CHECKS"""
                    # ~ if not self.check_done( d,
                    # ~ [],
                    # ~ []):
                    ##### CONVERSION FIELDS
                    # ~ cfg['field']={}
                    # ~ r.table(table).update(cfg).run(self.conn)

                    """ NEW FIELDS PRE CHECKS """
                    if not self.check_done(d, [["cpu_host_model"]], []):
                        ##### NEW FIELDS
                        self.add_keys(table, [{"cpu_host_model": "host-model"}], id=id)

                    # ''' REMOVE FIELDS PRE CHECKS '''
                    # if not self.check_done(d,
                    #                        [],
                    #                        [['paths', 'isos']]):
                    #     #### REMOVE FIELDS
                    #     self.del_keys(table, [{'paths': {'isos'}}])

                except Exception as e:
                    log.error("Something went wrong while upgrading hypervisors!")
                    log.error(e)
                    exit(1)

        if version == 19:
            pools = list(r.table("hypervisors_pools").run(self.conn))

            for hp in pools:
                hypervisors_in_pool = self._hypervisors_with_disk_operations_in_pool(hp)
                paths = hp["paths"]
                for p in paths:
                    for i, item in enumerate(paths[p]):
                        paths[p][i]["disk_operations"] = hypervisors_in_pool
                r.table("hypervisors_pools").get(hp["id"]).update(
                    {"paths": paths, "enabled": False}
                ).run(self.conn)

        if version == 29:
            for hypervisor_pool in r.table("hypervisors_pools").run(self.conn):
                hypervisors_in_pool = self._hypervisors_with_disk_operations_in_pool(
                    hypervisor_pool
                )
                r.table("hypervisors_pools").get(hypervisor_pool["id"]).update(
                    {
                        "paths": {
                            "volatile": [
                                {
                                    "path": "/isard/volatile",
                                    "disk_operations": hypervisors_in_pool,
                                    "weight": 100,
                                }
                            ]
                        }
                    }
                ).run(self.conn)
        return True

    """
    DOMAINS TABLE UPGRADES
    """

    def domains(self, version):
        table = "domains"
        data = list(r.table(table).run(self.conn))
        log.info("UPGRADING " + table + " VERSION " + str(version))
        if version == 2:
            for d in data:
                id = d["id"]
                d.pop("id", None)

                """ CONVERSION FIELDS PRE CHECKS """
                # ~ try:
                # ~ if not self.check_done( d,
                # ~ [],
                # ~ []):
                ##### CONVERSION FIELDS
                # ~ cfg['field']={}
                # ~ r.table(table).update(cfg).run(self.conn)
                # ~ except Exception as e:
                # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
                # ~ log.error('Error detail: '+str(e))

                """ NEW FIELDS PRE CHECKS """
                try:
                    if not self.check_done(d, ["preferences"], []):
                        ##### NEW FIELDS
                        self.add_keys(
                            table,
                            [
                                {
                                    "options": {
                                        "viewers": {"spice": {"fullscreen": False}}
                                    }
                                }
                            ],
                            id=id,
                        )
                except Exception as e:
                    log.error(
                        "Could not update table "
                        + table
                        + " add fields for db version "
                        + str(version)
                        + "!"
                    )
                    log.error("Error detail: " + str(e))

                """ REMOVE FIELDS PRE CHECKS """
                # ~ try:
                # ~ if not self.check_done( d,
                # ~ [],
                # ~ []):
                #### REMOVE FIELDS
                # ~ self.del_keys(TABLE,[])
                # ~ except Exception as e:
                # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
                # ~ log.error('Error detail: '+str(e))
        if version == 7:
            for d in data:
                id = d["id"]
                d.pop("id", None)

                """ CONVERSION FIELDS PRE CHECKS """
                # ~ try:
                # ~ if not self.check_done( d,
                # ~ [],
                # ~ []):
                ##### CONVERSION FIELDS
                # ~ cfg['field']={}
                # ~ r.table(table).update(cfg).run(self.conn)
                # ~ except Exception as e:
                # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
                # ~ log.error('Error detail: '+str(e))

                """ NEW FIELDS PRE CHECKS """
                try:
                    if not self.check_done(d, ["preferences"], []):
                        ##### NEW FIELDS
                        self.add_keys(
                            table,
                            [{"options": {"viewers": {"id_graphics": "default"}}}],
                            id=id,
                        )
                except Exception as e:
                    log.error(
                        "Could not update table "
                        + table
                        + " add fields for db version "
                        + version
                        + "!"
                    )
                    log.error("Error detail: " + str(e))

        if version == 14:
            self.index_create(table, ["tag"])

        if version == 16:
            try:
                r.table(table).index_create(
                    "wg_mac", r.row["create_dict"]["macs"]["wireguard"]
                ).run(self.conn)
            except:
                None

        if version == 18:
            try:
                domains = r.table(table).with_fields("id", "tag").run(self.conn)
                for d in domains:
                    if d["tag"]:
                        r.table(table).get(d["id"]).update(
                            {"tag": d["tag"].replace("#", "=")}
                        ).run(self.conn)
            except:
                None

        if version == 20:
            domains = r.table(table).with_fields("id", "forced_hyp").run(self.conn)
            for domain in domains:
                if domain["forced_hyp"] and not isinstance(domain["forced_hyp"], list):
                    r.table(table).get(domain["id"]).update(
                        {"forced_hyp": [domain["forced_hyp"]]}
                    ).run(self.conn)
                if domain["forced_hyp"] == ["false"]:
                    r.table(table).get(domain["id"]).update({"forced_hyp": False}).run(
                        self.conn
                    )

        if version == 22:
            try:
                r.table(table).index_create("image_id", r.row["image"]["id"]).run(
                    self.conn
                )
            except:
                None
            try:
                ids = [d["id"] for d in r.table(table).pluck("id").run(self.conn)]
                for domain_id in ids:
                    r.table("domains").get(domain_id).update(
                        {"image": self.get_domain_stock_card(domain_id)}
                    ).run(self.conn)
            except:
                None

        if version == 23:
            r.table(table).filter(r.row["kind"].match("template")).update(
                {"enabled": True}
            ).run(self.conn)

        if version == 24:
            try:
                ids = [
                    d["id"]
                    for d in r.table(table)
                    .filter(~r.row.has_fields("image"))
                    .run(self.conn)
                ]
                for domain_id in ids:
                    r.table("domains").get(domain_id).update(
                        {"image": self.get_domain_stock_card(domain_id)}
                    ).run(self.conn)
            except Exception as e:
                None

        if version == 25:
            try:
                r.table(table).get_all("base", index="kind").update(
                    {"kind": "template"}
                ).run(self.conn)
                r.table(table).get_all("user_template", index="kind").update(
                    {"kind": "template"}
                ).run(self.conn)
                r.table(table).get_all("public_template", index="kind").update(
                    {"kind": "template"}
                ).run(self.conn)
            except Exception as e:
                print(e)
                None

        if version == 26:
            try:
                r.table(table).index_create(
                    "parents",
                    lambda dom: dom["parents"].map(
                        lambda parents: [dom["id"], parents]
                    ),
                    multi=True,
                ).run(self.conn)
            except Exception as e:
                print(e)
                None

        if version == 28:
            self.index_create(table, ["jumperurl"])

        if version == 30:
            r.table(table).filter(
                lambda domain: domain["create_dict"]["hardware"]["interfaces"].contains(
                    "wireguard"
                )
            ).update(
                {
                    "guest_properties": {
                        "credentials": {
                            "username": "isard",
                            "password": "pirineus",
                        },
                        "fullscreen": r.row["options"]["viewers"]["spice"][
                            "fullscreen"
                        ],
                        "viewers": {
                            "file_spice": {"options": None},
                            "browser_vnc": {"options": None},
                            "file_rdpgw": {"options": None},
                            "file_rdpvpn": {"options": None},
                            "browser_rdp": {"options": None},
                        },
                    }
                }
            ).run(
                self.conn
            )
            r.table(table).filter(~r.row.has_fields("guest_properties")).update(
                {
                    "guest_properties": {
                        "credentials": {
                            "username": "isard",
                            "password": "pirineus",
                        },
                        "fullscreen": r.row["options"]["viewers"]["spice"][
                            "fullscreen"
                        ],
                        "viewers": {
                            "file_spice": {"options": None},
                            "browser_vnc": {"options": None},
                        },
                    }
                }
            ).run(self.conn)
            r.db("isard").table("domains").replace(r.row.without("options")).run(
                self.conn
            )

        if version == 32:
            try:
                r.table(table).filter(
                    {"create_dict": {"reservables": {"vgpus": [None]}}}
                ).replace(r.row.without({"create_dict": {"reservables": True}})).run(
                    self.conn
                )
            except Exception as e:
                print(e)
                None

        if version == 38:
            try:
                r.table(table).update(
                    {
                        "create_dict": {
                            "hardware": {
                                "diskbus": r.literal(),
                                "disk_bus": r.row["create_dict"]["hardware"]["diskbus"],
                            }
                        }
                    }
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 42:
            try:
                r.table(table).index_create(
                    "disk_paths",
                    lambda domain: domain["create_dict"]["hardware"][
                        "disks"
                    ].concat_map(lambda data: [data["file"]]),
                    multi=True,
                ).run(self.conn)
            except Exception as e:
                print(e)
            try:
                r.table(table).index_create(
                    "storage_ids",
                    lambda domain: domain["create_dict"]["hardware"][
                        "disks"
                    ].concat_map(lambda data: [data["storage_id"]]),
                    multi=True,
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 43:
            try:
                r.table(table).index_create(
                    "media_ids",
                    lambda domain: domain["create_dict"]["hardware"]["isos"].concat_map(
                        lambda data: [data["id"]]
                    ),
                    multi=True,
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 50:
            try:
                r.table(table).index_create(
                    "kind_status", [r.row["kind"], r.row["status"]]
                ).run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create(
                    "kind_category", [r.row["kind"], r.row["category"]]
                ).run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create(
                    "kind_status_category",
                    [r.row["kind"], r.row["status"], r.row["category"]],
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 55:
            try:
                r.table(table).index_create(
                    "kind_user", [r.row["kind"], r.row["user"]]
                ).run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create(
                    "kind_group", [r.row["kind"], r.row["group"]]
                ).run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create(
                    "kind_status_user", [r.row["kind"], r.row["status"], r.row["user"]]
                ).run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create(
                    "kind_status_group",
                    [r.row["kind"], r.row["status"], r.row["group"]],
                ).run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create(
                    "status_user",
                    [r.row["status"], r.row["user"]],
                ).run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create(
                    "status_group",
                    [r.row["status"], r.row["group"]],
                ).run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create(
                    "status_category",
                    [r.row["status"], r.row["category"]],
                ).run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create(
                    "template_enabled",
                    [r.row["kind"], r.row["enabled"]],
                ).run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create(
                    "template_enabled_category",
                    [r.row["kind"], r.row["enabled"], r.row["category"]],
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 56:
            r.table(table).update({"hyp_started": False}).run(self.conn)

        if version == 57:
            try:
                r.table("domains").index_create(
                    "serverstostart", [r.row["kind"], r.row["server"], r.row["status"]]
                ).run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table("domains").replace(
                    r.row.without({"create_dict": {"server"}})
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 58:
            r.table(table).update(
                {"create_dict": {"hardware": {"virtualization_nested": False}}}
            ).run(self.conn)

        return True

    """
    DEPLOYMENTS TABLE UPGRADES
    """

    def deployments(self, version):
        table = "deployments"
        data = list(r.table(table).run(self.conn))
        log.info("UPGRADING " + table + " VERSION " + str(version))

        if version == 18:
            try:
                deployments = list(r.table(table).run(self.conn))
                for d in deployments:
                    deployment = r.table(table).get(d["id"]).run(self.conn)
                    r.table(table).get(d["id"]).delete().run(self.conn)
                    deployment["id"] = deployment["id"].replace("#", "=")
                    r.table(table).insert(deployment).run(self.conn)
            except:
                None

        return True

    """
    MEDIA TABLE UPGRADES
    """

    def media(self, version):
        table = "media"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        # ~ data=list(r.table(table).run(self.conn))
        if version == 3:
            """KEY INDEX FIELDS PRE CHECKS"""
            self.index_create(table, ["kind"])
        if version == 9:
            """KEY INDEX FIELDS PRE CHECKS"""
            self.index_create(table, ["category", "group"])
            # ~ for d in data:
            # ~ id=d['id']
            # ~ d.pop('id',None)
            # ~ ''' CONVERSION FIELDS PRE CHECKS '''
            # ~ try:
            # ~ if not self.check_done( d,
            # ~ [],
            # ~ []):
            ##### CONVERSION FIELDS
            # ~ cfg['field']={}
            # ~ r.table(table).update(cfg).run(self.conn)
            # ~ except Exception as e:
            # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
            # ~ log.error('Error detail: '+str(e))

            # ~ ''' NEW FIELDS PRE CHECKS '''
            # ~ try:
            # ~ if not self.check_done( d,
            # ~ ['preferences'],
            # ~ []):
            # ~ ##### NEW FIELDS
            # ~ self.add_keys(  table,
            # ~ [   {'options': {'viewers':{'spice':{'fullscreen':False}}}}],
            # ~ id=id)
            # ~ except Exception as e:
            # ~ log.error('Could not update table '+table+' add fields for db version '+str(version)+'!')
            # ~ log.error('Error detail: '+str(e))

            # ~ ''' REMOVE FIELDS PRE CHECKS '''
            # ~ try:
            # ~ if not self.check_done( d,
            # ~ [],
            # ~ []):
            #### REMOVE FIELDS
            # ~ self.del_keys(TABLE,[])
            # ~ except Exception as e:
            # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
            # ~ log.error('Error detail: '+str(e))

        if version == 33:
            r.table(table).filter(
                lambda media: r.not_(media.has_fields({"allowed": {"roles": True}}))
            ).update({"allowed": {"roles": False, "categories": False}}).run(self.conn)
        if version == 34:
            r.table(table).filter(
                lambda media: r.not_(media.has_fields({"allowed": {"roles": True}}))
            ).update({"allowed": {"roles": False, "categories": False}}).run(self.conn)

        if version == 35:
            medias = r.table(table).run(self.conn)
            admin_user = list(
                r.table("users")
                .filter({"uid": "admin", "provider": "local"})
                .run(self.conn)
            )[0]
            user = {
                "category": admin_user["category"],
                "group": admin_user["group"],
                "user": admin_user["id"],
                "username": admin_user["username"],
            }
            for media in medias:
                if (
                    not r.table("categories").get(media["category"]).run(self.conn)
                    or not r.table("groups").get(media["group"]).run(self.conn)
                    or not r.table("users").get(media["user"]).run(self.conn)
                ):
                    r.table(table).get(media["id"]).update(user).run(self.conn)

        if version == 49:
            medias = list(r.table("media").run(self.conn))
            for media in medias:
                if "." in media["id"]:
                    r.table("domains").get_all(media["id"], index="media_ids").update(
                        {
                            "create_dict": {
                                "hardware": {
                                    "isos": [{"id": media["id"].replace(".", "_")}]
                                }
                            }
                        }
                    ).run(self.conn)
                    old_id = media["id"]
                    media["id"] = media["id"].replace(".", "_")
                    r.table("media").insert(media).run(self.conn)
                    r.table("media").get(old_id).delete().run(self.conn)

    """
    GROUPS TABLE UPGRADES
    """

    def groups(self, version):
        table = "groups"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        # ~ data=list(r.table(table).run(self.conn))
        if version == 9:
            """KEY INDEX FIELDS PRE CHECKS"""
            self.index_create(table, ["parent_category"])
            # ~ for d in data:
            # ~ id=d['id']
            # ~ d.pop('id',None)
            # ~ ''' CONVERSION FIELDS PRE CHECKS '''
            # ~ try:
            # ~ if not self.check_done( d,
            # ~ [],
            # ~ []):
            ##### CONVERSION FIELDS
            # ~ cfg['field']={}
            # ~ r.table(table).update(cfg).run(self.conn)
            # ~ except Exception as e:
            # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
            # ~ log.error('Error detail: '+str(e))

            # ~ ''' NEW FIELDS PRE CHECKS '''
            # ~ try:
            # ~ if not self.check_done( d,
            # ~ ['preferences'],
            # ~ []):
            #        #~ data=list(r.table(table).run(self.conn))               #~ [   {'options': {'viewers':{'spice':{'fullscreen':False}}}}],
            # ~ id=id)
            # ~ except Exception as e:
            # ~ log.error('Could not update table '+table+' add fields for db version '+str(version)+'!')
            # ~ log.error('Error detail: '+str(e))

            # ~ ''' REMOVE FIELDS PRE CHECKS '''
            # ~ try:
            # ~ if not self.check_done( d,
            # ~ [],
            # ~ []):
            #### REMOVE FIELDS
            # ~ self.del_keys(TABLE,[])
            # ~ except Exception as e:
            # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
            # ~ log.error('Error detail: '+str(e))

        if version == 40:
            r.table(table).update({"linked_groups": []}).run(self.conn)

        if version == 51:
            r.table(table).update({"external_app_id": None, "external_gid": None}).run(
                self.conn
            )

        return True

    """
    DOMAINS TABLE VIDEOS
    """

    def videos(self, version):
        table = "videos"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        if version == 12:
            r.table("videos").insert(
                [
                    {
                        "allowed": {
                            "categories": False,
                            "groups": False,
                            "roles": False,
                            "users": False,
                        },
                        "description": "nvidia with qxl only used to install drivers",
                        "heads": 1,
                        "id": "nvidia-with-qxl",
                        "model": "qxl",
                        "name": "NVIDIA with QXL",
                        "ram": 65536,
                        "vram": 65536,
                    },
                    {
                        "allowed": {
                            "categories": False,
                            "groups": False,
                            "roles": False,
                            "users": False,
                        },
                        "description": "Nvidia default profile",
                        "heads": 1,
                        "id": "gpu-default",
                        "model": "nvidia",
                        "name": "gpu-default",
                        "ram": 1048576,
                        "vram": 1048576,
                    },
                ]
            ).run(self.conn)

        if version == 31:
            try:
                r.table("videos").get("nvidia-with-qxl").delete().run(self.conn)
            except:
                None
            try:
                r.table("videos").get("gpu-default").delete().run(self.conn)
            except:
                None
            r.table("videos").insert(
                {
                    "allowed": {
                        "categories": False,
                        "groups": False,
                        "roles": False,
                        "users": False,
                    },
                    "description": "Will only use de GPU graphics",
                    "heads": 1,
                    "id": "none",
                    "model": "nvidia",
                    "name": "Only GPU",
                    "ram": 0,
                    "vram": 0,
                },
            ).run(self.conn)

        return True

    """
    DOMAINS TABLE GRAPHICS
    """

    def graphics(self, version):
        table = "graphics"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        # ~ data=list(r.table(table).run(self.conn))

        if version == 7:
            r.table(table).delete().run(self.conn)
            r.table("graphics").insert(
                [
                    {
                        "id": "default",
                        "name": "Default",
                        "description": "Spice viewer with compression and vlc",
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
                            "vlc": {"options": {}},
                        },
                    }
                ]
            ).run(self.conn)

        if version == 36:
            None
        if version == 37:
            default = r.table(table).get("default").run(self.conn)
            if default["types"].get("vlc"):
                default["types"]["vnc"] = default["types"].pop("vlc")
                default["description"] = "Spice viewer with compression and vnc"
                r.table(table).replace(default).run(self.conn)
        return True

    """
    USERS TABLE UPGRADES
    """

    def users(self, version):
        table = "users"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        # ~ data=list(r.table(table).run(self.conn))
        if version == 9:
            """KEY INDEX FIELDS PRE CHECKS"""
            self.index_create(table, ["category"])

            # ~ for d in data:
            # ~ id=d['id']
            # ~ d.pop('id',None)
            # ~ ''' CONVERSION FIELDS PRE CHECKS '''
            # ~ try:
            # ~ if not self.check_done( d,
            # ~ [],
            # ~ []):
            ##### CONVERSION FIELDS
            # ~ cfg['field']={}
            # ~ r.table(table).update(cfg).run(self.conn)
            # ~ except Exception as e:
            # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
            # ~ log.error('Error detail: '+str(e))

            # ~ ''' NEW FIELDS PRE CHECKS '''
            # ~ try:
            # ~ if not self.check_done( d,
            # ~ ['preferences'],
            # ~ []):
            # ~ ##### NEW FIELDS
            # ~ self.add_keys(  table,
            # ~ [   {'options': {'viewers':{'spice':{'fullscreen':False}}}}],
            # ~ id=id)
            # ~ except Exception as e:
            # ~ log.error('Could not update table '+table+' add fields for db version '+str(version)+'!')
            # ~ log.error('Error detail: '+str(e))

            # ~ ''' REMOVE FIELDS PRE CHECKS '''
            # ~ try:
            # ~ if not self.check_done( d,
            # ~ [],
            # ~ []):
            #### REMOVE FIELDS
            # ~ self.del_keys(TABLE,[])
            # ~ except Exception as e:
            # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
            # ~ log.error('Error detail: '+str(e))

        if version == 13:
            # Change False value to empty string of admin photo field
            # to not break golang unmarshal of json
            # backend/isard/user.go
            if (
                not r.table(table)
                .get("local-default-admin-admin")
                .pluck("photo")
                .run(self.conn)
                .get("photo", True)
            ):
                r.table(table).get("local-default-admin-admin").update(
                    {"photo": ""}
                ).run(self.conn)

        if version == 15:
            # We need to do it for all users
            r.table(table).filter({"photo": None}).update({"photo": ""}).run(self.conn)
            r.table(table).filter({"photo": False}).update({"photo": ""}).run(self.conn)
            r.table(table).update({"photo": (r.row["photo"]).default("")}).run(
                self.conn
            )

        if version == 21:
            try:
                r.table(table).index_create(
                    "wg_client_ip", r.row["vpn"]["wireguard"]["Address"]
                ).run(self.conn)
            except:
                log.error(
                    "Could not update table "
                    + table
                    + " index_create for db version "
                    + str(version)
                    + "!"
                )
                log.error("Error detail: " + str(e))

        if version == 39:
            r.table(table).update({"secondary_groups": []}).run(self.conn)

        if version == 46:
            r.table(table).filter(~r.row.has_fields("secondary_groups")).update(
                {"secondary_groups": []}
            ).run(self.conn)

        if version == 50:
            try:
                r.table(table).index_create("active").run(self.conn)
            except Exception as e:
                print(e)

        if version == 53:
            try:
                r.table(table).index_create("secondary_groups", multi=True).run(
                    self.conn
                )
            except Exception as e:
                print(e)

        if version == 59:

            r.table(table).index_create(
                "uid_category_provider",
                [r.row["uid"], r.row["category"], r.row["provider"]],
            ).run(self.conn)

            uid_list = list(
                r.table(table)
                .filter(lambda doc: doc["uid"].match(" "))
                .pluck("uid")
                .run(self.conn)
            )

            for uid in uid_list:
                r.table(table).get_all(uid["uid"], index="uid").update(
                    {
                        "uid": uid["uid"].replace(" ", ""),
                        "username": uid["uid"].replace(" ", ""),
                    }
                ).run(self.conn)

        return True

    """
    ROLES TABLE UPGRADES
    """

    def roles(self, version):
        table = "roles"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        # ~ data=list(r.table(table).run(self.conn))
        if version == 9:
            manager = r.table("roles").get("manager").run(self.conn)
            if manager is None:
                r.table("roles").insert(
                    {
                        "id": "manager",
                        "name": "Manager",
                        "description": "Can manage users, desktops, templates and media in a category",
                        "quota": {
                            "domains": {
                                "desktops": 10,
                                "desktops_disk_max": 40000000,
                                "templates": 2,
                                "templates_disk_max": 40000000,
                                "running": 2,
                                "isos": 2,
                                "isos_disk_max": 5000000,
                            },
                            "hardware": {"vcpus": 6, "memory": 6000000},
                        },  # 6GB
                    }
                ).run(self.conn)
            # ~ for d in data:
            # ~ id=d['id']
            # ~ d.pop('id',None)
            # ~ ''' CONVERSION FIELDS PRE CHECKS '''
            # ~ try:
            # ~ if not self.check_done( d,
            # ~ [],
            # ~ []):
            ##### CONVERSION FIELDS
            # ~ cfg['field']={}
            # ~ r.table(table).update(cfg).run(self.conn)
            # ~ except Exception as e:
            # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
            # ~ log.error('Error detail: '+str(e))

            # ~ ''' NEW FIELDS PRE CHECKS '''
            # ~ try:
            # ~ if not self.check_done( d,
            # ~ ['preferences'],
            # ~ []):
            # ~ ##### NEW FIELDS
            # ~ self.add_keys(  table,
            # ~ [   {'options': {'viewers':{'spice':{'fullscreen':False}}}}],
            # ~ id=id)
            # ~ except Exception as e:
            # ~ log.error('Could not update table '+table+' add fields for db version '+str(version)+'!')
            # ~ log.error('Error detail: '+str(e))

            # ~ ''' REMOVE FIELDS PRE CHECKS '''
            # ~ try:
            # ~ if not self.check_done( d,
            # ~ [],
            # ~ []):
            #### REMOVE FIELDS
            # ~ self.del_keys(TABLE,[])
            # ~ except Exception as e:
            # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
            # ~ log.error('Error detail: '+str(e))
        if version == 52:
            log.info("UPGRADING " + table + " VERSION " + str(version))
            updated = r.table("roles").has_fields("sortorder").count().run(self.conn)
            if updated == 0:
                r.table("roles").get("user").update({"sortorder": 1}).run(self.conn)
                r.table("roles").get("advanced").update({"sortorder": 2}).run(self.conn)
                r.table("roles").get("manager").update({"sortorder": 3}).run(self.conn)
                r.table("roles").get("admin").update({"sortorder": 4}).run(self.conn)

        return True

    """
    INTERFACES TABLE UPGRADES
    """

    def interfaces(self, version):
        table = "interfaces"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        if version == 11:
            wg = r.table(table).get("wireguard").run(self.conn)
            if wg == None:
                r.table(table).insert(
                    [
                        {
                            "allowed": {
                                "categories": False,
                                "groups": False,
                                "roles": ["admin"],
                                "users": False,
                            },
                            "description": "Allows direct access to guest IP",
                            "id": "wireguard",
                            "ifname": "wireguard",
                            "kind": "network",
                            "model": "virtio",
                            "name": "Wireguard VPN",
                            "net": "wireguard",
                            "qos_id": "unlimited",
                        }
                    ]
                ).run(self.conn)
        if version == 16:
            wg = r.table(table).get("wireguard").run(self.conn)
            if wg == None:
                r.table(table).insert(
                    [
                        {
                            "allowed": {
                                "categories": False,
                                "groups": False,
                                "roles": ["admin"],
                                "users": False,
                            },
                            "description": "Allows direct access to guest IP",
                            "id": "wireguard",
                            "ifname": "4095",
                            "kind": "ovs",
                            "model": "virtio",
                            "name": "Wireguard VPN",
                            "net": "4095",
                            "qos_id": "unlimited",
                        }
                    ]
                ).run(self.conn)
            else:
                r.table(table).get("wireguard").update(
                    {"kind": "ovs", "ifname": "4095", "net": "4095"}
                ).run(self.conn)

        if version == 17:
            ifs = list(r.table(table).run(self.conn))
            for interface in ifs:
                if interface["ifname"].startswith("br-"):
                    vlan_id = interface["ifname"].split("br-")[1]

                    r.table(table).get(interface["id"]).update(
                        {"ifname": vlan_id, "kind": "ovs", "net": vlan_id}
                    ).run(self.conn)
            # ~ for d in data:
            # ~ id=d['id']
            # ~ d.pop('id',None)
            # ~ ''' CONVERSION FIELDS PRE CHECKS '''
            # ~ try:
            # ~ if not self.check_done( d,
            # ~ [],
            # ~ []):
            ##### CONVERSION FIELDS
            # ~ cfg['field']={}
            # ~ r.table(table).update(cfg).run(self.conn)
            # ~ except Exception as e:
            # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
            # ~ log.error('Error detail: '+str(e))

            # ~ ''' NEW FIELDS PRE CHECKS '''
            # ~ try:
            # ~ if not self.check_done( d,
            # ~ ['preferences'],
            # ~ []):
            # ~ ##### NEW FIELDS
            # ~ self.add_keys(  table,
            # ~ [   {'options': {'viewers':{'spice':{'fullscreen':False}}}}],
            # ~ id=id)
            # ~ except Exception as e:
            # ~ log.error('Could not update table '+table+' add fields for db version '+str(version)+'!')
            # ~ log.error('Error detail: '+str(e))

            # ~ ''' REMOVE FIELDS PRE CHECKS '''
            # ~ try:
            # ~ if not self.check_done( d,
            # ~ [],
            # ~ []):
            #### REMOVE FIELDS
            # ~ self.del_keys(TABLE,[])
            # ~ except Exception as e:
            # ~ log.error('Could not update table '+table+' remove fields for db version '+str(version)+'!')
            # ~ log.error('Error detail: '+str(e))
        if version == 27:
            r.table(table).filter({"qos_id": False}).update(
                {"qos_id": "unlimited"}
            ).run(self.conn)

        return True

    """
    STORAGE TABLE UPGRADES
    """

    def storage(self, version):
        table = "storage"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        if version == 41:
            self.index_create(table, ["user_id"])
            self.index_create(table, ["status"])
        if version == 47:
            data = list(
                r.table("storage")
                .has_fields({"qemu-img-info": {"backing-filename": True}})
                .merge(
                    lambda store: {
                        "parent": r.table("storage")
                        .get(
                            store["qemu-img-info"]["backing-filename"]
                            .split("/")[-1]
                            .split(".")[0]
                        )
                        .default({"id": None})["id"]
                    }
                )
                .run(self.conn)
            )
            r.table("storage").insert(data, conflict="update").run(self.conn)

        if version == 54:
            r.table("storage").filter(lambda s: ~s["status"].eq("deleted")).update(
                {
                    "status_logs": [
                        {"status": "created", "time": int(time.time()) - 43200},  # 12h
                        {"status": "ready", "time": int(time.time()) - 43199},
                    ]
                }
            ).run(self.conn)
            r.table("storage").filter(lambda s: s["status"].eq("deleted")).update(
                {
                    "status_logs": [
                        {"status": "created", "time": int(time.time()) - 3600},  # 1h
                        {"status": "ready", "time": int(time.time()) - 3599},
                    ]
                }
            ).run(self.conn)

        return True

    def storage_physical_domains(self, version):
        table = "storage_physical_domains"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        if version == 45:
            r.table(table).delete().run(self.conn)
        return True

    def storage_physical_media(self, version):
        table = "storage_physical_media"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        if version == 45:
            r.table(table).delete().run(self.conn)
        return True

    def remotevpn(self, version):
        table = "remotevpn"
        log.info("UPGRADING " + table + " VERSION " + str(version))

        if version == 21:
            try:
                r.table(table).index_create(
                    "wg_client_ip", r.row["vpn"]["wireguard"]["Address"]
                ).run(self.conn)
            except:
                None

    """
    SCHEDULER_JOBS TABLE UPGRADES
    """

    def scheduler_jobs(self, version):
        table = "scheduler_jobs"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        if version == 44:
            self.index_create(table, ["type"])
            r.table(table).filter({"kind": "cron"}).update({"type": "system"}).run(
                self.conn
            )
            r.table(table).filter({"kind": "interval"}).update({"type": "system"}).run(
                self.conn
            )
            r.table(table).filter({"kind": "date"}).update({"type": "bookings"}).run(
                self.conn
            )
        return True

    """
    BOOKINGS TABLE UPGRADES
    """

    def bookings_priority(self, version):
        table = "bookings_priority"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        if version == 48:
            default = (
                r.table(table).get("default").pluck("allowed")["allowed"].run(self.conn)
            )

            new_allowed = {
                "categories": False
                if default["categories"] == None
                else default["categories"],
                "groups": False if default["groups"] == None else default["groups"],
                "roles": False if default["roles"] == None else default["roles"],
                "users": False if default["users"] == None else default["users"],
            }

            r.table(table).get("default").update({"allowed": new_allowed}).run(
                self.conn
            )

            default_admins = (
                r.table(table)
                .get("default admins")
                .pluck("allowed")["allowed"]
                .run(self.conn)
            )

            new_allowed = {
                "categories": False
                if default_admins["categories"] == None
                else default_admins["categories"],
                "groups": False
                if default_admins["groups"] == None
                else default_admins["groups"],
                "roles": False
                if default_admins["roles"] == None
                else default_admins["roles"],
                "users": False
                if default_admins["users"] == None
                else default_admins["users"],
            }

            r.table(table).get("default admins").update({"allowed": new_allowed}).run(
                self.conn
            )

    """
    Upgrade general actions
    """

    def add_keys(self, table, keys, id=False):
        for key in keys:
            if id is False:
                r.table(table).update(key).run(self.conn)
            else:
                r.table(table).get(id).update(key).run(self.conn)

    def del_keys(self, table, keys, id=False):
        log.info("Del keys init")
        for key in keys:
            if id is False:
                r.table(table).replace(r.row.without(key)).run(self.conn)
            else:
                r.table(table).get(id).replace(r.row.without(key)).run(self.conn)

    def check_done(self, dict, must=[], mustnot=[]):
        log.info("Self check init")
        done = False
        # ~ check_done(cfg,['grafana','resources','voucher_access',{'engine':{'api':{'token'}}}],[{'engine':{'carbon'}}])
        for m in must:
            if type(m) is str:
                m = [m]
            if self.keys_exists(dict, m):
                done = True
                # ~ print(str(m)+' exists on dict. ok')
            # ~ else:
            # ~ print(str(m)+' not exists on dict. KO')

        for mn in mustnot:
            log.info(mn)
            if type(mn) is str:
                mn = [mn]
            if not self.keys_exists(dict, mn):
                done = True
                # ~ print(str(mn)+' not exists on dict. ok')
            # ~ else:
            # ~ print(str(mn)+' exists on dict. KO')
        return done

    def keys_exists(self, element, keys):
        """
        Check if *keys (nested) exists in `element` (dict).
        """
        if type(element) is not dict:
            raise AttributeError("keys_exists() expects dict as first argument.")
        if len(keys) == 0:
            raise AttributeError(
                "keys_exists() expects at least two arguments, one given."
            )

        _element = element
        for key in keys:
            log.info(key)
            try:
                _element = _element[key]
            except KeyError:
                return False
        return True

    def index_create(self, table, indexes):

        indexes_ontable = r.table(table).index_list().run(self.conn)
        apply_indexes = [mi for mi in indexes if mi not in indexes_ontable]
        for i in apply_indexes:
            r.table(table).index_create(i).run(self.conn)
            r.table(table).index_wait(i).run(self.conn)

    ## To upgrade to default cards
    def get_domain_stock_card(self, domain_id):
        total = 0
        for i in range(0, len(domain_id)):
            total += total + ord(domain_id[i])
        total = total % 48 + 1
        return self.get_card(str(total) + ".jpg", "stock")

    def get_card(self, card_id, type):
        return {
            "id": card_id,
            "url": "/assets/img/desktops/" + type + "/" + card_id,
            "type": type,
        }
