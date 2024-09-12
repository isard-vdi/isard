# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import json
import sys
import time
from uuid import uuid4

import humanfriendly as hf
import rethinkdb as r
from isardvdi_common.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.storage import Storage
from redis import Redis

from .lib import *
from .log import *

""" 
Update to new database release version when new code version release
"""
release_version = 143
# release 143: Add UID index to categories
# release 142: Add uuid and photo fields to category
# release 141: Add deployment quotas
# release 140: Add credentials to RDP VPN viewer
# release 139: Add template index to deployments table
# release 138: Add duplicated_parent_template index and fixed parents index in recycle_bin
# release 137: Add notification templates with GPU deletion warnings
# release 136: Add co-owners to deployments
# release 135: update gpus_profiles
# release 134: add server_autostart flag in domains
# release 133: Add storage_id, domain_id, deployment_id, user_id, category_id, group_id index to storage
# release 132: update gpus_profiles
# release 131: storage permissions on existing disks
# release 130: Remove deleted storage from storage table
# release 129: Add default maintenance text to config table
# release 128: Add volatile field to applied quota
# release 127: Add viewers config
# release 126: Add user_category index to users table
# release 125: Add owner_category index
# release 124: Add/Remove required logs_users index
# release 123: Fix email field users
# release 122: Add maintenance field to categories
# release 121: BREAKING CHANGE, update "storage_pool" to new table
# release 120: REMOVED: update "storage_pool" table with new fields, add index "name"
# release 119: Add new password parameters to users
# release 118: Authentication uuid ids and email verification upgrade
# release 117: Remove computed usage totals
# release 116: Add new password parameters to users
# release 115: Add role index to users
# release 114: Fix domains and deployments with isos as string
# release 113: Add secondary indexes for storage and scheduler
# release 112: Merge duplicated users into one unique user
# release 111: Added interfaces, videos, boot_order and reservables index to domains
#              Remove deleted resources from domains
# release 110: Remove storages without field user_id
# release 109: Upgrade old domains with old storage to new storage
# release 106: Add parent index to storage
# release 105: Remove units from str_created in usage limits
# release 104: Remove existing user_storages and it's entries in users
# release 103: Add logs_desktops tables indexes
# release 102: Fix domains with empty interfaces field that got a dict instead of list
# release 101: Interfaces as list to keep order
# release 100: Fix interfaces starting with blank space
# release 99: Fix empty interface array to dict
# release 98: Update desktops created with wrong interfaces
# release 97: Update wg_mac index to new interfaces field format
# release 96: Interfaces managed with only interfaces and interfaces_macs fields
# release 95: Add download_id and it's index to domains and media already downloaded and
# release 94: Remove isardvdi and isardvdi-hypervisor secrets from database and use env variables
# release 93: admins priority update with new identification
# release 92: Add user_storage name index to check for duplicateds
# release 91: Rename logs_users owner fields to accomodate logs_desktops and consumptions
# release 90: Remove viewer key from stopped and failed desktops
# release 89: Add html5_ext_port to proxies index
# release 88: Fix guest_ip and proxies indexes
# release 87: Add viewer guest_ip and proxies indexes
# release 86: Fix parents to already duplicated templates
# release 85: fixed domains parents index and duplicated_parent_template index added
# release 84: "duplicate_parent_template" of old duplicated with oldest as parent
# release 83: Add accessed to missing templates
# release 82: Remove orphan deployments
# release 81: Add desktops_priority "name" index
# release 80: "tag_status" index for domains table
# release 79: added item_type_user bookings index
# release 78: remove status_logs from domains
# release 77: add kind to wg_mac index
# release 76: update gpus_profiles
# release 75: replace desktop interface macs if found duplicated
# release 74: update gpus_profiles
# release 73: 'favourite_hyp' domains field should be a list if it isn't False
# release 72: Remove existing storage_node entries (does not exist anymore)
# release 71: Added bookings_priority name index
# release 70: Add hypervisor execution time
# release 69: Buffering hyper
# release 68: Removed table field from interfaces, videos, remotevpn, qos_disk and qos_net.
# release 67: Updated qos_disk adding field read_iops_sec_max
# release 66: Added secondary indexes for uuids
# release 65: Updated users quotas removing fields isos_disk_size and templates_disk_size.
#             Updated users quotas adding fields total_size and total_soft_size.
#             Added user_status index to table storage
# release 64: Move hypervisor_pools paths to storage_pool
# release 63: Updated "Only GPU" video "model": "nvidia" to "model": "none"
# release 62: Updated media progress fields and added total_bytes field.
# release 61: Added indexes to table media.
#             Added kind_user_tag index and updated all desktops to tag False.
# release 60: Modify transitional_states_polling to 10 seconds by default
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
    "scheduler_jobs",
    "bookings_priority",
    "categories",
    "qos_net",
    "qos_disk",
    "gpu_profiles",
    "desktops_priority",
    "logs_users",
    "logs_desktops",
    "user_storage",
    "usage_parameter",
    "usage_consumption",
    "secrets",
    "recycle_bin",
    "authentication",
    "storage_pool",
    "notification_tmpls",
    "system_events",
]


class Upgrade(object):
    def __init__(self):
        cfg = loadConfig()
        self.conf = cfg.cfg()

        self.conn = False
        self.cfg = False
        self.check_db()
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

    def check_db(self):
        ready = False
        while not ready:
            try:
                self.conn = r.connect(
                    host=self.conf["RETHINKDB_HOST"],
                    port=self.conf["RETHINKDB_PORT"],
                    db=self.conf["RETHINKDB_DB"],
                ).repl()
                print("Database server OK")
                ready = True
            except Exception as e:
                print(
                    "Upgrade error: Database server "
                    + self.cfg["RETHINKDB_HOST"]
                    + ":"
                    + self.cfg["RETHINKDB_PORT"]
                    + " not present. Waiting to be ready"
                )
                time.sleep(0.5)
        ready = False

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

        if version == 60:
            try:
                d["engine"]["intervals"]["transitional_states_polling"] = 10
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

        if version == 127:
            try:
                rdp_fixed = """full address:s:%s"""
                rdp_default = """enableworkspacereconnect:i:0
disable wallpaper:i:0
allow font smoothing:i:0
allow desktop composition:i:0
disable full window drag:i:1
disable menu anims:i:1
disable themes:i:0
disable cursor setting:i:0
bitmapcachepersistenable:i:1
audiomode:i:0
redirectprinters:i:1
redirectcomports:i:0
redirectsmartcards:i:1
redirectclipboard:i:1
redirectposdevices:i:0
drivestoredirect:s:
autoreconnection enabled:i:1
authentication level:i:2
prompt for credentials:i:0
negotiate security layer:i:1
remoteapplicationmode:i:0
alternate shell:s:
shell working directory:s:
gatewayhostname:s:
gatewayusagemethod:i:4
gatewaycredentialssource:i:4
gatewayprofileusagemethod:i:0
promptcredentialonce:i:0
gatewaybrokeringtype:i:0
use redirection server name:i:0
rdgiskdcproxy:i:0
kdcproxyname:s:"""
                rdpgw_fixed = """full address:s:%s
gatewayhostname:s:%s:%s
gatewayaccesstoken:s:%s
username:s:%s
password:s:%s"""
                rdpgw_default = """enableworkspacereconnect:i:0
disable wallpaper:i:0
allow desktop composition:i:0
disable full window drag:i:1
disable menu anims:i:1
disable themes:i:0
disable cursor setting:i:0
bitmapcachepersistenable:i:1
audiomode:i: value:0
redirectprinters:i:1
redirectcomports:i:0
redirectsmartcards:i:1
redirectclipboard:i:1
redirectposdevices:i:0
drivestoredirect:s:
autoreconnection enabled:i:1
authentication level:i:2
prompt for credentials:i:0
negotiate security layer:i:1
remoteapplicationmode:i:0
alternate shell:s:
shell working directory:s:
gatewayusagemethod:i:1
gatewaycredentialssource:i:5
gatewayprofileusagemethod:i:1
networkautodetect:i:1
bandwidthautodetect:i:1
promptcredentialonce:i:0
gatewaybrokeringtype:i:0
use redirection server name:i:0
rdgiskdcproxy:i:0
kdcproxyname:s:
connection type:i:6
domain:s:
allow font smoothing:i:1
bitmapcachesize:i:32000
smart sizing:i:1"""
                spice_fixed = """[virt-viewer]
type=%s
proxy=http://%s:%s
host=%s
password=%s
tls-port=%s
fullscreen=%s
title=%s:%sd - Prem SHIFT+F12 per sortir"""
                spice_default = """
enable-smartcard=0
enable-usb-autoshare=1
delete-this-file=1
usb-filter=-1,-1,-1,-1,0
tls-ciphers=DEFAULT
toggle-fullscreen=shift+f11
release-cursor=shift+f12
secure-attention=ctrl+alt+end
secure-channels=main;inputs;cursor;playback;record;display;usbredir;smartcard"""
                r.table(table).update(
                    {
                        "viewers": {
                            "file_rdpvpn": {
                                "viewer": "RDP VPN",
                                "key": "file_rdpvpn",
                                "fixed": rdp_fixed,
                                "default": rdp_default.strip(),
                                "custom": rdp_default.strip(),
                            },
                            "file_rdpgw": {
                                "viewer": "RDP",
                                "key": "file_rdpgw",
                                "fixed": rdpgw_fixed,
                                "default": rdpgw_default.strip(),
                                "custom": rdpgw_default.strip(),
                            },
                            "file_spice": {
                                "viewer": "SPICE",
                                "key": "file_spice",
                                "fixed": spice_fixed,
                                "default": spice_default.strip(),
                                "custom": spice_default.strip(),
                            },
                        }
                    }
                ).run(self.conn)
            except Exception as e:
                log.error(
                    "Could not update table "
                    + table
                    + " conversion fields for db version "
                    + str(version)
                    + "!"
                )
                log.error("Error detail: " + str(e))

        if version == 129:
            try:
                d["maintenance_text"] = {}
                d["maintenance_text"][
                    "title"
                ] = "Currently, Isard service is under maintenance"
                d["maintenance_text"][
                    "body"
                ] = "The service is going to be available again in a few minutes\nSorry for the inconvenience"
                d["maintenance_text"]["enabled"] = False
                r.table(table).update(d).run(self.conn)
            except Exception as e:
                log.error(
                    "Could not update table "
                    + table
                    + " conversion fields for db version "
                    + str(version)
                    + "!"
                )
                log.error(e)
                log.error("Error detail: " + str(e))

        if version == 140:
            try:
                rdp_fixed = """full address:s:%s
username:s:%s
password:s:%s"""
                r.table(table).update(
                    {
                        "viewers": {
                            "file_rdpvpn": {
                                "fixed": rdp_fixed,
                            },
                        }
                    }
                ).run(self.conn)
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

        if version == 66:
            try:
                r.table("gpus").index_create("name").run(self.conn)
            except Exception as e:
                print(e)

        if version == 69:
            try:
                r.table(table).update({"buffering_hyper": False}).run(self.conn)

            except Exception as e:
                log.error(
                    "Could not update table "
                    + table
                    + " conversion fields for db version "
                    + str(version)
                    + "!"
                )
                log.error("Error detail: " + str(e))

        if version == 70:
            try:
                r.table(table).update({"destroy_time": None}).run(self.conn)

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
        if version == 64:
            hypervisors = {}
            for hypervisor_pool in r.table("hypervisors_pools").run(self.conn):
                if not hypervisor_pool.get("paths"):
                    continue
                if hypervisor_pool["id"] == "default":
                    storage_pool_id = DEFAULT_STORAGE_POOL_ID
                else:
                    storage_pool_id = str(uuid4())
                storage_pool = {
                    "id": storage_pool_id,
                    "name": hypervisor_pool["id"],
                    "paths": {
                        "desktop": [],
                        "media": [],
                        "template": [],
                        "volatile": [],
                    },
                }
                for path_type, paths in hypervisor_pool.get("paths", {}).items():
                    if path_type == "bases":
                        continue
                    if path_type == "groups":
                        path_type = "desktop"
                    if path_type == "templates":
                        path_type = "template"
                    for path in paths:
                        storage_pool["paths"][path_type].append(
                            {
                                "path": path["path"],
                                "weight": path["weight"],
                            }
                        )
                        for hypervisor_id in path["disk_operations"]:
                            hypervisors.setdefault(hypervisor_id, set())
                            hypervisors[hypervisor_id].add(storage_pool_id)
                r.table("storage_pool").insert(storage_pool, conflict="update").run(
                    self.conn
                )
                r.table("hypervisors_pools").get(hypervisor_pool["id"]).replace(
                    r.row.without({"paths"})
                ).run(self.conn)
            for hypervisor_id, storage_pool_ids in hypervisors.items():
                r.table("hypervisors").get(hypervisor_id).update(
                    {"storage_pools": storage_pool_ids}
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

        if version == 61:
            r.table(table).filter(
                lambda domain: r.not_(domain.has_fields({"tag"}))
            ).update({"tag": False, "tag_name": False, "tag_visible": False}).run(
                self.conn
            )
            try:
                r.table("domains").index_create(
                    "kind_user_tag",
                    [r.row["kind"], r.row["user"], r.row["tag"]],
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 66:
            try:
                r.table(table).index_create(
                    "name_user", [r.row["name"], r.row["user"]]
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 73:
            r.table(table).update({"favourite_hyp": False}).run(self.conn)

        if version == 75:
            domains_interfaces = list(
                r.table(table)
                .get_all("desktop", index="kind")
                .pluck("id", {"create_dict": {"hardware": {"interfaces_mac": True}}})
                .run(self.conn)
            )
            hardware_macs = [
                {
                    "id": dom["id"],
                    "interfaces": dom["create_dict"]["hardware"]["interfaces_mac"],
                }
                for dom in domains_interfaces
                if dom.get("create_dict").get("hardware").get("interfaces_mac")
            ]
            all_macs = [
                element
                for innerList in hardware_macs
                for element in innerList["interfaces"]
            ]
            ids_to_replace_macs = []
            macs_found = []
            for h in hardware_macs:
                for interface in h["interfaces"]:
                    if all_macs.count(interface) > 1:
                        if interface not in macs_found:
                            macs_found.append(interface)
                        else:
                            ids_to_replace_macs.append(h["id"])
            if len(ids_to_replace_macs):
                print(
                    "UPGRADE WARNING: Found "
                    + str(len(ids_to_replace_macs))
                    + " duplicated. Updating domins macs..."
                )
                for id in ids_to_replace_macs:
                    macs = (
                        r.table(table)
                        .get(id)
                        .pluck(
                            {
                                "create_dict": {
                                    "hardware": {"interfaces_mac", "interfaces"}
                                }
                            }
                        )
                        .run(self.conn)
                    )
                    old_interfaces_macs = (
                        macs.get("create_dict", {})
                        .get("hardware", {})
                        .get("interfaces_mac")
                    )
                    if old_interfaces_macs:
                        print("Updating macs in desktop " + id)
                        new_interfaces_macs = []
                        new_macs = {}
                        for iname in macs["create_dict"]["hardware"]["interfaces"]:
                            generated = gen_new_mac()
                            new_interfaces_macs.append(generated)
                            new_macs[iname] = generated
                        r.table(table).get(id).update(
                            {
                                "create_dict": {
                                    "macs": new_macs,
                                    "hardware": {
                                        "interfaces_mac": new_interfaces_macs,
                                    },
                                }
                            }
                        ).run(self.conn)
            else:
                print("No duplicate macs found during upgrade")

        if version == 77:
            try:
                r.table(table).index_drop("wg_mac").run(self.conn)
                r.table(table).index_create(
                    "wg_mac", [r.row["kind"], r.row["create_dict"]["macs"]["wireguard"]]
                ).run(self.conn)
            except:
                None

        if version == 78:
            try:
                self.del_keys(table, ["status_logs"])
            except:
                None

        if version == 80:
            try:
                r.table(table).index_create(
                    "tag_status", [r.row["tag"], r.row["status"]]
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 83:
            try:
                r.table(table).filter(
                    lambda domain: r.not_(domain.has_fields("accessed"))
                ).update({"accessed": r.row["history_domain"][-1]["when"]}).run(
                    self.conn
                )
            except Exception as e:
                print(e)

        if version == 84:
            try:
                templates = list(
                    r.table("domains")
                    .get_all("template", index="kind")
                    .pluck(
                        "id", "accessed", {"create_dict": {"hardware": {"disks": True}}}
                    )
                    .run(self.conn)
                )
                templates_dict = {}
                for d in templates:
                    for disk in d["create_dict"]["hardware"]["disks"]:
                        if (
                            disk.get("storage_id", disk.get("file"))
                            not in templates_dict
                        ):
                            templates_dict[disk.get("storage_id", disk.get("file"))] = [
                                d
                            ]
                        else:
                            templates_dict[
                                disk.get("storage_id", disk.get("file"))
                            ].append(d)
                duplicated = [t for t in templates_dict if len(templates_dict[t]) > 1]

                duplicated = [
                    templates_dict[t]
                    for t in templates_dict
                    if len(templates_dict[t]) > 1
                ]

                for templates in duplicated:
                    if len(templates) > 1:
                        # assume parent is the one with oldest accessed time
                        min_accessed_template = min(
                            templates, key=lambda t: t["accessed"]
                        )
                        for t in templates:
                            if t != min_accessed_template:
                                # update every duplicated with new duplicate_parent_template
                                r.table("domains").get(t["id"]).update(
                                    {
                                        "duplicate_parent_template": min_accessed_template[
                                            "id"
                                        ]
                                    }
                                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 85:
            try:
                r.table(table).index_drop("parents").run(self.conn)
                r.table(table).index_create("parents", multi=True).run(self.conn)
                r.table(table).index_wait("parents").run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create("duplicate_parent_template").run(self.conn)
                r.table(table).index_wait("duplicate_parent_template").run(self.conn)
            except Exception as e:
                print(e)

        if version == 86:
            try:
                duplicated = list(
                    r.table(table)
                    .has_fields("duplicate_parent_template")
                    .run(self.conn)
                )
                for d in duplicated:
                    try:
                        parents = (
                            r.table("domains")
                            .get(d["duplicate_parent_template"])
                            .pluck("parents")["parents"]
                            .run(self.conn)
                        )
                        r.table(table).get(d["id"]).update({"parents": parents}).run(
                            self.conn
                        )
                    except:
                        print(
                            "Unable to update duplicated template "
                            + d["id"]
                            + " with parents"
                        )
            except Exception as e:
                print(e)

        if version == 87:
            pass
            # try:
            #     r.table(table).index_create(
            #         "guest_ip", [r.row["status"], r.row["viewer"]["guest_ip"]]
            #     ).run(self.conn)
            #     r.table(table).index_create(
            #         "proxies",
            #         [
            #             r.row["status"],
            #             r.row["viewer"]["proxy_video"],
            #             r.row["viewer"]["proxy_hyper_host"],
            #         ],
            #     ).run(self.conn)
            # except:
            #     print(e)

        if version == 88:
            try:
                r.table(table).index_drop("guest_ip").run(self.conn)
                # r.table(table).index_drop("proxies").run(self.conn)
            except:
                None
            try:
                r.table(table).index_create(
                    "guest_ip", r.row["viewer"]["guest_ip"]
                ).run(self.conn)
                # r.table(table).index_create(
                #     "proxies",
                #     [
                #         r.row["viewer"]["proxy_video"],
                #         r.row["viewer"]["proxy_hyper_host"],
                #     ],
                # ).run(self.conn)
            except:
                print(e)

        if version == 89:
            try:
                r.table(table).index_drop("proxies").run(self.conn)
            except:
                None
            try:
                r.table(table).index_create(
                    "proxies",
                    [
                        r.row["viewer"]["proxy_video"],
                        r.row["viewer"]["html5_ext_port"],
                        r.row["viewer"]["proxy_hyper_host"],
                    ],
                ).run(self.conn)
            except:
                print(e)

        if version == 90:
            try:
                r.table("domains").get_all(
                    r.args(["Stopped", "Failed"]), index="status"
                ).has_fields("viewer").replace(r.row.without("viewer")).run(self.conn)
            except:
                print(e)

        if version == 95:
            try:
                for d in r.table(table).has_fields("url-isard").run(self.conn):
                    if d.get("url-isard"):
                        download_id = d.pop("id")
                        r.table(table).get(download_id).delete().run(self.conn)
                        r.table(table).insert(d).run(self.conn)
                r.table(table).index_create("url-isard").run(self.conn)
                r.table(table).index_create("url-web").run(self.conn)
            except Exception as e:
                print(e)

        if version == 96:
            try:
                domains_to_update = list(
                    r.table("domains")
                    .pluck(
                        {
                            "id": True,
                            "create_dict": {
                                "hardware": {"interfaces": True, "interfaces_mac": True}
                            },
                        }
                    )
                    .run(self.conn)
                )
                if len(domains_to_update):
                    all_macs = (
                        r.table("domains")
                        .pluck({"create_dict": {"hardware": {"interfaces_mac": True}}})[
                            "create_dict"
                        ]["hardware"]["interfaces_mac"]
                        .default([])
                        .reduce(lambda left, right: left.add(right))
                        .distinct()
                        .run(self.conn)
                    )

                    updated_domains = []
                    for domain in domains_to_update:
                        if not domain["create_dict"]["hardware"].get("interfaces"):
                            continue
                        if not domain["create_dict"]["hardware"].get("interfaces_mac"):
                            domain["create_dict"]["hardware"]["interfaces_mac"] = []
                        if not (
                            len(domain["create_dict"]["hardware"]["interfaces"])
                            == len(
                                domain["create_dict"]["hardware"].get(
                                    "interfaces_mac", []
                                )
                            )
                        ):
                            for i in range(
                                0,
                                len(domain["create_dict"]["hardware"]["interfaces"])
                                - len(
                                    domain["create_dict"]["hardware"].get(
                                        "interfaces_mac", []
                                    )
                                ),
                            ):
                                new_mac = gen_random_mac()
                                while all_macs.count(new_mac) > 0:
                                    new_mac = gen_random_mac()
                                all_macs.append(new_mac)
                                domain["create_dict"]["hardware"][
                                    "interfaces_mac"
                                ].append(new_mac)
                        interfaces = {
                            interface: mac
                            for interface, mac in zip(
                                domain["create_dict"]["hardware"]["interfaces"],
                                domain["create_dict"]["hardware"]["interfaces_mac"],
                            )
                        }
                        domain["create_dict"]["hardware"].pop("interfaces_mac")
                        domain["create_dict"]["hardware"].pop("macs", None)
                        domain["create_dict"]["hardware"]["interfaces"] = interfaces
                        updated_domains.append(domain)
                    r.table("domains").insert(updated_domains, conflict="update").run(
                        self.conn
                    )
                    r.table("domains").replace(
                        r.row.without(
                            {
                                "create_dict": {
                                    "macs": True,
                                    "hardware": {"interfaces_mac": True},
                                }
                            }
                        )
                    ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 97:
            try:
                r.table(table).index_drop("wg_mac").run(self.conn)
                r.table(table).index_create(
                    "wg_mac",
                    [
                        r.row["kind"],
                        r.row["create_dict"]["hardware"]["interfaces"]["wireguard"],
                    ],
                ).run(self.conn)
            except:
                None

        if version == 98:
            try:
                domains_to_update = list(
                    r.db("isard")
                    .table("domains")
                    .get_all("desktop", index="kind")
                    .pluck(
                        {"id": True, "create_dict": {"hardware": {"interfaces": True}}}
                    )
                    .filter(
                        lambda d: d["create_dict"]["hardware"]["interfaces"]
                        .type_of()
                        .eq("ARRAY")
                    )
                    .run(self.conn)
                )
                if len(domains_to_update):
                    all_macs = (
                        r.table("domains")
                        .pluck({"create_dict": {"hardware": {"interfaces": True}}})[
                            "create_dict"
                        ]["hardware"]["interfaces"]
                        .filter(lambda d: d.type_of().ne("ARRAY"))
                        .concat_map(lambda x: x.values())
                        .default([])
                        .distinct()
                        .run(self.conn)
                    )

                    updated_domains = []
                    for domain in domains_to_update:
                        if not domain["create_dict"]["hardware"].get("interfaces"):
                            continue
                        if not domain["create_dict"]["hardware"].get("interfaces_mac"):
                            domain["create_dict"]["hardware"]["interfaces_mac"] = []
                        if not (
                            len(domain["create_dict"]["hardware"]["interfaces"])
                            == len(
                                domain["create_dict"]["hardware"].get(
                                    "interfaces_mac", []
                                )
                            )
                        ):
                            for i in range(
                                0,
                                len(domain["create_dict"]["hardware"]["interfaces"])
                                - len(
                                    domain["create_dict"]["hardware"].get(
                                        "interfaces_mac", []
                                    )
                                ),
                            ):
                                new_mac = gen_random_mac()
                                while all_macs.count(new_mac) > 0:
                                    new_mac = gen_random_mac()
                                all_macs.append(new_mac)
                                domain["create_dict"]["hardware"][
                                    "interfaces_mac"
                                ].append(new_mac)
                        interfaces = {
                            interface: mac
                            for interface, mac in zip(
                                domain["create_dict"]["hardware"]["interfaces"],
                                domain["create_dict"]["hardware"]["interfaces_mac"],
                            )
                        }
                        domain["create_dict"]["hardware"].pop("interfaces_mac")
                        domain["create_dict"]["hardware"].pop("macs", None)
                        domain["create_dict"]["hardware"]["interfaces"] = interfaces
                        updated_domains.append(domain)
                    r.table("domains").insert(updated_domains, conflict="update").run(
                        self.conn
                    )
                    r.table("domains").replace(
                        r.row.without(
                            {
                                "create_dict": {
                                    "macs": True,
                                    "hardware": {"interfaces_mac": True},
                                }
                            }
                        )
                    ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 99:
            try:
                domains_to_update = list(
                    r.db("isard")
                    .table("domains")
                    .get_all("desktop", index="kind")
                    .pluck(
                        {"id": True, "create_dict": {"hardware": {"interfaces": True}}}
                    )
                    .filter(
                        lambda d: d["create_dict"]["hardware"]["interfaces"]
                        .type_of()
                        .eq("ARRAY")
                    )["id"]
                    .run(self.conn)
                )
                if len(domains_to_update):
                    r.table("domains").get_all(*domains_to_update).replace(
                        r.row.without(
                            {"create_dict": {"hardware": {"interfaces": True}}}
                        )
                    ).run(self.conn)
                    r.table("domains").get_all(*domains_to_update).update(
                        {"create_dict": {"hardware": {"interfaces": {}}}}
                    ).run(self.conn)

            except Exception as e:
                print(e)

        if version == 100:
            try:
                blank_space_interfaces = list(
                    r.table("interfaces")
                    .filter(lambda interface: interface["id"].match("^ "))
                    .run(self.conn)
                )
                for interface in blank_space_interfaces:
                    trim_interface = interface.pop("id").strip()
                    interface["name"] = interface.get("name").strip()
                    new_interface_id = (
                        r.table("interfaces")
                        .insert(interface, return_changes=True)["changes"]["new_val"][
                            "id"
                        ]
                        .run(self.conn)
                    )[0]

                    domains_with_blank_space_interface = list(
                        r.table("domains")
                        .has_fields(
                            {
                                "create_dict": {
                                    "hardware": {"interfaces": {trim_interface: True}}
                                }
                            }
                        )
                        .pluck("id")["id"]
                        .run(self.conn)
                    )

                    r.table("domains").get_all(
                        *domains_with_blank_space_interface
                    ).update(
                        {
                            "create_dict": {
                                "hardware": {
                                    "interfaces": {
                                        new_interface_id: r.row["create_dict"][
                                            "hardware"
                                        ]["interfaces"][trim_interface]
                                    }
                                }
                            }
                        }
                    ).run(
                        self.conn
                    )
                    r.table("domains").get_all(
                        *domains_with_blank_space_interface
                    ).replace(
                        r.row.without(
                            {
                                "create_dict": {
                                    "hardware": {"interfaces": {trim_interface: True}}
                                }
                            }
                        )
                    ).run(
                        self.conn
                    )

                r.table("interfaces").filter(
                    lambda interface: interface["id"].match("^ ")
                ).delete().run(self.conn)

            except Exception as e:
                print(e)

        if version == 101:
            try:
                domains_to_update = list(
                    r.table("domains")
                    .pluck(
                        {
                            "id": True,
                            "hardware": {"interfaces": True},
                            "create_dict": {"hardware": {"interfaces": True}},
                        }
                    )
                    .run(self.conn)
                )

                updated_domains = []
                for domain in domains_to_update:
                    new_interfaces = []
                    if not domain["create_dict"]["hardware"].get("interfaces"):
                        continue
                    if not domain["hardware"].get("interfaces"):
                        en_ifs = []
                    else:
                        en_ifs = [
                            interface["mac"]
                            for interface in domain["hardware"]["interfaces"]
                        ]
                    ui_ifs = [
                        mac
                        for mac in domain["create_dict"]["hardware"][
                            "interfaces"
                        ].values()
                    ]
                    if en_ifs == ui_ifs:
                        # Has been updated, so create new default order
                        if (
                            "default"
                            in domain["create_dict"]["hardware"]["interfaces"].keys()
                        ):
                            new_interfaces.append(
                                {
                                    "id": "default",
                                    "mac": domain["create_dict"]["hardware"][
                                        "interfaces"
                                    ]["default"],
                                }
                            )
                            domain["create_dict"]["hardware"]["interfaces"].pop(
                                "default"
                            )
                        if (
                            "wireguard"
                            in domain["create_dict"]["hardware"]["interfaces"].keys()
                        ):
                            new_interfaces.append(
                                {
                                    "id": "wireguard",
                                    "mac": domain["create_dict"]["hardware"][
                                        "interfaces"
                                    ]["wireguard"],
                                }
                            )
                            domain["create_dict"]["hardware"]["interfaces"].pop(
                                "wireguard"
                            )
                        for interface in domain["create_dict"]["hardware"][
                            "interfaces"
                        ]:
                            new_interfaces.append(
                                {
                                    "id": interface,
                                    "mac": domain["create_dict"]["hardware"][
                                        "interfaces"
                                    ][interface],
                                }
                            )
                    else:
                        # user en_ifs to construct the new_interfaces
                        for mac in en_ifs:
                            for interface in domain["create_dict"]["hardware"][
                                "interfaces"
                            ]:
                                if (
                                    domain["create_dict"]["hardware"]["interfaces"][
                                        interface
                                    ]
                                    == mac
                                ):
                                    new_interfaces.append({"id": interface, "mac": mac})

                    domain["create_dict"]["hardware"]["interfaces"] = new_interfaces
                    domain["hardware"].pop("interfaces", None)
                    updated_domains.append(domain)
                r.table("domains").insert(updated_domains, conflict="update").run(
                    self.conn
                )

                r.table(table).index_drop("wg_mac").run(self.conn)
                r.table(table).index_create(
                    "wg_mac",
                    lambda domain: domain["create_dict"]["hardware"][
                        "interfaces"
                    ].concat_map(lambda data: [data["mac"]]),
                    multi=True,
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 102:
            try:
                domains_to_update = list(
                    r.table("domains")
                    .filter(
                        r.row["create_dict"]["hardware"]["interfaces"].type_of()
                        == "OBJECT"
                    )
                    .merge(
                        lambda domain: {"create_dict": {"hardware": {"interfaces": []}}}
                    )
                    .pluck(
                        {
                            "id": True,
                            "create_dict": {"hardware": {"interfaces": True}},
                        }
                    )
                    .run(self.conn)
                )
                r.table("domains").insert(domains_to_update, conflict="update").run(
                    self.conn
                )
            except Exception as e:
                print(e)

        if version == 109:
            storages_to_check = []

            incorrect_storages_ids = list(
                r.table("storage")
                .filter(~r.row.has_fields("user_id"))["id"]
                .run(self.conn)
            )

            print(
                "--- Deleted {} storages created incorrectly in previous upgrades ---".format(
                    len(incorrect_storages_ids)
                )
            )
            r.table("storage").get_all(incorrect_storages_ids).delete().run(self.conn)

            try:
                print(
                    "--- Getting nonpersistent domains with old file path in [create_dict][hardware][disks] ---"
                )
                nonpersistent_with_old_file = list(
                    r.table("domains")
                    .pluck(
                        {
                            "id": True,
                            "user": True,
                            "parents": True,
                            "create_dict": {"hardware": {"disks": True}},
                            "persistent": True,
                        }
                    )
                    .filter(
                        (r.row.has_fields("persistent"))
                        & (r.row["persistent"] == False)
                        & (
                            r.row["create_dict"]["hardware"]["disks"][0].has_fields(
                                "file"
                            )
                        )
                    )["id"]
                    .run(self.conn)
                )

                print(
                    "Found {} nonpersistent desktops with old file path, deleting them".format(
                        len(nonpersistent_with_old_file)
                    )
                )

                r.table("domains").get_all(
                    r.args(nonpersistent_with_old_file)
                ).delete().run(self.conn)
            except Exception as e:
                print(e)

            try:
                print(
                    "--- Getting nonpersistent domains with storages migrating or deleted ---"
                )
                nonpersistent_storage_migrating_or_deleted = list(
                    r.table("domains")
                    .filter(
                        (r.row.has_fields("persistent"))
                        & (r.row["persistent"] == False)
                    )
                    .eq_join(
                        r.row["create_dict"]["hardware"]["disks"][0]["storage_id"],
                        r.table("storage"),
                    )
                    .filter(
                        lambda storage: r.expr(["migrating", "deleted"]).contains(
                            storage["right"]["status"]
                        )
                    )
                    .pluck("right")["right"]["id"]
                    .distinct()
                    .run(self.conn)
                )

                nonpersistent_domains_migrating_or_deleted = list(
                    r.table("domains")
                    .get_all(
                        r.args(nonpersistent_storage_migrating_or_deleted),
                        index="storage_ids",
                    )["id"]
                    .run(self.conn)
                )

                print(
                    "Deleting %s nonpersistent domains with storage migrating or deleted"
                    % len(nonpersistent_domains_migrating_or_deleted)
                )

                r.table("domains").get_all(
                    r.args(nonpersistent_domains_migrating_or_deleted)
                ).delete().run(self.conn)

                print(
                    "Generating tasks for %s incorrectly created storages to set them as deleted"
                    % len(nonpersistent_storage_migrating_or_deleted)
                )
                storages_to_check = (
                    storages_to_check + nonpersistent_storage_migrating_or_deleted
                )
            except Exception as e:
                print(e)

            try:
                print(
                    "--- Nonpersistent domains with storage_id in [create_dict][hardware][disks] that don't exist in the db ---"
                )
                nonpersistent_without_storage = list(
                    r.table("domains")
                    .pluck(
                        {
                            "id": True,
                            "user": True,
                            "parents": True,
                            "kind": True,
                            "persistent": True,
                            "create_dict": {"hardware": {"disks": True}},
                        }
                    )
                    .filter(
                        lambda domain: r.table("storage")
                        .get_all(
                            domain["create_dict"]["hardware"]["disks"][0]["storage_id"]
                        )
                        .count()
                        .eq(0)
                    )
                    .filter(
                        (r.row.has_fields("persistent"))
                        & (r.row["persistent"] == False)
                    )["id"]
                    .run(self.conn)
                )

                print(
                    "Deleting {} nonpersistent desktop without storage".format(
                        len(nonpersistent_without_storage)
                    )
                )

                r.table("domains").get_all(
                    r.args(nonpersistent_without_storage)
                ).delete().run(self.conn)
            except Exception as e:
                print(e)

            try:
                print(
                    "--- Getting persistent domains with old file path in [create_dict][hardware][disks] ---"
                )
                domains_with_file_path = list(
                    r.table("domains")
                    .pluck(
                        {
                            "id": True,
                            "user": True,
                            "parents": True,
                            "create_dict": {"hardware": {"disks": True}},
                        }
                    )
                    .filter(
                        r.row["create_dict"]["hardware"]["disks"][0].has_fields("file")
                    )
                    .run(self.conn)
                )

                domains_to_update = []
                storages_to_insert = []
                storages = {}

                # Extract the data from the file to insert the new storage onto the db.
                for domain in domains_with_file_path:
                    old_disk = domain["create_dict"]["hardware"]["disks"][0]
                    base_name = os.path.splitext(old_disk["file"])
                    fmt = base_name[1][1:]
                    directory_path = "/".join(old_disk["file"].split("/")[:3])
                    uuid = os.path.relpath(base_name[0], directory_path + "/")
                    if not storages.get(old_disk["file"]):
                        storages[old_disk["file"]] = uuid
                        storages_to_insert.append(
                            {
                                "id": uuid,
                                "directory_path": directory_path,
                                "status": "migrating",
                                "type": fmt,
                                "user_id": domain["user"],
                                "status_logs": [
                                    {"status": "created", "time": int(time.time())}
                                ],
                            }
                        )
                    # Update the domain with the new storage_id
                    domains_to_update.append(
                        {
                            "id": domain["id"],
                            "create_dict": {
                                "hardware": {
                                    "disks": [
                                        {
                                            "storage_id": uuid,
                                        }
                                    ]
                                }
                            },
                        }
                    )

                print(
                    "Inserting %s new storages with the data retrieved from [hardware][disks] file info"
                    % len(storages_to_insert)
                )
                r.table("storage").insert(storages_to_insert).run(self.conn)
                print(
                    "Updating %s domains setting their new generated storage_id in [create_dict][hardware][disks]"
                    % len(domains_to_update)
                )
                r.table("domains").insert(domains_to_update, conflict="update").run(
                    self.conn
                )

                print(
                    "WARNING: Adding tasks to check %s storages in the next minutes."
                    % len(storages_to_insert)
                )

                # Generate check task
                for storage_to_insert in storages_to_insert:
                    storages_to_check.append(storage_to_insert["id"])
            except Exception as e:
                print(e)

            try:
                print(
                    "--- Getting domains with storages migrating or deleted with file in [hardware][disks] ---"
                )
                storages_ids_to_remove = list(
                    r.table("domains")
                    .filter(
                        (r.row["hardware"]["disks"][0].has_fields("file"))
                        & (~r.row["hardware"]["disks"][0].has_fields("storage_id"))
                    )
                    .eq_join(
                        r.row["create_dict"]["hardware"]["disks"][0]["storage_id"],
                        r.table("storage"),
                    )
                    .filter(
                        lambda storage: r.expr(["migrating", "deleted"]).contains(
                            storage["right"]["status"]
                        )
                    )
                    .pluck("right")["right"]["id"]
                    .distinct()
                    .run(self.conn)
                )

                # Exclude storages migrating from first insert in the upgrade
                storages_ids_to_remove = [
                    i for i in storages_ids_to_remove if i not in storages.values()
                ]

                domains_with_file_path = list(
                    r.table("domains")
                    .get_all(r.args(storages_ids_to_remove), index="storage_ids")
                    .pluck(
                        {
                            "id": True,
                            "user": True,
                            "kind": True,
                            "parents": True,
                            "hardware": {"disks": True},
                        }
                    )
                    .run(self.conn)
                )

                domains_to_update = []
                storages_to_insert = []
                storages = {}

                # Extract the data from the file to insert the new storage onto the db.
                for domain in domains_with_file_path:
                    old_disk = domain["hardware"]["disks"][0]
                    base_name = os.path.splitext(old_disk["file"])
                    fmt = base_name[1][1:]
                    directory_path = "/".join(old_disk["file"].split("/")[:3])
                    uuid = os.path.relpath(base_name[0], directory_path + "/")

                    if not storages.get(old_disk["file"]):
                        storages[old_disk["file"]] = uuid
                        existing_storage = r.table("storage").get(uuid).run(self.conn)
                        if (
                            existing_storage
                            and existing_storage["directory_path"] == directory_path
                        ):
                            continue
                        else:
                            storages_to_insert.append(
                                {
                                    "id": uuid,
                                    "directory_path": directory_path,
                                    "status": "migrating",
                                    "type": fmt,
                                    "user_id": domain["user"],
                                    "status_logs": [
                                        {"status": "created", "time": int(time.time())}
                                    ],
                                }
                            )
                    # Update the domain with the new storage_id
                    domains_to_update.append(
                        {
                            "id": domain["id"],
                            "create_dict": {
                                "hardware": {
                                    "disks": [
                                        {
                                            "storage_id": uuid,
                                        }
                                    ]
                                }
                            },
                        }
                    )

                print(
                    "Generating tasks for %s incorrectly created storages to set them as deleted"
                    % len(storages_ids_to_remove)
                )

                # Generate check task
                storages_to_check = storages_to_check + storages_ids_to_remove

                print(
                    "Inserting %s new storages with the data retrieved from [hardware][disks] file info"
                    % len(storages_to_insert)
                )
                r.table("storage").insert(storages_to_insert).run(self.conn)
                print(
                    "Updating %s domains setting their new generated storage_id in [create_dict][hardware][disks]"
                    % len(domains_to_update)
                )
                r.table("domains").insert(domains_to_update, conflict="update").run(
                    self.conn
                )

                print(
                    "WARNING: Adding tasks to check %s storages in the next minutes."
                    % len(storages_to_insert)
                )

                # Generate check task
                for storage_to_insert in storages_to_insert:
                    storages_to_check.append(storage_to_insert["id"])
            except Exception as e:
                print(e)

            try:
                print(
                    "--- Getting domains with storages migrating or deleted with 'storage_id' in [hardware][disks] ---"
                )
                storages_to_generate_task = list(
                    r.table("domains")
                    .filter(
                        (r.row["hardware"]["disks"][0].has_fields("storage_id"))
                        & (~r.row["hardware"]["disks"][0].has_fields("file"))
                    )
                    .eq_join(
                        r.row["create_dict"]["hardware"]["disks"][0]["storage_id"],
                        r.table("storage"),
                    )
                    .filter(
                        lambda storage: r.expr(["migrating", "deleted"]).contains(
                            storage["right"]["status"]
                        )
                    )
                    .pluck("right")["right"]["id"]
                    .run(self.conn)
                )

                print(
                    "WARNING: Adding tasks to check %s storages in the next minutes."
                    % len(storages_to_generate_task)
                )

                # Generate check task
                storages_to_check = storages_to_check + storages_to_generate_task
            except Exception as e:
                print(e)

            try:
                print(
                    "--- Persistent domains with storage_id in [create_dict][hardware][disks] that don't exist in the db ---"
                )
                domains_without_storage = list(
                    r.table("domains")
                    .pluck(
                        {
                            "id": True,
                            "user": True,
                            "parents": True,
                            "kind": True,
                            "create_dict": {"hardware": {"disks": True}},
                        }
                    )
                    .filter(
                        lambda domain: r.table("storage")
                        .get_all(
                            domain["create_dict"]["hardware"]["disks"][0]["storage_id"]
                        )
                        .count()
                        .eq(0)
                    )
                    .run(self.conn)
                )

                storages_to_insert = []

                # Extract the data from the file to insert the new storage onto the db.
                for domain in domains_without_storage:
                    storages_to_insert.append(
                        {
                            "id": domain["create_dict"]["hardware"]["disks"][0][
                                "storage_id"
                            ],
                            "directory_path": (
                                "/isard/groups"
                                if domain["kind"] == "desktop"
                                else "/isard/templates"
                            ),
                            "status": "migrating",
                            "type": "qcow2",
                            "user_id": domain["user"],
                            "status_logs": [
                                {"status": "created", "time": int(time.time())}
                            ],
                        }
                    )

                print(
                    "Inserting %s new storages with the id from [create_disk][hardware][disks]"
                    % len(storages_to_insert)
                )
                r.table("storage").insert(storages_to_insert).run(self.conn)

                print(
                    "WARNING: Adding tasks to check %s storages in the next minutes."
                    % len(storages_to_insert)
                )

                # Generate check task
                for storage_to_insert in storages_to_insert:
                    storages_to_check.append(storage_to_insert["id"])
            except Exception as e:
                print(e)

            try:
                other_status_disks = list(
                    r.table("storage")
                    .filter(
                        lambda storage: r.expr(["ready", "deleted"])
                        .contains(storage["status"])
                        .not_()
                    )
                    .pluck("id")["id"]
                    .run(self.conn)
                )
                print(
                    f"Got {len(other_status_disks)} storages not in ready nor deleted status to check"
                )
                storages_to_check = list(set(storages_to_check + other_status_disks))
                print(
                    f"Total storages to check after removing duplicates: {len(storages_to_check)}"
                )
            except Exception as e:
                print(e)

            try:
                print(f"Generating {len(storages_to_check)} tasks...")
                for storage_to_remove in storages_to_check:
                    # print(f"Generating task for storage {storage_to_remove}")
                    storage = Storage(storage_to_remove)
                    storage.check_backing_chain(
                        user_id="local-default-admin-admin", blocking=False
                    )
                if len(storages_to_insert):
                    for storage_to_insert in storages_to_insert:
                        storage = Storage(storage_to_insert["id"])
                        storage.check_backing_chain(
                            user_id="local-default-admin-admin", blocking=False
                        )
            except Exception as e:
                print(e)

        if version == 111:
            try:
                r.table(table).index_create(
                    "interfaces",
                    r.row["create_dict"]["hardware"]["interfaces"].concat_map(
                        lambda data: [data["id"]]
                    ),
                    multi=True,
                ).run(self.conn)
                r.table(table).index_wait("interfaces").run(self.conn)
            except Exception as e:
                pass
            try:
                r.table(table).index_create(
                    "videos",
                    r.row["create_dict"]["hardware"]["videos"],
                    multi=True,
                ).run(self.conn)
                r.table(table).index_wait("videos").run(self.conn)
            except Exception as e:
                pass
            try:
                r.table(table).index_create(
                    "boot_order",
                    r.row["create_dict"]["hardware"]["boot_order"],
                    multi=True,
                ).run(self.conn)
                r.table(table).index_wait("boot_order").run(self.conn)
            except Exception as e:
                pass
            try:
                r.table(table).index_create(
                    "vgpus", r.row["create_dict"]["reservables"]["vgpus"], multi=True
                ).run(self.conn)
                r.table(table).index_wait("vgpus").run(self.conn)
            except Exception as e:
                pass
            try:
                all_media = list(r.table("media").pluck("id")["id"].run(self.conn))
                domains_medias = list(
                    r.table("domains")
                    .pluck({"create_dict": {"hardware": {"isos": True}}})[
                        "create_dict"
                    ]["hardware"]["isos"]
                    .map(lambda x: x["id"])
                    .reduce(lambda left, right: left.add(right))
                    .distinct()
                    .run(self.conn)
                )
                for media_id in domains_medias:
                    if media_id not in all_media:
                        r.table("domains").get_all(media_id, index="media_ids").update(
                            {
                                "create_dict": {
                                    "hardware": {
                                        "isos": r.row["create_dict"]["hardware"][
                                            "isos"
                                        ].filter(lambda media: media["id"].ne(media_id))
                                    }
                                }
                            }
                        ).run(self.conn)
            except r.ReqlNonExistenceError:
                pass
            except Exception as e:
                print(e)
            try:
                all_interfaces = list(
                    r.table("interfaces").pluck("id")["id"].run(self.conn)
                )
                domains_interfaces = list(
                    r.table("domains")
                    .pluck({"create_dict": {"hardware": {"interfaces": True}}})[
                        "create_dict"
                    ]["hardware"]["interfaces"]
                    .map(lambda x: x["id"])
                    .reduce(lambda left, right: left.add(right))
                    .distinct()
                    .run(self.conn)
                )
                for i in domains_interfaces:
                    if i not in all_interfaces:
                        r.table("domains").get_all(i, index="interfaces").update(
                            {
                                "create_dict": {
                                    "hardware": {
                                        "interfaces": r.row["create_dict"]["hardware"][
                                            "interfaces"
                                        ].filter(
                                            lambda interface: interface["id"].ne(i)
                                        )
                                    }
                                }
                            }
                        ).run(self.conn)
            except r.ReqlNonExistenceError:
                pass
            except Exception as e:
                print(e)
            try:
                all_reservables = list(
                    r.table("reservables_vgpus").pluck("id")["id"].run(self.conn)
                )
                domains_reservables = list(
                    r.table("domains")
                    .filter(r.row["create_dict"]["reservables"].has_fields("vgpus"))
                    .pluck({"create_dict": {"reservables": True}})["create_dict"][
                        "reservables"
                    ]["vgpus"]
                    .reduce(lambda left, right: left.add(right))
                    .distinct()
                    .run(self.conn)
                )
                for reservable in domains_reservables:
                    if reservable not in all_reservables:
                        r.table("domains").get_all(reservable, index="vgpus").update(
                            {"create_dict": {"reservables": {"vgpus": None}}}
                        ).run(self.conn)
            except r.ReqlNonExistenceError:
                pass
            except Exception as e:
                print(e)

        if version == 114:
            try:
                domains_with_iso_string = list(
                    r.table("domains")
                    .filter(
                        lambda doc: doc["create_dict"]["hardware"]["isos"].contains(
                            lambda iso: iso.type_of().eq("STRING")
                        )
                    )
                    .run(self.conn)
                )

                print(
                    "Updating "
                    + str(len(domains_with_iso_string))
                    + " domains with iso as string"
                )

                updated_domains_ids = []

                for domain in domains_with_iso_string:
                    isos = [
                        json.loads(i.replace("&#39;", '"'))
                        for i in domain["create_dict"]["hardware"]["isos"]
                    ]
                    r.table("domains").get(domain["id"]).update(
                        {"create_dict": {"hardware": {"isos": isos}}}
                    ).run(self.conn)
                    updated_domains_ids.append(domain["id"])

                print("Domains ids updated: " + str(updated_domains_ids))
            except Exception as e:
                print(e)
        if version == 128:
            try:
                r.table("domains").get_all("desktop", index="kind").filter(
                    r.row.has_fields("persistent").not_()
                ).update({"persistent": True}).run(self.conn)
                r.table("domains").get_all("desktop", index="kind").filter(
                    r.row.has_fields("tag").not_()
                ).update({"tag": False}).run(self.conn)
            except Exception as e:
                print(e)

        if version == 134:
            try:
                r.table("domains").index_create(
                    "kind_autostart_status",
                    [r.row["kind"], r.row["server_autostart"], r.row["status"]],
                ).run(self.conn)
                r.table("domains").index_drop("serverstostart").run(self.conn)
                r.table("domains").index_create("server").run(self.conn)
                r.table("domains").index_wait("server").run(self.conn)
                r.table("domains").get_all(True, index="server").update(
                    {"server_autostart": True}
                ).run(self.conn)
            except Exception as e:
                print(e)

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

        if version == 66:
            try:
                r.table(table).index_create("name").run(self.conn)
            except Exception as e:
                print(e)

        if version == 82:
            try:
                deployments = (
                    r.table(table)
                    .merge(
                        lambda deployment: {
                            "user": r.table("users").get(deployment["user"])
                        }
                    )
                    .filter({"user": None})
                    .pluck("id")["id"]
                    .run(self.conn)
                )
                r.table(table).get_all(r.args(deployments)).delete().run(self.conn)
            except Exception as e:
                print(e)

        if version == 111:
            try:
                r.table("deployments").filter(
                    lambda d: d["create_dict"]["hardware"]["interfaces"]
                    .type_of()
                    .eq("OBJECT")
                ).update(
                    {
                        "create_dict": {
                            "hardware": {
                                "interfaces": r.row["create_dict"]["hardware"][
                                    "interfaces"
                                ].keys()
                            }
                        }
                    }
                ).run(
                    self.conn
                )
            except Exception as e:
                pass
            try:
                r.table(table).index_create(
                    "interfaces",
                    r.row["create_dict"]["hardware"]["interfaces"],
                    multi=True,
                ).run(self.conn)
                r.table(table).index_wait("interfaces").run(self.conn)
            except Exception as e:
                pass
            try:
                r.table(table).index_create(
                    "videos",
                    r.row["create_dict"]["hardware"]["videos"],
                    multi=True,
                ).run(self.conn)
                r.table(table).index_wait("videos").run(self.conn)
            except Exception as e:
                pass
            try:
                r.table(table).index_create(
                    "boot_order",
                    r.row["create_dict"]["hardware"]["boot_order"],
                    multi=True,
                ).run(self.conn)
                r.table(table).index_wait("boot_order").run(self.conn)
            except Exception as e:
                pass
            try:
                r.table(table).index_create(
                    "isos",
                    lambda domain: domain["create_dict"]["hardware"]["isos"].concat_map(
                        lambda data: [data["id"]]
                    ),
                    multi=True,
                ).run(self.conn)
                r.table(table).index_wait("isos").run(self.conn)
            except Exception as e:
                pass
            try:
                r.table(table).index_create(
                    "vgpus", r.row["create_dict"]["reservables"]["vgpus"], multi=True
                ).run(self.conn)
                r.table(table).index_wait("vgpus").run(self.conn)
            except Exception as e:
                pass
            try:
                all_media = list(r.table("media").pluck("id")["id"].run(self.conn))
                deployments_medias = list(
                    r.table("deployments")
                    .pluck({"create_dict": {"hardware": {"isos": True}}})[
                        "create_dict"
                    ]["hardware"]["isos"]
                    .map(lambda x: x["id"])
                    .reduce(lambda left, right: left.add(right))
                    .distinct()
                    .run(self.conn)
                )
                for media_id in deployments_medias:
                    if media_id not in all_media:
                        r.table("deployments").get_all(media_id, index="isos").update(
                            {
                                "create_dict": {
                                    "hardware": {
                                        "isos": r.row["create_dict"]["hardware"][
                                            "isos"
                                        ].filter(lambda media: media["id"].ne(media_id))
                                    }
                                }
                            }
                        ).run(self.conn)
            except r.ReqlNonExistenceError:
                pass
            except Exception as e:
                print(e)
            try:
                all_interfaces = list(
                    r.table("interfaces").pluck("id")["id"].run(self.conn)
                )
                deployments_interfaces = list(
                    r.table("deployments")
                    .pluck({"create_dict": {"hardware": {"interfaces": True}}})[
                        "create_dict"
                    ]["hardware"]["interfaces"]
                    .reduce(lambda left, right: left.add(right))
                    .distinct()
                    .run(self.conn)
                )
                for i in deployments_interfaces:
                    if i not in all_interfaces:
                        r.table("deployments").get_all(i, index="interfaces").update(
                            {
                                "create_dict": {
                                    "hardware": {
                                        "interfaces": r.row["create_dict"]["hardware"][
                                            "interfaces"
                                        ].filter(lambda interface: interface.ne(i))
                                    }
                                }
                            }
                        ).run(self.conn)
            except r.ReqlNonExistenceError:
                pass
            except Exception as e:
                print(e)
            try:
                all_reservables = list(
                    r.table("reservables_vgpus").pluck("id")["id"].run(self.conn)
                )
                deployments_reservables = list(
                    r.table("deployments")
                    .filter(r.row["create_dict"]["reservables"].has_fields("vgpus"))
                    .pluck({"create_dict": {"reservables": True}})["create_dict"][
                        "reservables"
                    ]["vgpus"]
                    .reduce(lambda left, right: left.add(right))
                    .distinct()
                    .run(self.conn)
                )
                for reservable in deployments_reservables:
                    if reservable not in all_reservables:
                        r.table("deployments").get_all(
                            reservable, index="vgpus"
                        ).update({"create_dict": {"reservables": {"vgpus": None}}}).run(
                            self.conn
                        )
            except r.ReqlNonExistenceError:
                pass
            except Exception as e:
                print(e)

        if version == 114:
            try:
                deployments_with_iso_string = list(
                    r.table("deployments")
                    .filter(
                        lambda doc: doc["create_dict"]["hardware"]["isos"].contains(
                            lambda iso: iso.type_of().eq("STRING")
                        )
                    )
                    .run(self.conn)
                )

                print(
                    "Updating "
                    + str(len(deployments_with_iso_string))
                    + " deployments with iso as string"
                )

                updated_deployments_ids = []

                for deployment in deployments_with_iso_string:
                    isos = [
                        json.loads(i.replace("&#39;", '"'))
                        for i in deployment["create_dict"]["hardware"]["isos"]
                    ]
                    r.table("deployments").get(deployment["id"]).update(
                        {"create_dict": {"hardware": {"isos": isos}}}
                    ).run(self.conn)
                    updated_deployments_ids.append(deployment["id"])

                print("Deployments ids updated: " + str(updated_deployments_ids))
            except Exception as e:
                print(e)

        if version == 136:
            try:
                r.table(table).index_create("co_owners", multi=True).run(self.conn)
                r.table(table).index_wait("co_owners").run(self.conn)
            except Exception as e:
                pass

            deployments = list(r.table(table).run(self.conn))

            for deployment in deployments:
                ##### NEW FIELDS
                self.add_keys(
                    table,
                    [
                        {"co_owners": []},
                    ],
                    deployment["id"],
                )

        if version == 139:
            try:
                r.table(table).index_create(
                    "template", r.row["create_dict"]["template"]
                ).run(self.conn)
            except Exception as e:
                print(e)

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

        if version == 61:
            try:
                r.table(table).index_create("user").run(self.conn)
            except Exception as e:
                pass

            try:
                r.table(table).index_create("category").run(self.conn)
            except Exception as e:
                pass

            try:
                r.table(table).index_create("group").run(self.conn)
            except Exception as e:
                pass

            try:
                r.table(table).index_create(
                    "status_user", [r.row["status"], r.row["user"]]
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

        if version == 62:
            medias = r.table(table).get_all("Downloaded", index="status").run(self.conn)
            media_update = []
            for media in medias:
                media_update.append(
                    {
                        "id": media["id"],
                        "progress": {
                            "received": media["progress"]["total"],
                            "total_percent": 100,
                            "total_bytes": (
                                hf.parse_size(media["progress"]["total"] + "iB")
                                if media["progress"]["total"] != "0"
                                else 0
                            ),
                        },
                    }
                )
            r.table(table).insert(media_update, conflict="update").run(self.conn)

        if version == 66:
            try:
                r.table(table).index_create("name").run(self.conn)
            except Exception as e:
                print(e)

        if version == 95:
            try:
                for d in r.table(table).has_fields("url-isard").run(self.conn):
                    if d.get("url-isard"):
                        download_id = d.pop("id")
                        r.table(table).get(download_id).delete().run(self.conn)
                        r.table(table).insert(d).run(self.conn)
                r.table(table).index_create("url-isard").run(self.conn)
                r.table(table).index_create("url-web").run(self.conn)
            except Exception as e:
                print(e)

        return True

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

        if version == 65:
            groups_quota = list(
                r.table(table)
                .filter(lambda group: r.not_(group["quota"] == False))
                .run(self.conn)
            )

            for group in groups_quota:
                ##### REMOVE FIELDS
                self.del_keys(table, [{"quota": {"isos_disk_size"}}], group["id"])
                self.del_keys(table, [{"quota": {"templates_disk_size"}}], group["id"])

                ##### NEW FIELDS
                self.add_keys(
                    table,
                    [
                        {
                            "quota": {
                                "total_size": 999,
                                "total_soft_size": 900,
                            }
                        },
                    ],
                    group["id"],
                )

            groups_limits = list(
                r.table(table)
                .filter(lambda group: r.not_(group["limits"] == False))
                .run(self.conn)
            )

            for group in groups_limits:
                ##### REMOVE FIELDS
                self.del_keys(table, [{"limits": {"isos_disk_size"}}], group["id"])
                self.del_keys(table, [{"limits": {"templates_disk_size"}}], group["id"])

                ##### NEW FIELDS
                self.add_keys(
                    table,
                    [
                        {
                            "limits": {
                                "total_size": 9999,
                                "total_soft_size": 9000,
                            }
                        },
                    ],
                    group["id"],
                )

        if version == 66:
            try:
                r.table(table).index_create("name").run(self.conn)
            except Exception as e:
                print(e)

        if version == 128:
            try:
                r.table(table).filter(r.row["quota"].eq(False).not_()).update(
                    {"quota": {"volatile": 999}}
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 141:
            groups_quota = list(
                r.table(table)
                .filter(lambda group: r.not_(group["quota"] == False))
                .run(self.conn)
            )
            for group in groups_quota:
                self.add_keys(
                    table,
                    [
                        {
                            "quota": {
                                "deployments_total": 999,
                                "deployment_desktops": 999,
                                "started_deployment_desktops": 999,
                            }
                        },
                    ],
                    group["id"],
                )

            groups_limits = list(
                r.table(table)
                .filter(lambda group: r.not_(group["limits"] == False))
                .run(self.conn)
            )
            for group in groups_limits:
                self.add_keys(
                    table,
                    [
                        {
                            "limits": {
                                "deployments_total": 999,
                            }
                        },
                    ],
                    group["id"],
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

        if version == 63:
            try:
                r.table("videos").get("none").update({"model": "none"}).run(self.conn)
            except:
                None

        if version == 66:
            try:
                r.table(table).index_create("name").run(self.conn)
            except Exception as e:
                print(e)

        if version == 68:
            try:
                videos = list(r.table(table).run(self.conn))

                for video in videos:
                    ##### REMOVE FIELDS
                    self.del_keys(
                        table,
                        ["table"],
                        video["id"],
                    )
            except Exception as e:
                print(e)

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

        if version == 65:
            users = list(
                r.table(table)
                .filter(lambda user: r.not_(user["quota"] == False))
                .run(self.conn)
            )

            for user in users:
                ##### REMOVE FIELDS
                self.del_keys(table, [{"quota": {"isos_disk_size"}}], user["id"])
                self.del_keys(table, [{"quota": {"templates_disk_size"}}], user["id"])

                ##### NEW FIELDS
                self.add_keys(
                    table,
                    [
                        {
                            "quota": {
                                "total_size": 999,
                                "total_soft_size": 900,
                            }
                        },
                    ],
                    user["id"],
                )

        if version == 66:
            try:
                r.table(table).index_create("name").run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create(
                    "uid_category_provider",
                    [r.row["uid"], r.row["category"], r.row["provider"]],
                ).run(self.conn)
            except Exception as e:
                None

        if version == 104:
            try:
                r.table(table).replace(r.row.without("user_storage")).run(self.conn)
            except Exception as e:
                None

        if version == 112:
            try:
                # Move duplicated users domains to the most recently used user
                duplicated_users_items = list(
                    r.db("isard")
                    .table("users")
                    .group("uid", "category", "provider")
                    .count()
                    .ungroup()
                    .filter(lambda u: u["reduction"].gt(1))
                    .merge(
                        lambda user: {
                            "oldest_users": r.db("isard")
                            .table("users")
                            .get_all(user["group"][0], index="uid")
                            .order_by("accessed")
                            .coerce_to("array")[:-1]
                            .pluck("id")
                            .merge(
                                lambda u: {
                                    "domains": r.db("isard")
                                    .table("domains")
                                    .get_all(u["id"], index="user")
                                    .pluck(
                                        "id",
                                    )["id"]
                                    .coerce_to("array"),
                                    "media": r.db("isard")
                                    .table("media")
                                    .get_all(u["id"], index="user")
                                    .pluck(
                                        "id",
                                    )["id"]
                                    .coerce_to("array"),
                                    "deployments": r.db("isard")
                                    .table("deployments")
                                    .get_all(u["id"], index="user")
                                    .pluck(
                                        "id",
                                    )["id"]
                                    .coerce_to("array"),
                                }
                            ),
                            "newest_user": r.db("isard")
                            .table("users")
                            .get_all(user["group"][0], index="uid")
                            .order_by("accessed")
                            .coerce_to("array")[-1]
                            .pluck("id")["id"],
                        }
                    )
                    .run(self.conn)
                )
                print("### MOVE DUPLICATED USERS ITEMS TO LATEST ACESSED USER")
                for user in duplicated_users_items:
                    for idx, old_user in enumerate(user["oldest_users"]):
                        if len(old_user["domains"]) > 0:
                            r.db("isard").table("domains").get_all(
                                r.args(old_user["domains"])
                            ).update(
                                {
                                    "user": user["newest_user"],
                                    "name": "d" + str(idx) + "_" + r.row["name"],
                                }
                            ).run(
                                self.conn
                            )
                            print(
                                "Reassigning "
                                + str(len(old_user["domains"]))
                                + " domains with ids "
                                + ", ".join(old_user["domains"])
                                + " from duplicated user with id "
                                + old_user["id"]
                                + " to user with id "
                                + user["newest_user"]
                            )
                        if len(old_user["media"]) > 0:
                            r.db("isard").table("media").get_all(
                                r.args(old_user["media"])
                            ).update(
                                {
                                    "user": user["newest_user"],
                                    "name": "d" + str(idx) + "_" + r.row["name"],
                                }
                            ).run(
                                self.conn
                            )
                            print(
                                "Reassigning "
                                + str(len(old_user["media"]))
                                + " media with ids "
                                + ", ".join(old_user["media"])
                                + " from duplicated user with id "
                                + old_user["id"]
                                + " to user with id "
                                + user["newest_user"]
                            )
                        if len(old_user["deployments"]) > 0:
                            r.db("isard").table("deployments").get_all(
                                r.args(old_user["deployments"])
                            ).update(
                                {
                                    "user": user["newest_user"],
                                    "name": "d" + str(idx) + "_" + r.row["name"],
                                }
                            ).run(
                                self.conn
                            )
                            print(
                                "Reassigning "
                                + str(len(old_user["deployments"]))
                                + " deployments with ids "
                                + ", ".join(old_user["deployments"])
                                + " from duplicated user with id "
                                + old_user["id"]
                                + " to user with id "
                                + user["newest_user"]
                            )
                # Delete duplicated users and keep the one that has the latest access
                duplicated_users = list(
                    r.db("isard")
                    .table("users")
                    .group("uid", "category", "provider")
                    .count()
                    .ungroup()
                    .filter(lambda u: u["reduction"].gt(1))
                    .merge(
                        lambda user: {
                            "oldest_users": r.db("isard")
                            .table("users")
                            .get_all(user["group"][0], index="uid")
                            .order_by("accessed")
                            .coerce_to("array")[:-1]["id"],
                            "newest_user": r.db("isard")
                            .table("users")
                            .get_all(user["group"][0], index="uid")
                            .order_by("accessed")
                            .coerce_to("array")[-1]["id"],
                        }
                    )
                    .run(self.conn)
                )
                print("### DELETE DUPLICATED USERS")
                for user in duplicated_users:
                    print(
                        "Removing "
                        + str(len(user["oldest_users"]))
                        + " duplicated users with ids "
                        + ", ".join(user["oldest_users"])
                        + " keeping user with id "
                        + user["newest_user"]
                    )
                    r.db("isard").table("users").get_all(
                        r.args(user["oldest_users"])
                    ).delete().run(self.conn)
            except Exception as e:
                print(e)

        if version == 115:
            try:
                r.table(table).index_create("role").run(self.conn)
            except Exception as e:
                print(e)

        if version == 116:
            try:
                r.table(table).get_all("local", index="provider").update(
                    {"password_history": [], "password_last_updated": 0}
                )
            except Exception as e:
                None

        if version == 118:
            try:
                r.table("users").update(
                    {"email_verified": None, "email_verification_token": None}
                ).run(self.conn)
            except Exception as e:
                None

        if version == 119:
            try:
                r.table(table).get_all("local", index="provider").filter(
                    ~r.row.has_fields("password_history")
                ).update({"password_history": []}).run(self.conn)
            except Exception as e:
                None

            try:
                r.table(table).get_all("local", index="provider").filter(
                    ~r.row.has_fields("password_last_updated")
                ).update({"password_last_updated": 0}).run(self.conn)
            except Exception as e:
                None
        if version == 123:
            try:
                r.table(table).filter(~r.row.has_fields("email")).update(
                    {"email": ""}
                ).run(self.conn)
            except Exception as e:
                None

        if version == 126:
            try:
                r.table(table).index_create(
                    "user_category", [r.row["id"], r.row["category"]]
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 128:
            try:
                r.table(table).filter(r.row["quota"].eq(False).not_()).update(
                    {"quota": {"volatile": 999}}
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 141:
            users_qota = list(
                r.table(table)
                .filter(lambda user: r.not_(user["quota"] == False))
                .run(self.conn)
            )

            for user in users_qota:
                self.add_keys(
                    table,
                    [
                        {
                            "quota": {
                                "deployments_total": 999,
                                "deployment_desktops": 999,
                                "started_deployment_desktops": 999,
                            }
                        },
                    ],
                    user["id"],
                )

        return True

    """
    AUTHENTICATION TABLE UPGRADES
    """

    def authentication(self, version):
        table = "authentication"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        if version == 118:
            try:
                r.table(table).index_drop("subtype").run(self.conn)
            except Exception as e:
                print(e)
            try:
                r.table(table).index_drop("type-subtype").run(self.conn)
            except Exception as e:
                print(e)
            try:
                r.table(table).index_drop("category-role-subtype").run(self.conn)
                r.table("authentication").index_create(
                    "category-role",
                    [r.row["category"], r.row["role"]],
                ).run(self.conn)
            except Exception as e:
                print(e)
            try:
                result = (
                    r.table(table)
                    .update(
                        lambda policy: {
                            "disclaimer": False,
                            "email_verification": False,
                            "password": {
                                "digits": policy["digits"],
                                "length": policy["length"],
                                "lowercase": policy["lowercase"],
                                "uppercase": policy["uppercase"],
                                "special_characters": policy["special_characters"],
                                "not_username": policy["not_username"],
                                "expiration": policy["expire"],
                                "old_passwords": policy["old_passwords"],
                            },
                        }
                    )
                    .run(self.conn)
                )
                if (result["replaced"]) > 0:
                    r.table(table).replace(
                        r.row.without(
                            "subtype",
                            "digits",
                            "length",
                            "lowercase",
                            "uppercase",
                            "special_characters",
                            "not_username",
                            "expire",
                            "old_passwords",
                        )
                    ).run(self.conn)
            except Exception as e:
                print(e)
            try:
                if (
                    r.table(table)
                    .get("default-password")
                    .delete()
                    .run(self.conn)["deleted"]
                ) > 0:
                    r.table(table).insert(
                        {
                            "type": "local",  # provider
                            "category": "all",
                            "role": "all",
                            "password": {
                                "digits": 0,
                                "length": 8,
                                "lowercase": 0,
                                "uppercase": 0,
                                "special_characters": 0,
                                "not_username": False,
                                "expiration": 0,
                                "old_passwords": 0,
                            },
                            "disclaimer": False,
                            "email_verification": False,
                        }
                    ).run(self.conn)
            except Exception as e:
                print(e)
            try:
                r.table(table).get("default-email-verification").delete().run(self.conn)
            except Exception as e:
                print(e)
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

        if version == 66:
            try:
                r.table(table).index_create("name").run(self.conn)
            except Exception as e:
                print(e)

        if version == 68:
            try:
                interfaces = list(r.table(table).run(self.conn))

                for interface in interfaces:
                    ##### REMOVE FIELDS
                    self.del_keys(
                        table,
                        ["table"],
                        interface["id"],
                    )
            except Exception as e:
                print(e)

        return True

    """
    QOS DISK TABLE UPGRADES
    """

    def qos_disk(self, version):
        table = "qos_disk"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        if version == 66:
            try:
                qos_disks = list(r.table(table).run(self.conn))

                for qos_disk in qos_disks:
                    ##### NEW FIELDS
                    self.add_keys(
                        table,
                        [
                            {"iotune": {"read_iops_sec_max": 0}},
                        ],
                        qos_disk["id"],
                    )
            except Exception as e:
                print(e)

        if version == 68:
            try:
                qos_disks = list(r.table(table).run(self.conn))

                for qos_disk in qos_disks:
                    ##### NEW FIELDS
                    self.del_keys(
                        table,
                        ["table"],
                        qos_disk["id"],
                    )
            except Exception as e:
                print(e)

    """
    QOS NET TABLE UPGRADES
    """

    def qos_net(self, version):
        table = "qos_net"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        if version == 68:
            try:
                qos_nets = list(r.table(table).run(self.conn))

                for qos_net in qos_nets:
                    ##### REMOVE FIELDS
                    self.del_keys(
                        table,
                        ["table"],
                        qos_net["id"],
                    )
            except Exception as e:
                print(e)

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

        if version == 65:
            try:
                r.table(table).index_create(
                    "user_status", [r.row["user_id"], r.row["status"]]
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 106:
            try:
                r.table(table).index_create("parent", r.row["parent"]).run(self.conn)
                r.table(table).index_wait("parent").run(self.conn)
            except Exception as e:
                print(e)

        if version == 110:
            incorrect_storages_ids = list(
                r.table("storage")
                .filter(~r.row.has_fields("user_id"))["id"]
                .run(self.conn)
            )

            print(
                "--- Deleted {} storages created incorrectly in previous upgrades ---".format(
                    len(incorrect_storages_ids)
                )
            )
            r.table("storage").get_all(r.args(incorrect_storages_ids)).delete().run(
                self.conn
            )
        if version == 130:
            r.table("storage").get_all("deleted", index="status").delete().run(
                self.conn
            )

        if version == 131:
            try:
                r.table("storage").update({"perms": ["r", "w"]}).run(self.conn)

                parents = list(  ## storage with disks dependencies
                    r.table("storage")
                    .filter(
                        lambda storage: (
                            storage["status"].ne("deleted") & storage["parent"].ne(None)
                        )
                    )["parent"]
                    .distinct()
                    .run(self.conn)
                )
                for parent in parents:
                    try:
                        r.table("storage").get(parent).update({"perms": ["r"]}).run(
                            self.conn
                        )
                    except Exception:
                        pass
            except Exception as e:
                print(e)

        if version == 138:
            try:
                r.db("isard").table("storage").filter(
                    lambda storage: storage.has_fields("status").not_()
                ).delete().run(self.conn)
            except Exception as e:
                print(e)

        return True

    """
    GPU_PROFILES DISK TABLE UPGRADES
    """

    def gpu_profiles(self, version):
        table = "gpu_profiles"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        if version in [74, 76, 132, 135]:
            try:
                f = open("./initdb/profiles/gpu_profiles.json")
                gpu_profiles = json.loads(f.read())
                f.close()
                r.table("gpu_profiles").insert(gpu_profiles, conflict="update").run(
                    self.conn
                )
            except Exception as e:
                print(e)
        return True

    # def storage_node(self, version):
    #     table = "storage_node"
    #     log.info("UPGRADING " + table + " VERSION " + str(version))
    #     if version == 72:
    #         r.table(table).delete().run(self.conn)
    #     return True

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

        if version == 66:
            try:
                r.table(table).index_create("name").run(self.conn)
            except Exception as e:
                print(e)

        if version == 68:
            try:
                remotevpns = list(r.table(table).run(self.conn))

                for remotevpn in remotevpns:
                    ##### REMOVE FIELDS
                    self.del_keys(
                        table,
                        ["table"],
                        remotevpn["id"],
                    )
            except Exception as e:
                print(e)

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

        if version == 113:
            try:
                r.table(table).index_create("action").run(self.conn)
            except Exception as e:
                print(e)
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
                "categories": (
                    False if default["categories"] == None else default["categories"]
                ),
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
                "categories": (
                    False
                    if default_admins["categories"] == None
                    else default_admins["categories"]
                ),
                "groups": (
                    False
                    if default_admins["groups"] == None
                    else default_admins["groups"]
                ),
                "roles": (
                    False
                    if default_admins["roles"] == None
                    else default_admins["roles"]
                ),
                "users": (
                    False
                    if default_admins["users"] == None
                    else default_admins["users"]
                ),
            }

            r.table(table).get("default admins").update({"allowed": new_allowed}).run(
                self.conn
            )
        if version == 71:
            try:
                r.table(table).index_create("name").run(self.conn)
            except Exception as e:
                print(e)

        if version == 79:
            try:
                r.table("bookings").index_create(
                    "item_type_user", [r.row["item_type"], r.row["user_id"]]
                ).run(self.conn)
            except Exception as e:
                print(e)

        # Version 93 Skipped as introduced a bug in reservables priority changes
        # if version == 93:
        #     try:
        #         default_admins = (
        #             r.table(table)
        #             .filter(  ## "default admins" priority
        #                 lambda row: row["allowed"]["roles"] == ["admin"]
        #                 and row["allowed"]["categories"] == False
        #                 and row["allowed"]["groups"] == False
        #                 and row["allowed"]["users"] == False
        #             )
        #             .pluck("allowed")["allowed"]
        #             .run(self.conn)
        #         )

        #         new_allowed = {
        #             "categories": False
        #             if default_admins["categories"] == None
        #             else default_admins["categories"],
        #             "groups": False
        #             if default_admins["groups"] == None
        #             else default_admins["groups"],
        #             "roles": False
        #             if default_admins["roles"] == None
        #             else default_admins["roles"],
        #             "users": False
        #             if default_admins["users"] == None
        #             else default_admins["users"],
        #         }

        #         r.table(table).filter(  ## "default admins" priority
        #             lambda row: row["allowed"]["roles"] == ["admin"]
        #             and row["allowed"]["categories"] == False
        #             and row["allowed"]["groups"] == False
        #             and row["allowed"]["users"] == False
        #         ).update({"allowed": new_allowed}).run(self.conn)
        #     except Exception as e:
        #         print(e)

    """
    CATEGORIES TABLE UPGRADES
    """

    def categories(self, version):
        table = "categories"
        log.info("UPGRADING " + table + " VERSION " + str(version))

        if version == 65:
            categories_quota = list(
                r.table(table)
                .filter(lambda category: r.not_(category["quota"] == False))
                .run(self.conn)
            )

            for category in categories_quota:
                ##### REMOVE FIELDS
                self.del_keys(table, [{"quota": {"isos_disk_size"}}], category["id"])
                self.del_keys(
                    table, [{"quota": {"templates_disk_size"}}], category["id"]
                )

                ##### NEW FIELDS
                self.add_keys(
                    table,
                    [
                        {
                            "quota": {
                                "total_size": 999,
                                "total_soft_size": 900,
                            }
                        },
                    ],
                    category["id"],
                )

            categories_limits = list(
                r.table(table)
                .filter(lambda category: r.not_(category["limits"] == False))
                .run(self.conn)
            )

            for category in categories_limits:
                ##### REMOVE FIELDS
                self.del_keys(table, [{"limits": {"isos_disk_size"}}], category["id"])
                self.del_keys(
                    table, [{"limits": {"templates_disk_size"}}], category["id"]
                )

                ##### NEW FIELDS
                self.add_keys(
                    table,
                    [
                        {
                            "limits": {
                                "total_size": 9999,
                                "total_soft_size": 9000,
                            }
                        },
                    ],
                    category["id"],
                )
        if version == 66:
            try:
                r.table(table).index_create("name").run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table("categories").update({"custom_url_name": r.row["id"]}).run(
                    self.conn
                )
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create("custom_url_name").run(self.conn)
            except Exception as e:
                print(e)

        if version == 122:
            try:
                r.table("categories").update({"maintenance": False}).run(self.conn)
            except Exception as e:
                print(e)

        if version == 128:
            try:
                r.table(table).filter(r.row["quota"].eq(False).not_()).update(
                    {"quota": {"volatile": 999}}
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 141:
            categories_quota = list(
                r.table(table)
                .filter(lambda category: r.not_(category["quota"] == False))
                .run(self.conn)
            )
            for category in categories_quota:
                self.add_keys(
                    table,
                    [
                        {
                            "quota": {
                                "deployments_total": 999,
                                "deployment_desktops": 999,
                                "started_deployment_desktops": 999,
                            }
                        },
                    ],
                    category["id"],
                )

            categories_limits = list(
                r.table(table)
                .filter(lambda category: r.not_(category["limits"] == False))
                .run(self.conn)
            )
            for category in categories_limits:
                self.add_keys(
                    table,
                    [
                        {
                            "limits": {
                                "deployments_total": 999,
                            }
                        },
                    ],
                    category["id"],
                )

        if version == 142:
            try:
                categories = list(r.table(table).run(self.conn))

                for category in categories:
                    self.add_keys(
                        table,
                        [
                            {"uid": category["id"]},
                            {"photo": ""},
                        ],
                        id=category["id"],
                    )

            except Exception as e:
                print(e)
        if version == 143:
            try:
                r.table(table).index_create("uid").run(self.conn)
            except Exception as e:
                print(e)

        return True

    def qos_net(self, version):
        table = "qos_net"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        if version == 66:
            try:
                r.table(table).index_create("name").run(self.conn)
            except Exception as e:
                print(e)
        return True

    def qos_disk(self, version):
        table = "qos_disk"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        if version == 66:
            try:
                r.table(table).index_create("name").run(self.conn)
            except Exception as e:
                print(e)
        return True

    """
    DESKTOPS PRIORITY TABLE UPGRADES
    """

    def desktops_priority(self, version):
        table = "desktops_priority"
        if version == 81:
            try:
                r.table(table).index_create("name").run(self.conn)
            except Exception as e:
                print(e)

        return True

    """
    LOGS TABLE UPGRADES
    """

    def logs_users(self, version):
        table = "logs_users"
        log.info("UPGRADING " + table + " TABLE TO VERSION " + str(version))
        if version == 91:
            try:
                r.table(table).replace(
                    lambda row: row.without(
                        "user_id",
                        "user_name",
                        "user_group_id",
                        "user_group_name",
                        "user_category_id",
                        "user_category_name",
                        "user_role_id",
                    ).merge(
                        {
                            "owner_user_id": row["user_id"],
                            "owner_user_name": row["user_name"],
                            "owner_group_id": row["user_group_id"],
                            "owner_group_name": row["user_group_name"],
                            "owner_category_id": row["user_category_id"],
                            "owner_category_name": row["user_category_name"],
                            "owner_role_id": row["user_role_id"],
                        }
                    )
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 124:
            try:
                r.table(table).index_drop("user_category_id").run(self.conn)
            except Exception as e:
                pass
            try:
                r.table(table).index_drop("user_id").run(self.conn)
            except Exception as e:
                pass
            try:
                r.table(table).index_drop("user_role_id").run(self.conn)
            except Exception as e:
                pass
            try:
                r.table(table).index_create("owner_user_id").run(self.conn)
            except Exception as e:
                pass
            try:
                r.table(table).index_create("owner_group_id").run(self.conn)
            except Exception as e:
                pass
            try:
                r.table(table).index_create("owner_category_id").run(self.conn)
            except Exception as e:
                pass

        return True

    """
    RECYCLE BIN TABLE UPGRADES
    """

    def recycle_bin(self, version):
        table = "recycle_bin"
        if version == 113:
            try:
                r.table(table).index_create("status").run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create(
                    "owner_status", [r.row["owner_id"], r.row["status"]]
                ).run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create(
                    "owner_category_status",
                    [r.row["owner_category_id"], r.row["status"]],
                ).run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create(
                    "agent_status", [r.row["agent_id"], r.row["status"]]
                ).run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table("recycle_bin").index_create(
                    "parents",
                    r.row["desktops"].concat_map(lambda desktop: desktop["parents"]),
                    multi=True,
                ).run(self.conn)
                r.table("recycle_bin").index_wait("parents").run(self.conn)
            except Exception as e:
                print(e)
        if version == 125:
            try:
                r.table(table).index_create(
                    "owner_category",
                    r.row["owner_category_id"],
                ).run(self.conn)
            except Exception as e:
                print(e)
        if version == 133:
            try:
                r.table("recycle_bin").index_create(
                    "storage",
                    r.row["storages"].map(lambda storage: storage["id"]),
                    multi=True,
                ).run(self.conn)
                r.table("recycle_bin").index_wait("storage").run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table("recycle_bin").index_create(
                    "desktop",
                    r.row["desktops"].map(lambda desktop: desktop["id"]),
                    multi=True,
                ).run(self.conn)
                r.table("recycle_bin").index_wait("desktop").run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table("recycle_bin").index_create(
                    "template",
                    r.row["templates"].map(lambda template: template["id"]),
                    multi=True,
                ).run(self.conn)
                r.table("recycle_bin").index_wait("template").run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table("recycle_bin").index_create(
                    "user",
                    r.row["users"].map(lambda user: user["id"]),
                    multi=True,
                ).run(self.conn)
                r.table("recycle_bin").index_wait("user").run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table("recycle_bin").index_create(
                    "group",
                    r.row["groups"].map(lambda group: group["id"]),
                    multi=True,
                ).run(self.conn)
                r.table("recycle_bin").index_wait("group").run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table("recycle_bin").index_create(
                    "category",
                    r.row["categories"].concat_map(lambda category: category["id"]),
                    multi=True,
                ).run(self.conn)
                r.table("recycle_bin").index_wait("category").run(self.conn)
            except Exception as e:
                print(e)

        if version == 138:
            try:
                r.table(table).index_drop("parents").run(self.conn)
            except Exception as e:
                pass
            try:
                r.table(table).index_create(
                    "parents",
                    r.row["desktops"]
                    .concat_map(lambda desktop: desktop["parents"])
                    .add(
                        r.row["templates"].concat_map(
                            lambda template: template["parents"]
                        )
                    ),
                    multi=True,
                ).run(self.conn)
                r.table(table).index_wait("parents").run(self.conn)
            except Exception as e:
                print(e)
            try:
                r.table(table).index_create(
                    "duplicate_parent_template",
                    r.row["templates"].map(
                        lambda template: template["duplicate_parent_template"]
                    ),
                    multi=True,
                ).run(self.conn)
                r.table(table).index_wait("duplicate_parent_template").run(self.conn)
            except Exception as e:
                print(e)

        return True

    def logs_desktops(self, version):
        table = "logs_desktops"
        log.info("UPGRADING " + table + " TABLE TO VERSION " + str(version))
        if version == 103:
            try:
                log.info(
                    "-> Creating index desktop_name. Please be patient, it can take a while..."
                )
                r.table(table).index_create("desktop_name").run(self.conn)
                r.table(table).index_wait("desktop_name").run(self.conn)
            except Exception as e:
                print(e)
            try:
                log.info(
                    "-> Creating index starting_time. Please be patient, it can take a while..."
                )
                r.table(table).index_create("starting_time").run(self.conn)
                r.table(table).index_wait("starting_time").run(self.conn)
            except Exception as e:
                print(e)

        return True

    """
    STORAGE POOL TABLE UPGRADES
    """

    def storage_pool(self, version):
        table = "storage_pool"
        # if version == 120:
        #     try:
        #         r.table(table).update(
        #             {
        #                 "allowed": {
        #                     "categories": False,
        #                     "groups": False,
        #                     "roles": False,
        #                     "users": False,
        #                 },
        #                 "description": "System default storage pool",
        #                 "startable": True,
        #                 "enabled": True,
        #                 "read": True,
        #                 "write": True,
        #                 "category_id": None,
        #             },
        #         ).run(self.conn)
        #     except Exception as e:
        #         print(e)
        #     try:
        #         r.table(table).index_create("name").run(self.conn)
        #     except Exception as e:
        #         print(e)

        if version == 121:
            try:
                r.table(table).delete().run(self.conn)
                r.table(table).insert(
                    {
                        "allowed": {
                            "categories": False,
                            "groups": False,
                            "roles": [],
                            "users": False,
                        },
                        "categories": [],
                        "description": "Default storage pool",
                        "enabled": True,
                        "id": "00000000-0000-0000-0000-000000000000",
                        "mountpoint": "/isard",
                        "name": "Default",
                        "paths": {
                            "desktop": [{"path": "groups", "weight": 100}],
                            "media": [{"path": "media", "weight": 100}],
                            "template": [{"path": "templates", "weight": 100}],
                            "volatile": [{"path": "volatile", "weight": 100}],
                        },
                        "read": True,
                        "startable": True,
                        "write": True,
                    }
                ).run(self.conn)
            except Exception as e:
                print(e)
            try:
                r.table(table).index_create("name").run(self.conn)
            except Exception as e:
                pass
        return True

    def user_storage(self, version):
        table = "user_storage"
        log.info("UPGRADING " + table + " TABLE TO VERSION " + str(version))
        if version == 92:
            try:
                r.table(table).index_create("name").run(self.conn)
            except Exception as e:
                None

        if version == 104:
            try:
                r.table(table).index_create("name").run(self.conn)
            except Exception as e:
                None
        return True

    def secrets(self, version):
        table = "secrets"
        log.info("UPGRADING " + table + " TABLE TO VERSION " + str(version))
        if version == 94:
            try:
                r.table(table).get("isardvdi").delete().run(self.conn)
            except Exception as e:
                print(e)
            try:
                r.table(table).get("isardvdi-hypervisors").delete().run(self.conn)
            except Exception as e:
                print(e)
        return True

    """
    USAGE PARAMETER TABLE UPGRADES
    """

    def usage_parameter(self, version):
        table = "usage_parameter"
        log.info("UPGRADING " + table + " TABLE TO VERSION " + str(version))
        if version == 105:
            try:
                r.table(table).get("str_created").update({"units": ""}).run(self.conn)
            except Exception as e:
                print(e)
        return True

    """
    USAGE CONSUMPTION TABLE UPGRADES
    """

    def usage_consumption(self, version):
        table = "usage_consumption"
        log.info("UPGRADING " + table + " TABLE TO VERSION " + str(version))
        if version == 117:
            try:
                r.table(table).get_all("_total_", index="item_id").delete().run(
                    self.conn
                )
            except Exception as e:
                print(e)
        return True

    """
    NOTIFICATION TEMPLATES TABLE UPGRADES
    """

    def notification_tmpls(self, version):
        table = "notification_tmpls"
        log.info("UPGRADING " + table + " TABLE TO VERSION " + str(version))
        if version == 137:
            try:
                r.table(table).insert(
                    {
                        "default": "en",
                        "description": "Notification about the modification of the user's elements with bookables when a GPU profile is deleted.",
                        "kind": "deleted_gpu",
                        "lang": {
                            "ca": {
                                "body": "<br> <h2>Alguns dels elements amb reserves han estat modificats</h2> <p>Hola usuari,</p> <p>A causa de la <strong>eliminació d'un perfil de GPU</strong> per part d'un administrador, us informem que</p> <strong>Aquests elements ja no porten el perfil que tenien assignat:<br></strong> <br> <h3>Escriptoris:</h3> {desktops} <br> <h3>Desplegaments:</h3> {deployments} <br> <hr><br> <strong>I aquestes reserves han estat eliminades:</strong> <br> <h3>Reserves:</h3> {bookings}<br>",
                                "footer": "Si us plau, no respongueu a aquest correu electrònic, ja que ha estat generat automàticament.",
                                "title": "Alguns elements teus amb reserves han estat modificats",
                            },
                            "en": {
                                "body": "<br> <h2>Some of the elements with bookings you own have been modified</h2> <p>Hello user,</p> <p>Due to the <strong>elimination of a GPU profile</strong> by an administrator, we inform you that</p> <strong>The profiles assigned to these items have been deleted and they no longer have assigned the profile they had before:<br></strong> <br> <h3>Desktops:</h3> {desktops} <br> <h3>Deployments:</h3> {deployments} <br> <hr> <br> <strong>And these bookings have been deleted:</strong> <br> <h3>Bookings:</h3> {bookings} <br>",
                                "footer": "Please do not answer since this email has been automatically generated.",
                                "title": "Some of your elements with bookings have been modified",
                            },
                            "es": {
                                "body": "<br> <h2>Algunos de tus elementos con reservas han sido modificados</h2> <p>A causa de la <strong>eliminación de un perfil de GPU</strong> por parte de un administrador, le informamos que</p> <strong>Estos elementos ya no llevan el perfil que tenían asignado:<br></strong> <br> <h3>Escritorios:</h3> {desktops} <br> <h3>Despliegues:</h3> {deployments} <br> <hr> <br> <strong>Y estas reservas han sido eliminadas:</strong> <br> <h3>Reservas:</h3> {bookings} <br>",
                                "footer": "Por favor, no responda a este correo electrónico, ya que es un envío automático.",
                                "title": "Se han modificado algunos de tus elementos con reservas",
                            },
                        },
                        "name": "Deleted GPU profile",
                        "system": {
                            "body": "<br> <h2>Some of the elements with bookings you own have been modified</h2> <p>Hello user,</p> <p>Due to the <strong>elimination of a GPU profile</strong> by an administrator, we inform you that</p> <strong>The profiles assigned to these items have been deleted and they no longer have assigned the profile they had before:<br></strong> <br> <h3>Desktops:</h3> {desktops} <br> <h3>Deployments:</h3> {deployments} <br> <hr> <br> <strong>And these bookings have been deleted:</strong> <br> <h3>Bookings:</h3> {bookings} <br>",
                            "footer": "Please do not answer since this email has been automatically generated.",
                            "title": "Some of your elements with bookings have been modified",
                        },
                        "vars": {
                            "bookings": "<ul class='list-group'><li class='list-group-item'>Windows 10 GPU | From 12 Mar 2024 13:00 to 13 Apr 2024 15:30</li><li class='list-group-item'>Ubuntu 22.04 GPU | From 12 Mar 2024 14:00 - 13 Mar 2024 15:30</li></ul>",
                            "deployments": "<ul class='list-group'><li class='list-group-item'>Windows 11 deployment</li><li class='list-group-item'>Ubuntu 24.04 deployment</li></ul>",
                            "desktops": "<ul class='list-group'><li class='list-group-item'>Windows 11</li><li class='list-group-item'>Windows 10</li><li class='list-group-item'>Ubuntu 22.04</li></ul>",
                        },
                    }
                ).run(self.conn)
            except Exception as e:
                print(e)
        return True

    """
    SYSTEM EVENTS TABLE UPGRADES
    """

    def system_events(self, version):
        table = "system_events"
        log.info("UPGRADING " + table + " TABLE TO VERSION " + str(version))
        if version == 137:
            try:
                templates = list(
                    r.table("notification_tmpls").pluck("id", "kind").run(self.conn)
                )
                result = (
                    r.table(table)
                    .insert(
                        {
                            "channels": ["mail"],
                            "event": "deleted-gpu",
                            "tmpl_id": [
                                template["id"]
                                for template in templates
                                if template.get("kind") == "deleted_gpu"
                            ][0],
                        }
                    )
                    .run(self.conn)
                )
                print(result)
            except Exception as e:
                print(e)
        return True

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
