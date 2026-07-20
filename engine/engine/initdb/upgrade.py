# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import json
import os
import re
import sys
import time
from uuid import uuid4


def strtobool(val):
    """Replacement for ``distutils.util.strtobool``, removed in Python 3.12.

    Returns 1 for truthy strings ('y', 'yes', 'true', 't', '1', 'on'),
    0 for falsy ('n', 'no', 'false', 'f', '0', 'off'). Raises ValueError
    on anything else, matching the legacy contract.
    """
    val = (val or "").strip().lower()
    if val in {"y", "yes", "t", "true", "on", "1"}:
        return 1
    if val in {"n", "no", "f", "false", "off", "0"}:
        return 0
    raise ValueError(f"invalid truth value: {val!r}")


import humanfriendly as hf
import rethinkdb as r
from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from redis import Redis

from .lib import *
from .log import *
from .upgrade_helpers import (
    _system_upgrades,
    add_keys,
    check_done,
    del_keys,
    get_card,
    get_domain_stock_card,
    index_create,
    keys_exists,
    v189_backfill_and_canon_vgpus,
    v189_canonicalize_vgpu_ids,
    v189_prune_non_full_use_gpu_profiles,
)

"""
Update to new database release version when new code version release
"""
release_version = 202
# release 202: drop dead RethinkDB indexes and reconcile populate on hot tables
# release 201: normalise path-shaped storage.parent rows to their UUID
# release 200: cleanup old single domain field for bastion targets
# release 199: purge decommissioned core_worker RQ state (the core and
#              core.feedback queues, their stale worker registrations and job
#              registries) left orphaned by the apiv4 migration. Idempotent.
# release 198: Seed vgpus.requested_profile (operator intent) and
#              vgpus.operator_passthrough from current vgpu_profile so the new
#              reconcile policy (intent vs runtime state) has DB rows to read.
#              Idempotent — only touches rows missing the new fields.
#              (Upstream MR !4496 ships this as v189 on main; the v189_*
#              helper names in upgrade_helpers.py are kept for cross-branch
#              diffability. bugfix/1179 renumbers to 199 if it lands after.)
# release 197: CUTOVER RECONCILIATION — re-assert, idempotently, every
#              apiv4-integration-only migration that lives at a version number
#              (184-189) the main lineage reused for DIFFERENT content. The two
#              lineages share migration history up to v183 and diverge from
#              v184: a main-lineage DB (config.version 188, or 189 with the GPU
#              stack) attached to this code would only run forward and silently
#              skip apiv4's own 184-189 content (deployment_users quota split,
#              deployments/domains tag_desktop_id backfill, apiv4 pagination +
#              recycle_bin/media indexes, hypervisors thread_status strip).
#              Re-running on an apiv4-lineage DB is a guarded no-op.
#              RULE GOING FORWARD: main mints versions <= 189; this branch
#              mints >= 190 contiguously IN MERGE ORDER (no reserved holes —
#              the runner is forward-only, so a DB that passes a hole never
#              comes back for it). Main's ceiling is therefore always the
#              immediate predecessor of this lineage's chain at cutover.
# release 195: Seed provider status (healthy/msg/last_updated) on each auth provider config
# release 194: Normalize legacy media status "Deleted"/"FailedDeleted" to "deleted"
# release 193: Add unused_deployment_desktops notification kinds, default rule, and matching notifications/action entries (port of main 7df258e32)
# release 192: Add config.usage_retention defaults (daily_months=3, weekly_months=6, total_months=None)
# release 191: Add domains.kind_user_accessed compound index for apiv4 pagination
# release 190: Add allow_insecure_tls field to LDAP and SAML provider configs
# release 189: Move hypervisor thread_status from DB to engine RAM; drop the field
# release 187: Add recycle_bin compound indexes + pre-computed count fields for performance
# release 186: Split category authentication tri-state boolean into two explicit booleans
#              Import authentication providers status from AUTHENTICATION_*_ENABLED variables
#              Repair storage records missing user_id, ensure perms and status_logs
# release 185: Align deployment structure with apiv4 (tag_desktop_id, image, kind, deployment_users quota)
# release 184: Add recycle_bin indexes and pre-computed count fields for performance
# release 183: Import Google OAuth2 configuration from AUTHENTICATION_AUTHENTICATION_GOOGLE_CLIENT_* environment variables
# release 182: Import SAML configuration from AUTHENTICATION_AUTHENTICATION_SAML_* environment variables
# release 181: Add proxy_protocol field to bastion targets http configuration
# release 180: Import LDAP configuration from AUTHENTICATION_AUTHENTICATION_LDAP_* environment variables
# release 179: Remove old LDAP configuration
# release 178: Bastion targets support multiple domains (array)
# release 177: Recreate deployment indexes considering the new create_dict structure
# release 176: Delete null parents on domains
# release 175: Import SMTP configuration from NOTIFY_EMAIL* environment variables
# release 174: Add task index to storage table
# release 173: Remove enabled field from maintenance_text
# release 172: New deployment structure to match future labs feature
# release 171: Add 'start' notification action and bastion notification
# release 170: Global and category bastion_domain
# release 169: Set secrets role to manager
# release 168: Add new field api_key to all users
# release 167: Recycle bin scheduled jobs interval changed to 1 hour, recycle_bin_cutoff_time field added to categories
# release 166: Local allowed domain removed
# release 165: Delete missing users and groups from migration exceptions
# release 164: Add field reservables to all domains
# release 163: Move category allowed_domain to allowed_domains as an array of providers
# release 162: Add unused_deployments notification template
#              Add send_unused_deployments_to_recycle_bin rule to unused_item_timeouts table
# release 161: Delete the unused_desktops_cutoff_time field from the config table
# release 160: Add enabled field to login notifications
# release 159: Add nonpersistent desktops delete timeout to config table
# release 158: Add unused_desktops notification template
# release 157: Add unused_desktops_cutoff_time field to config table
# release 156: Remove user_permissions field from deployments create_dict
# release 155: Add empty dict values to provider settings
# release 154: Add bastion alloweds to config table
# release 153: Add new field 'user_migration' to config table
# release 152: Add index 'owner_group_status', categor to recycle bin table
# release 151: Add new field 'enabled_virt' to storage pools table
# release 150: Fix storage users to match domain users
# release 149: Add multi desktop ids and kind index
# release 148: Add booking_id, kind_booking, kind_valid_booking index to domains table
#              Add item_type index to bookings table
#              Update desktops without booking_id to booking_id False
# release 147: Add new virtio video model
# release 146: Add template index to authentication table
# release 145: Change default QoS values
# release 144: Add password_history to users that don't have it
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
    "bookings",
    "unused_item_timeout",
    "users_migrations_exceptions",
    "notifications",
    "notifications_action",
    "targets",
    "vgpus",
    "redis_tasks_cleanup",
]


# --- vGPU id canonicalization (used only by the one-shot v189 migration) -----
# Kept local: this is migration-only code (runs once, version-gated), so it is
# deliberately NOT promoted into the shared isardvdi_common package. The runtime
# canonicalization lives at the discovery source
# (gpu_discovery._canon_vgpu_profile_name); this mirrors its transform on the
# full BRAND-MODEL-PROFILE id so freshly-discovered and migrated ids share one
# canonical shape.
#
# BRAND-MODEL-PROFILE must have exactly two dashes. Canonical form strips dashes
# from MODEL and replaces the dash inside a MIG suffix with "_" ("1-2Q" -> "1_2Q");
# dot-form MIG ("1g.24gb") and "passthrough" are already dash-free (unchanged).


class Upgrade(object):
    # The table-upgrade helper methods live in upgrade_helpers (module-level
    # functions taking `self`, so upgrade_vgpu_unify_test can import that file
    # without this module's runtime deps). Bind them here so the hundreds of
    # existing self.add_keys()/self.check_done()/... call sites keep working.
    add_keys = add_keys
    del_keys = del_keys
    check_done = check_done
    keys_exists = keys_exists
    index_create = index_create
    get_domain_stock_card = get_domain_stock_card
    get_card = get_card
    _system_upgrades = _system_upgrades

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
        self.db_cleanup()
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
                log.info("Database server ready")
                ready = True
            except Exception as e:
                log.error(
                    "Upgrade error: Database server "
                    + self.cfg["RETHINKDB_HOST"]
                    + ":"
                    + self.cfg["RETHINKDB_PORT"]
                    + " not present. Waiting to be ready"
                )
                time.sleep(0.5)
        ready = False

    def db_cleanup(self):
        log.info("Cleaning database...")
        result = (
            r.table("storage")
            .filter(lambda doc: doc.keys().count().eq(1).and_(doc.has_fields("id")))
            .delete()
            .run(self.conn)
        )
        if result.get("deleted"):
            log.warning(
                f"DBCLEANING: deleted {result['deleted']} incomplete storage entries."
            )

    def upgrade_if_needed(self):
        log.info(
            f"DB CODE RELEASE VERSION: {release_version} - DB IN USE VERSION: {self.cfg['version']}"
        )
        if not release_version > self.cfg["version"]:
            log.info("No database upgrade needed.")
            self._system_upgrades()
            return False
        apply_upgrades = [
            i for i in range(self.cfg["version"] + 1, release_version + 1)
        ]
        log.info("Now will upgrade database versions: " + str(apply_upgrades))
        for version in apply_upgrades:
            for table in tables:
                getattr(self, table)(version)
        self._system_upgrades()
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

        if version == 153:
            try:
                r.table(table).update({"user_migration": {"check_quotas": True}}).run(
                    self.conn
                )
            except Exception as e:
                log.error(
                    "Could not update table "
                    + table
                    + " conversion fields for db version "
                    + str(version)
                    + "!"
                )
                log.error("Error detail: " + str(e))

        if version == 154:
            try:
                r.table(table).update(
                    {
                        "bastion": {
                            "allowed": {
                                "categories": [],
                                "groups": [],
                                "roles": [],
                                "users": [],
                            },
                        }
                    }
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 155:
            try:
                r.table(table).get(1).update(
                    {
                        "auth": {
                            "google": {
                                "migration": {
                                    "action_after_migrate": "none",
                                    "export": False,
                                    "import": False,
                                    "notification_bar": {
                                        "enabled": False,
                                        "level": None,
                                        "template": None,
                                    },
                                }
                            },
                            "ldap": {
                                "migration": {
                                    "action_after_migrate": "none",
                                    "export": False,
                                    "import": False,
                                    "notification_bar": {
                                        "enabled": False,
                                        "level": None,
                                        "template": None,
                                    },
                                }
                            },
                            "local": {
                                "migration": {
                                    "action_after_migrate": "none",
                                    "export": False,
                                    "import": False,
                                    "notification_bar": {
                                        "enabled": False,
                                        "level": None,
                                        "template": None,
                                    },
                                }
                            },
                            "saml": {
                                "migration": {
                                    "action_after_migrate": "none",
                                    "export": False,
                                    "import": False,
                                    "notification_bar": {
                                        "enabled": False,
                                        "level": None,
                                        "template": None,
                                    },
                                }
                            },
                        }
                    }
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 157:
            try:
                r.table(table).get(1).update({"unused_desktops_cutoff_time": None}).run(
                    self.conn
                )
            except Exception as e:
                print(e)

        if version == 159:
            try:
                r.table(table).get(1).update(
                    {"nonpersistent_desktops_inactivity_limit": 60}  # 60 minutes
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 160:
            try:
                current_login_config = (
                    r.table("config")
                    .get(1)
                    .run(self.conn)
                    .get(
                        "login",
                        {
                            "notification_cover": {
                                "enabled": False,
                                "title": None,
                                "description": None,
                                "icon": None,
                                "extra_styles": None,
                                "button": {
                                    "extra_styles": None,
                                    "text": None,
                                    "url": None,
                                },
                            },
                            "notification_form": {
                                "enabled": False,
                                "title": None,
                                "description": None,
                                "icon": None,
                                "extra_styles": None,
                                "button": {
                                    "extra_styles": None,
                                    "text": None,
                                    "url": None,
                                },
                            },
                        },
                    )
                )
                notification_cover = (
                    current_login_config.get("notification_cover") or {}
                )
                notification_form = current_login_config.get("notification_form") or {}
                login_config = {
                    "notification_cover": {
                        "enabled": (
                            True
                            if notification_cover.get("title")
                            or notification_cover.get("description")
                            or (
                                notification_cover.get("button", {}).get("text")
                                and notification_cover.get("button", {}).get("url")
                            )
                            else False
                        ),
                        "title": notification_cover.get("title"),
                        "description": notification_cover.get("description"),
                        "icon": notification_cover.get("icon"),
                        "extra_styles": notification_cover.get("extra_styles"),
                        "button": {
                            "extra_styles": notification_cover.get("button", {}).get(
                                "extra_styles"
                            ),
                            "text": notification_cover.get("button", {}).get("text"),
                            "url": notification_cover.get("button", {}).get("url"),
                        },
                    },
                    "notification_form": {
                        "enabled": (
                            True
                            if notification_form.get("title")
                            or notification_form.get("description")
                            or (
                                notification_form.get("button", {}).get("text")
                                and notification_form.get("button", {}).get("url")
                            )
                            else False
                        ),
                        "title": notification_form.get("title"),
                        "description": notification_form.get("description"),
                        "icon": notification_form.get("icon"),
                        "extra_styles": notification_form.get("extra_styles"),
                        "button": {
                            "extra_styles": notification_form.get("button", {}).get(
                                "extra_styles"
                            ),
                            "text": notification_form.get("button", {}).get("text"),
                            "url": notification_form.get("button", {}).get("url"),
                        },
                    },
                }

                r.table("config").get(1).update({"login": login_config}).run(self.conn)
            except Exception as e:
                print(e)

        if version == 161:
            try:
                self.del_keys(table, ["unused_desktops_cutoff_time"])
                self.del_keys(table, [{"recycle_bin": {"unused_desktops_cutoff_time"}}])
            except Exception as e:
                print(e)

        if version == 167:
            try:
                max_delete_period = (
                    r.table("scheduler_jobs")
                    .get("admin.recycle_bin_delete_admin")
                    .pluck("kwargs")
                    .default({"kwargs": {"max_delete_period": 1}})
                    .run(self.conn)["kwargs"]["max_delete_period"]
                )
                # The old field max_delete_period will be from now on recycle_bin_cutoff_time under the config table
                r.table("config").update(
                    {"recycle_bin": {"recycle_bin_cutoff_time": int(max_delete_period)}}
                ).run(
                    self.conn
                )  # Defines the amount of time in hours that the recycle bin will keep the deleted items before being permanently deleted
                r.table("scheduler_jobs").get(
                    "admin.recycle_bin_delete_admin"
                ).delete().run(self.conn)
            except Exception as e:
                print(e)

        if version == 170:
            try:
                r.table("config").get(1).update(
                    {
                        "bastion": {
                            "enabled": True,
                            "domain": os.environ.get("DOMAIN"),
                            "domain_verification_required": True,
                            "individual_domains": {
                                "allowed": {
                                    "categories": False,
                                    "groups": False,
                                    "roles": False,
                                    "users": False,
                                },
                            },
                        }
                    }
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 173:
            try:
                self.del_keys(table, [{"maintenance_text": "enabled"}])
            except Exception as e:
                print(e)

        if version == 175:
            r.table(table).update(
                {
                    "smtp": {
                        "enabled": bool(
                            strtobool(os.environ.get("NOTIFY_EMAIL", "False"))
                        ),
                        "host": os.environ.get(
                            "NOTIFY_EMAIL_SMTP_SERVER", "example.com"
                        ),
                        # SMPT is the pre-rename misspelling, still injected by a
                        # docker-compose.yml generated before the rename
                        "port": int(
                            os.environ.get("NOTIFY_EMAIL_SMTP_PORT")
                            or os.environ.get("NOTIFY_EMAIL_SMPT_PORT")
                            or 587
                        ),
                        "username": os.environ.get(
                            "NOTIFY_EMAIL_USERNAME", "user@example.com"
                        ),
                        "password": os.environ.get(
                            "NOTIFY_EMAIL_PASSWORD", "SomePlainStoredPassphrase"
                        ),
                    }
                }
            ).run(self.conn)

        if version == 179:
            r.table(table).replace(
                r.row.without({"auth": {"ldap": ["bind_dn", "ldap_server"]}})
            ).run(self.conn)

        if version == 180:
            ldap_config = {}
            default_config = {
                "protocol": "ldap",
                "host": "",
                "bind_dn": "",
                "password": "",
                "base_search": "",
                "filter": "(&(objectClass=person)(uid=%s)",
                "field_uid": "",
                "regex_uid": ".*",
                "field_username": "",
                "regex_username": ".*",
                "field_name": "",
                "regex_name": ".*",
                "field_email": "",
                "regex_email": ".*",
                "field_photo": "",
                "regex_photo": ".*",
                "field_category": "",
                "regex_category": ".*",
                "field_group": "",
                "regex_group": ".*",
                "group_default": "default",
                "role_list_search_base": "",
                "role_list_filter": "(&(objectClass=posixGroup)(memberUid=%s))",
                "role_list_field": "",
                "role_list_regex": ".*",
                "role_admin_ids": "",
                "role_manager_ids": "",
                "role_advanced_ids": "",
                "role_user_ids": "",
                "role_default": "user",
            }
            for config_key, config_value in default_config.items():
                ldap_config[config_key] = os.environ.get(
                    f"AUTHENTICATION_AUTHENTICATION_LDAP_{config_key.upper()}",
                    config_value,
                )
            default_config = {
                "auto_register": "false",
                "guess_category": "false",
                "role_list_use_user_dn": "false",
                "save_email": "true",
            }
            for config_key, config_value in default_config.items():
                ldap_config[config_key] = bool(
                    strtobool(
                        os.environ.get(
                            f"AUTHENTICATION_AUTHENTICATION_LDAP_{config_key.upper()}",
                            config_value,
                        )
                    )
                )
            ldap_config["port"] = int(
                os.environ.get(f"AUTHENTICATION_AUTHENTICATION_LDAP_PORT", 389)
            )
            ldap_config["auto_register_roles"] = os.environ.get(
                "AUTHENTICATION_AUTHENTICATION_LDAP_AUTO_REGISTER_GROUPS", ""
            )

            r.table(table).update({"auth": {"ldap": {"ldap_config": ldap_config}}}).run(
                self.conn
            )

        if version == 182:
            saml_config = {}
            default_config = {
                "metadata_url": "",
                "metadata_file": "/keys/idp-metadata.xml",
                "entity_id": "",
                "signature_method": "",
                "key_file": "/keys/isardvdi.key",
                "cert_file": "/keys/isardvdi.cert",
                "max_issue_delay": "90s",
                "field_uid": "",
                "regex_uid": ".*",
                "field_username": "",
                "regex_username": ".*",
                "field_name": "",
                "regex_name": ".*",
                "field_email": "",
                "regex_email": ".*",
                "field_photo": "",
                "regex_photo": ".*",
                "auto_register_roles": "",
                "field_category": "",
                "regex_category": ".*",
                "field_group": "",
                "regex_group": ".*",
                "group_default": "default",
                "field_role": "",
                "regex_role": ".*",
                "role_admin_ids": "",
                "role_manager_ids": "",
                "role_advanced_ids": "",
                "role_user_ids": "",
                "role_default": "user",
                "logout_redirect_url": "",
            }
            for config_key, config_value in default_config.items():
                saml_config[config_key] = os.environ.get(
                    f"AUTHENTICATION_AUTHENTICATION_SAML_{config_key.upper()}",
                    config_value,
                )
            default_config = {
                "auto_register": "false",
                "guess_category": "false",
                "save_email": "true",
            }
            for config_key, config_value in default_config.items():
                saml_config[config_key] = bool(
                    strtobool(
                        os.environ.get(
                            f"AUTHENTICATION_AUTHENTICATION_SAML_{config_key.upper()}",
                            config_value,
                        )
                    )
                )
            r.table(table).update({"auth": {"saml": {"saml_config": saml_config}}}).run(
                self.conn
            )

        if version == 183:
            r.table(table).update(
                {
                    "auth": {
                        "google": {
                            "google_config": {
                                "client_id": os.environ.get(
                                    "AUTHENTICATION_AUTHENTICATION_GOOGLE_CLIENT_ID"
                                ),
                                "client_secret": os.environ.get(
                                    "AUTHENTICATION_AUTHENTICATION_GOOGLE_CLIENT_SECRET"
                                ),
                            }
                        }
                    }
                }
            ).run(self.conn)

        if version == 186:
            default_config = {
                "local": "true",
                "ldap": "false",
                "saml": "false",
                "google": "false",
            }
            auth_config = {}
            for config_key, config_value in default_config.items():
                auth_config[config_key] = {
                    "enabled": bool(
                        strtobool(
                            os.environ.get(
                                f"AUTHENTICATION_AUTHENTICATION_{config_key.upper()}_ENABLED",
                                config_value,
                            )
                        )
                    )
                }

            r.table(table).update({"auth": auth_config}).run(self.conn)

        if version == 190:
            # Write-preserving form: a main-lineage DB already ran this as its
            # v187 and an operator may have enabled the flag since — default()
            # keeps the stored value and only fills in False when absent, so
            # the cutover pass through 190 cannot clobber it.
            r.table(table).update(
                lambda cfg: {
                    "auth": {
                        "ldap": {
                            "ldap_config": {
                                "allow_insecure_tls": cfg["auth"]["ldap"][
                                    "ldap_config"
                                ]["allow_insecure_tls"].default(False)
                            }
                        },
                        "saml": {
                            "saml_config": {
                                "allow_insecure_tls": cfg["auth"]["saml"][
                                    "saml_config"
                                ]["allow_insecure_tls"].default(False)
                            }
                        },
                    }
                }
            ).run(self.conn)

        if version == 192:
            # Tiered retention for usage_consumption rows. Older daily
            # rows are aggregated into weekly / monthly buckets so the
            # table doesn't grow unbounded (it was already 3.8 GB / 63%
            # of the database with 8 months of daily granularity on a
            # ~5k-item install).
            r.table(table).update(
                {
                    "usage_retention": {
                        "daily_months": 3,
                        "weekly_months": 6,
                        "total_months": None,
                    }
                }
            ).run(self.conn)

        if version == 195:
            provider_status = {
                "healthy": False,
                "msg": "",
                "last_updated": r.epoch_time(0),
            }
            r.table(table).update(
                {
                    "auth": {
                        "local": {"status": provider_status},
                        "ldap": {"status": provider_status},
                        "saml": {"status": provider_status},
                        "google": {"status": provider_status},
                    }
                }
            ).run(self.conn)

        if version == 196:
            # The "none"/"" action_after_migrate sentinels now map to null
            # (only "disable"/"delete" are real actions). Normalise stored
            # provider migration config so the DB matches the API contract.
            auth = r.table(table).get(1)["auth"].run(self.conn) or {}
            updates = {}
            for provider, pconf in auth.items():
                migration = pconf.get("migration") if isinstance(pconf, dict) else None
                if isinstance(migration, dict) and migration.get(
                    "action_after_migrate"
                ) in ("none", ""):
                    updates[provider] = {"migration": {"action_after_migrate": None}}
            if updates:
                r.table(table).get(1).update({"auth": updates}).run(self.conn)

        return True

    """
    HYPERVISORS TABLE UPGRADES
    """

    def hypervisors(self, version):
        table = "hypervisors"
        # Pre-178 blocks iterate this snapshot; 178+ (incl. the 190->197 cutover)
        # is server-side and never reads it. Skip the full-table load (100K+ rows
        # on big installs, otherwise materialised once per version call).
        data = list(r.table(table).run(self.conn)) if version < 178 else []
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

        if version == 189:
            # thread_status moved from DB to engine-process RAM.
            # Strip the now-obsolete field from every hypervisor row in a
            # single server-side replace. Non-atomic is required because
            # replace() with an r.row expression must be non-atomic.
            try:
                r.table(table).replace(
                    r.row.without("thread_status"), non_atomic=True
                ).run(self.conn)
            except Exception as e:
                log.error(
                    "Could not strip thread_status from "
                    + table
                    + " for db version "
                    + str(version)
                    + "!"
                )
                log.error("Error detail: " + str(e))

        if version == 197:
            # Cutover reconciliation: apiv4-only v189 thread_status strip
            # (moved from DB to engine RAM). without() is a no-op when the
            # field is already absent.
            try:
                r.table(table).replace(
                    r.row.without("thread_status"), non_atomic=True
                ).run(self.conn)
            except Exception as e:
                log.error(
                    "Could not strip thread_status from "
                    + table
                    + " for db version "
                    + str(version)
                )
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
        # Pre-178 blocks iterate this snapshot; 178+ (incl. the 190->197 cutover)
        # is server-side and never reads it. Skip the full-table load (100K+ rows
        # on big installs, otherwise materialised once per version call).
        data = list(r.table(table).run(self.conn)) if version < 178 else []
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
        # Pre-178 blocks iterate this snapshot; 178+ (incl. the 190->197 cutover)
        # is server-side and never reads it. Skip the full-table load (100K+ rows
        # on big installs, otherwise materialised once per version call).
        data = list(r.table(table).run(self.conn)) if version < 178 else []
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

        if version == 145:
            try:
                r.table(table).index_create(
                    "qos_disk_id", r.row["create_dict"]["hardware"]["qos_disk_id"]
                ).run(self.conn)
                r.table(table).index_wait("qos_disk_id").run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table("domains").update(
                    {"create_dict": {"hardware": {"qos_disk_id": False}}}
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 148:
            try:
                r.table(table).index_create("booking_id").run(self.conn)
                r.table(table).index_wait("booking_id").run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create(
                    "kind_booking",
                    [r.row["kind"], r.row["booking_id"]],
                ).run(self.conn)
                r.table(table).index_wait("kind_booking").run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).get_all("desktop", index="kind").filter(
                    r.row.has_fields("booking_id").not_()
                ).update({"booking_id": False}).run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create(
                    "kind_valid_booking",
                    lambda doc: r.branch(
                        doc["booking_id"] != False,
                        doc["kind"],
                        None,
                    ),
                ).run(self.conn)
                r.table(table).index_wait("kind_valid_booking").run(self.conn)
            except Exception as e:
                print(e)
        if version == 149:
            try:
                r.table("domains").index_create(
                    "kind_ids", [r.row["kind"], r.row["id"]]
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 164:
            try:
                r.table("domains").filter(
                    r.row["create_dict"].has_fields("reservables").not_()
                ).update(
                    {
                        "create_dict": {
                            "reservables": {
                                "vgpus": None,
                            }
                        }
                    }
                ).run(
                    self.conn
                )
            except Exception as e:
                print(e)

        if version == 176:
            try:
                r.table(table).filter(
                    lambda d: d.has_fields("parents") & d["parents"].contains(None)
                ).update(
                    {"parents": r.row["parents"].filter(lambda p: p.ne(None))}
                ).run(
                    self.conn
                )
            except Exception as e:
                print(e)

        if version == 184:
            # Build tag → tag_desktop_id mapping in Python from the
            # (small) deployments table.
            try:
                deployments = list(
                    r.table("deployments").pluck("id", "create_dict").run(self.conn)
                )
                deployment_tag_desktop_ids = {}
                for deployment in deployments:
                    if (
                        isinstance(deployment.get("create_dict"), list)
                        and len(deployment["create_dict"]) > 0
                    ):
                        deployment_tag_desktop_ids[deployment["id"]] = deployment[
                            "create_dict"
                        ][0].get("tag_desktop_id", False)

                # One server-side update over the whole domains table:
                # for each row, look up tag_desktop_id from the
                # deployment mapping if the row has a tag, else False.
                # Replaces a Python loop that issued one round-trip per
                # tagged row + a separate full-table fallback update —
                # ~14 minutes on a 77k-row prod-shape dataset.
                deployment_map = r.expr(deployment_tag_desktop_ids)
                r.table(table).update(
                    lambda d: {
                        "tag_desktop_id": r.branch(
                            d["tag"].default(False).ne(False),
                            deployment_map[d["tag"]].default(False),
                            False,
                        )
                    }
                ).run(self.conn)
            except Exception as e:
                print(e)

            # Build both indexes concurrently. RethinkDB builds indexes
            # in the background; sequencing two ``index_wait`` calls
            # serialises the wallclock. A single combined ``index_wait``
            # blocks until both are ready.
            try:
                r.table(table).index_create("tag_desktop_id").run(self.conn)
            except Exception as e:
                print(e)
            try:
                r.table(table).index_create(
                    "tag_tag_desktop_id",
                    [r.row["tag"], r.row["tag_desktop_id"]],
                ).run(self.conn)
            except Exception as e:
                print(e)
            try:
                r.table(table).index_wait("tag_desktop_id", "tag_tag_desktop_id").run(
                    self.conn
                )
            except Exception as e:
                print(e)

        if version == 185:
            # Compound indexes for apiv4 templates pagination
            try:
                r.table(table).index_create(
                    "kind_accessed",
                    [r.row["kind"], r.row["accessed"]],
                ).run(self.conn)
                r.table(table).index_wait("kind_accessed").run(self.conn)
            except Exception as e:
                print(e)
            try:
                r.table(table).index_create(
                    "enabled_kind_accessed",
                    [r.row["enabled"], r.row["kind"], r.row["accessed"]],
                ).run(self.conn)
                r.table(table).index_wait("enabled_kind_accessed").run(self.conn)
            except Exception as e:
                print(e)

        if version == 191:
            # Compound index for apiv4 desktops pagination. Used by
            # ``DesktopService.get_user_desktops_paginated`` (route
            # ``GET /api/v4/items/paginated/desktops``); without it the
            # endpoint 500s with
            # ``ReqlOpFailedError: Index 'kind_user_accessed' was not
            # found on table 'isard.domains'``. Mirrors the index
            # introduced on the apiv4-and-websockets reference branch
            # in commit ``a474b1278`` that never reached upgrade.py on
            # apiv4-integration.
            try:
                r.table(table).index_create(
                    "kind_user_accessed",
                    [r.row["kind"], r.row["user"], r.row["accessed"]],
                ).run(self.conn)
                r.table(table).index_wait("kind_user_accessed").run(self.conn)
            except Exception as e:
                print(e)

        if version == 197:
            # Cutover reconciliation: apiv4-only v184 tag_desktop_id mapping +
            # the v184/v185 apiv4 pagination indexes + the apiv4-and-websockets
            # v178 create_dict hardware backfill (disk_bus/isos/floppies/
            # personal_vlans, added at the end of this block). The mapping update
            # only touches rows still missing tag_desktop_id; index creation is
            # guarded on index_list.
            try:
                deployments = list(
                    r.table("deployments").pluck("id", "create_dict").run(self.conn)
                )
                deployment_tag_desktop_ids = {}
                for deployment in deployments:
                    if (
                        isinstance(deployment.get("create_dict"), list)
                        and len(deployment["create_dict"]) > 0
                    ):
                        deployment_tag_desktop_ids[deployment["id"]] = deployment[
                            "create_dict"
                        ][0].get("tag_desktop_id", False)
                deployment_map = r.expr(deployment_tag_desktop_ids)
                r.table(table).filter(
                    lambda d: d.has_fields("tag_desktop_id").not_()
                ).update(
                    lambda d: {
                        "tag_desktop_id": r.branch(
                            d["tag"].default(False).ne(False),
                            deployment_map[d["tag"]].default(False),
                            False,
                        )
                    }
                ).run(
                    self.conn
                )
            except Exception as e:
                print(e)
            for index_name, index_def in (
                ("tag_desktop_id", None),
                ("tag_tag_desktop_id", [r.row["tag"], r.row["tag_desktop_id"]]),
                ("kind_accessed", [r.row["kind"], r.row["accessed"]]),
                (
                    "enabled_kind_accessed",
                    [r.row["enabled"], r.row["kind"], r.row["accessed"]],
                ),
            ):
                try:
                    if index_name not in r.table(table).index_list().run(self.conn):
                        if index_def is None:
                            r.table(table).index_create(index_name).run(self.conn)
                        else:
                            r.table(table).index_create(index_name, index_def).run(
                                self.conn
                            )
                        r.table(table).index_wait(index_name).run(self.conn)
                except Exception as e:
                    print(e)
            # Port of apiv4-and-websockets v178 (SUPERSET): backfill create_dict
            # hardware fields (+ personal_vlans) on legacy domains migrated here
            # without ever running AW's private v178 (the fork minted 178-181
            # after the shared v177; this branch inherits main's numbering, so
            # AW's backfill ran in NO deployed lineage). _common reads these
            # unguarded (quotas.py, models/deployment.py, lib/users/.../user.py)
            # -> KeyError on a 100K-domain cutover. Parents are .default({})-
            # guarded on BOTH the filter and the update, so a malformed row
            # missing create_dict/hardware (exactly a row that would KeyError in
            # _common) is REPAIRED, not skipped -- a deliberate divergence from
            # strict v178. One scan + one targeted update; .default() per field
            # preserves already-present values. reservables is excluded -- v164
            # backfills create_dict.reservables.
            try:
                ids = list(
                    r.table(table)
                    .filter(
                        lambda d: d["create_dict"]
                        .default({})["hardware"]
                        .default({})
                        .has_fields("disk_bus")
                        .not_()
                        | d["create_dict"]
                        .default({})["hardware"]
                        .default({})
                        .has_fields("isos")
                        .not_()
                        | d["create_dict"]
                        .default({})["hardware"]
                        .default({})
                        .has_fields("floppies")
                        .not_()
                        | d["create_dict"]
                        .default({})
                        .has_fields("personal_vlans")
                        .not_()
                    )["id"]
                    .run(self.conn)
                )
                if ids:
                    r.table(table).get_all(r.args(ids)).update(
                        lambda d: {
                            "create_dict": {
                                "hardware": {
                                    "disk_bus": d["create_dict"]
                                    .default({})["hardware"]
                                    .default({})["disk_bus"]
                                    .default("default"),
                                    "isos": d["create_dict"]
                                    .default({})["hardware"]
                                    .default({})["isos"]
                                    .default([]),
                                    "floppies": d["create_dict"]
                                    .default({})["hardware"]
                                    .default({})["floppies"]
                                    .default([]),
                                },
                                "personal_vlans": d["create_dict"]
                                .default({})["personal_vlans"]
                                .default(False),
                            }
                        }
                    ).run(self.conn)
            except Exception as e:
                log.error(
                    "v197 cutover: domains create_dict hardware backfill "
                    f"(disk_bus/isos/floppies/personal_vlans) failed: {e}"
                )
        if version == 202:
            # kind_booking is superseded by the partial kind_valid_booking (the
            # one actually consumed). videos is KEPT: it has a live reader in the
            # alloweds-unassign / admin table-delete path (get_all index="videos").
            try:
                r.table(table).index_drop("kind_booking").run(self.conn)
            except Exception:
                pass

        return True

    """
    DEPLOYMENTS TABLE UPGRADES
    """

    def deployments(self, version):
        table = "deployments"
        # Pre-178 blocks iterate this snapshot; 178+ (incl. the 190->197 cutover)
        # is server-side and never reads it. Skip the full-table load (100K+ rows
        # on big installs, otherwise materialised once per version call).
        data = list(r.table(table).run(self.conn)) if version < 178 else []
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

        if version == 156:
            try:
                deployments = list(r.table(table).run(self.conn))

                for deployment in deployments:
                    ##### REMOVE FIELDS
                    self.del_keys(
                        table, [{"create_dict": {"user_permissions"}}], deployment["id"]
                    )
            except Exception as e:
                print(e)

        if version == 172:
            try:
                deployments = r.table(table).run(self.conn)
                updates = []
                for deployment in deployments:
                    create_dict_data = deployment["create_dict"]
                    update_data = {}
                    if not isinstance(create_dict_data, list):
                        # data that will be moved or added from create_dict into the root
                        update_data = {
                            "allowed": create_dict_data.get("allowed"),
                            "description": create_dict_data.get("description"),
                            "tag": create_dict_data.get("tag"),
                            "tag_name": create_dict_data.get("tag_name"),
                            "tag_visible": create_dict_data.get("tag_visible"),
                            "image": {"id": "1.jpg", "type": "stock", "url": ""},
                            "resources": [],
                        }

                        # data that will be added with empty value to match desktop structure
                        update_data["create_dict"] = {
                            "image": {"url": ""},
                            "hardware": {"disks": []},
                        }
                    updates.append({"id": deployment["id"], "data": update_data})

                if updates:
                    # update with new data structure
                    r.table(table).update(
                        lambda row: row.merge(
                            r.expr({u["id"]: u["data"] for u in updates})
                            .default({})[row["id"]]
                            .default({})
                        )
                    ).run(self.conn)

                    # remove old fields from create_dict
                    r.table(table).update(
                        lambda row: {
                            "create_dict": [
                                r.literal(
                                    row["create_dict"].without(
                                        "allowed",
                                        # "description",
                                        "tag",
                                        "tag_name",
                                        "tag_visible",
                                    )
                                )
                            ]
                        }
                    ).run(self.conn)
            except Exception as e:
                print(e)

            try:
                # Fix deployments with missing description and url fields
                deployments = r.table(table).run(self.conn)
                for deployment in deployments:
                    update_data = {}
                    needs_update = False

                    if "description" not in deployment:
                        update_data["description"] = ""
                        needs_update = True

                    if "image" in deployment and "url" not in deployment["image"]:
                        update_data["image"] = deployment["image"].copy()
                        update_data["image"]["url"] = ""
                        needs_update = True

                    if "create_dict" in deployment and isinstance(
                        deployment["create_dict"], list
                    ):
                        create_dict = []
                        for cd in deployment["create_dict"]:
                            if "description" not in cd:
                                cd["description"] = ""
                                needs_update = True

                            if "image" in cd and "url" not in cd["image"]:
                                cd["image"]["url"] = ""
                                needs_update = True

                            create_dict.append(cd)

                        update_data["create_dict"] = create_dict

                    if needs_update:
                        r.table(table).get(deployment["id"]).update(update_data).run(
                            self.conn
                        )

            except Exception as e:
                print(e)

        if version == 177:
            try:
                # Recreate the indexes considering the new structure under the create_dict list
                # Template
                # The index will match any of the templates in the create_dict list
                r.table(table).index_drop("template").run(self.conn)
                r.table(table).index_create(
                    "template",
                    lambda domain: domain["create_dict"].concat_map(
                        lambda data: [data["template"]]
                    ),
                    multi=True,
                ).run(self.conn)

                # Media
                r.table(table).index_drop("isos").run(self.conn)
                r.table(table).index_create(
                    "isos",
                    lambda domain: domain["create_dict"].concat_map(
                        lambda data: data["hardware"]["isos"].concat_map(
                            lambda iso: [iso["id"]]
                        )
                    ),
                    multi=True,
                ).run(self.conn)

                # Interfaces
                r.table(table).index_drop("interfaces").run(self.conn)
                r.table(table).index_create(
                    "interfaces",
                    lambda domain: domain["create_dict"].concat_map(
                        lambda data: data["hardware"]["interfaces"]
                    ),
                    multi=True,
                ).run(self.conn)

                # Boot
                r.table(table).index_drop("boot_order").run(self.conn)
                r.table(table).index_create(
                    "boot_order",
                    lambda domain: domain["create_dict"].concat_map(
                        lambda data: data["hardware"]["boot_order"]
                    ),
                    multi=True,
                ).run(self.conn)

                # Video
                r.table(table).index_drop("videos").run(self.conn)
                r.table(table).index_create(
                    "videos",
                    lambda domain: domain["create_dict"].concat_map(
                        lambda data: data["hardware"]["videos"]
                    ),
                    multi=True,
                ).run(self.conn)

                # Vgpus
                r.table(table).index_drop("vgpus").run(self.conn)
                r.table(table).index_create(
                    "vgpus",
                    lambda domain: domain["create_dict"].concat_map(
                        lambda data: data["reservables"]["vgpus"]
                    ),
                    multi=True,
                ).run(self.conn)

            except Exception as e:
                print(e)

        if version == 184:
            try:
                deployments = list(r.table(table).run(self.conn))
                for deployment in deployments:
                    tag_desktop_id = str(uuid4())
                    update_data = {}
                    # Add tag_desktop_id to each create_dict entry
                    if isinstance(deployment.get("create_dict"), list):
                        new_create_dict = []
                        for cd in deployment["create_dict"]:
                            if "tag_desktop_id" not in cd:
                                cd["tag_desktop_id"] = tag_desktop_id
                            new_create_dict.append(cd)
                        update_data["create_dict"] = new_create_dict
                    # Add image at deployment root if missing
                    if "image" not in deployment:
                        if (
                            isinstance(deployment.get("create_dict"), list)
                            and len(deployment["create_dict"]) > 0
                            and "image" in deployment["create_dict"][0]
                        ):
                            update_data["image"] = deployment["create_dict"][0]["image"]
                        else:
                            update_data["image"] = {
                                "id": "1.jpg",
                                "type": "stock",
                                "url": "",
                            }
                    # Add kind field
                    if "kind" not in deployment:
                        update_data["kind"] = "desktops"
                    if update_data:
                        r.table(table).get(deployment["id"]).update(update_data).run(
                            self.conn
                        )
            except Exception as e:
                print(e)

        if version == 197:
            # Cutover reconciliation: apiv4-only v184 deployments backfill
            # (tag_desktop_id / image / kind). Per-field guarded, so this is a
            # no-op on apiv4-lineage DBs.
            try:
                deployments = list(r.table(table).run(self.conn))
                for deployment in deployments:
                    tag_desktop_id = str(uuid4())
                    update_data = {}
                    if isinstance(deployment.get("create_dict"), list):
                        new_create_dict = []
                        changed = False
                        for cd in deployment["create_dict"]:
                            if "tag_desktop_id" not in cd:
                                cd["tag_desktop_id"] = tag_desktop_id
                                changed = True
                            new_create_dict.append(cd)
                        if changed:
                            update_data["create_dict"] = new_create_dict
                    if "image" not in deployment:
                        if (
                            isinstance(deployment.get("create_dict"), list)
                            and len(deployment["create_dict"]) > 0
                            and "image" in deployment["create_dict"][0]
                        ):
                            update_data["image"] = deployment["create_dict"][0]["image"]
                        else:
                            update_data["image"] = {
                                "id": "1.jpg",
                                "type": "stock",
                                "url": "",
                            }
                    if "kind" not in deployment:
                        update_data["kind"] = "desktops"
                    if update_data:
                        r.table(table).get(deployment["id"]).update(update_data).run(
                            self.conn
                        )
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

        if version == 188:
            try:
                r.table(table).index_create(
                    "status_accessed",
                    [r.row["status"], r.row["accessed"]],
                ).run(self.conn)
                r.table(table).index_wait("status_accessed").run(self.conn)
            except Exception as e:
                print(e)

        if version == 194:
            r.table(table).get_all(
                r.args(["Deleted", "FailedDeleted"]), index="status"
            ).update({"status": "deleted"}).run(self.conn)

        if version == 197:
            # Cutover reconciliation: apiv4-only v188 media status_accessed
            # index.
            try:
                if "status_accessed" not in r.table(table).index_list().run(self.conn):
                    r.table(table).index_create(
                        "status_accessed",
                        [r.row["status"], r.row["accessed"]],
                    ).run(self.conn)
                    r.table(table).index_wait("status_accessed").run(self.conn)
            except Exception as e:
                print(e)
        if version == 202:
            # Media quota accounting keys on status_user, never per-group.
            try:
                r.table(table).index_drop("status_group").run(self.conn)
            except Exception:
                pass

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

        if version == 184:
            groups_quota = list(
                r.table(table)
                .filter(lambda group: r.not_(group["quota"] == False))
                .run(self.conn)
            )
            for group in groups_quota:
                quota = group["quota"]
                self.add_keys(
                    table,
                    [
                        {
                            "quota": {
                                "deployment_users": quota.get(
                                    "deployment_desktops", 999
                                ),
                            }
                        },
                    ],
                    group["id"],
                )
                r.table(table).get(group["id"]).update(
                    {"quota": {"deployment_desktops": 999}}
                ).run(self.conn)

            groups_limits = list(
                r.table(table)
                .filter(lambda group: r.not_(group["limits"] == False))
                .run(self.conn)
            )
            for group in groups_limits:
                limits = group["limits"]
                self.add_keys(
                    table,
                    [
                        {
                            "limits": {
                                "deployment_users": limits.get(
                                    "deployment_desktops", 999
                                ),
                            }
                        },
                    ],
                    group["id"],
                )

        if version == 197:
            # Cutover reconciliation (see release_version header): re-assert
            # the apiv4-only v184 deployment_users quota/limits split for
            # main-lineage DBs that never ran it. Guarded on key ABSENCE so an
            # apiv4-lineage DB (or an admin-tuned value) is never overwritten.
            # Server-side single pass per field (was a per-row Python loop ->
            # up to 20K round-trips on users). Select rows where the field is
            # set (!= False) and lacks deployment_users; fill it from the old
            # deployment_desktops (default 999). For quota, also reset
            # deployment_desktops to 999 in the SAME update -- the lambda reads
            # the original row, so deployment_users still captures the old value.
            try:
                for field in ("quota", "limits"):
                    selected = r.table(table).filter(
                        lambda row: r.not_(row[field] == False)
                        & row[field].default({}).has_fields("deployment_users").not_()
                    )
                    if field == "quota":
                        selected.update(
                            lambda row: {
                                "quota": {
                                    "deployment_users": row["quota"]
                                    .default({})["deployment_desktops"]
                                    .default(999),
                                    "deployment_desktops": 999,
                                }
                            }
                        ).run(self.conn)
                    else:
                        selected.update(
                            lambda row: {
                                field: {
                                    "deployment_users": row[field]
                                    .default({})["deployment_desktops"]
                                    .default(999)
                                }
                            }
                        ).run(self.conn)
            except Exception as e:
                log.error(
                    f"v197 cutover: {table} deployment_users quota/limits "
                    f"split failed: {e}"
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

        if version == 147:
            r.table("videos").insert(
                [
                    {
                        "allowed": {
                            "categories": False,
                            "groups": False,
                            "roles": ["admin"],
                            "users": False,
                        },
                        "description": "Virtio default video profile",
                        "heads": 1,
                        "model": "virtio",
                        "name": "Virtio",
                        "ram": 0,
                        "vram": 0,
                    },
                ]
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
        if version == 144:
            try:
                r.table("users").filter(
                    lambda user: r.not_(user.has_fields("password_history"))
                ).update(lambda user: {"password_history": [user["password"]]}).run(
                    self.conn
                )
                r.table("users").filter(
                    lambda user: r.not_(user.has_fields("password_last_updated"))
                ).update(lambda user: {"password_last_updated": int(time.time())}).run(
                    self.conn
                )
                r.table("users").filter(
                    lambda user: r.not_(user.has_fields("email_verified"))
                ).update(lambda user: {"email_verified": None}).run(self.conn)
            except Exception as e:
                print(e)
        if version == 168:
            try:
                self.add_keys(table, [{"api_key": None}])
            except Exception as e:
                print(e)

        if version == 184:
            users_quota = list(
                r.table(table)
                .filter(lambda user: r.not_(user["quota"] == False))
                .run(self.conn)
            )
            for user in users_quota:
                quota = user["quota"]
                self.add_keys(
                    table,
                    [
                        {
                            "quota": {
                                "deployment_users": quota.get(
                                    "deployment_desktops", 999
                                ),
                            }
                        },
                    ],
                    user["id"],
                )
                r.table(table).get(user["id"]).update(
                    {"quota": {"deployment_desktops": 999}}
                ).run(self.conn)

        if version == 197:
            # Cutover reconciliation (see release_version header): re-assert
            # the apiv4-only v184 deployment_users quota/limits split for
            # main-lineage DBs that never ran it. Guarded on key ABSENCE so an
            # apiv4-lineage DB (or an admin-tuned value) is never overwritten.
            # Server-side single pass per field (was a per-row Python loop ->
            # up to 20K round-trips on users). Select rows where the field is
            # set (!= False) and lacks deployment_users; fill it from the old
            # deployment_desktops (default 999). For quota, also reset
            # deployment_desktops to 999 in the SAME update -- the lambda reads
            # the original row, so deployment_users still captures the old value.
            try:
                for field in ("quota", "limits"):
                    selected = r.table(table).filter(
                        lambda row: r.not_(row[field] == False)
                        & row[field].default({}).has_fields("deployment_users").not_()
                    )
                    if field == "quota":
                        selected.update(
                            lambda row: {
                                "quota": {
                                    "deployment_users": row["quota"]
                                    .default({})["deployment_desktops"]
                                    .default(999),
                                    "deployment_desktops": 999,
                                }
                            }
                        ).run(self.conn)
                    else:
                        selected.update(
                            lambda row: {
                                field: {
                                    "deployment_users": row[field]
                                    .default({})["deployment_desktops"]
                                    .default(999)
                                }
                            }
                        ).run(self.conn)
            except Exception as e:
                log.error(
                    f"v197 cutover: {table} deployment_users quota/limits "
                    f"split failed: {e}"
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

        if version == 146:
            try:
                r.table(table).index_create(
                    "disclaimer_template", r.row["disclaimer"]["template"]
                ).run(self.conn)
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

        if version == 150:
            try:
                print(
                    "--- Starting retrieval of storages and its matching domain... ---"
                )
                start = datetime.datetime.now()
                storages = list(
                    r.db("isard")
                    .table("storage")
                    .eq_join("id", r.db("isard").table("domains"), index="storage_ids")
                    .filter(
                        lambda result: result.has_fields(
                            {"right": "duplicate_parent_template"}
                        ).not_()
                    )
                    .pluck(
                        {"left": {"id": True, "user_id": True}, "right": {"user": True}}
                    )
                    .run(self.conn)
                )

                print(datetime.datetime.now() - start)
                print(f"Query finished in {datetime.datetime.now() - start}")
                print(f"Found {len(storages)} storages")

                storage_user_not_match_domain_user = list(
                    filter(
                        lambda item: item["left"]["user_id"] != item["right"]["user"],
                        storages,
                    )
                )
                print(
                    f"--- Found {len(storage_user_not_match_domain_user)} storages that the owner does not match the domain owner. Updating storages... ---"
                )

                for item in storage_user_not_match_domain_user:
                    print(f"Updating storage {item['left']['id']}...")
                    r.db("isard").table("storage").get(item["left"]["id"]).update(
                        {
                            "user_id": item["right"]["user"],
                        }
                    ).run(self.conn)
                print(
                    f"--- Storages update finished in {datetime.datetime.now() - start} ---"
                )

            except Exception as e:
                print(e)

        if version == 174:
            try:
                r.table(table).index_create("task").run(self.conn)
            except Exception as e:
                print(e)

        if version == 186:
            try:
                # Find storage records missing user_id
                broken_ids = list(
                    r.table(table)
                    .filter(lambda s: s.has_fields("user_id").not_())["id"]
                    .run(self.conn)
                )
                print(
                    f"--- Found {len(broken_ids)} storage records missing user_id ---"
                )

                if broken_ids:
                    # Phase 1: Try to repair from domain relationship
                    repairable = list(
                        r.table(table)
                        .get_all(r.args(broken_ids))
                        .eq_join("id", r.table("domains"), index="storage_ids")
                        .pluck({"left": {"id": True}, "right": {"user": True}})
                        .run(self.conn)
                    )
                    repaired_ids = set()
                    for item in repairable:
                        r.table(table).get(item["left"]["id"]).update(
                            {"user_id": item["right"]["user"]}
                        ).run(self.conn)
                        repaired_ids.add(item["left"]["id"])
                    print(
                        f"--- Repaired {len(repaired_ids)} storage records from domain owner ---"
                    )

                    # Phase 2: Try to repair backing files by tracing children
                    # to their domain owners, preferring template owners since
                    # backing files typically belong to templates
                    unrepairable_ids = [
                        sid for sid in broken_ids if sid not in repaired_ids
                    ]
                    if unrepairable_ids:
                        for sid in unrepairable_ids:
                            # Get children that have a user_id
                            children = list(
                                r.table(table)
                                .get_all(sid, index="parent")
                                .has_fields("user_id")
                                .pluck("id", "user_id")
                                .run(self.conn)
                            )
                            if not children:
                                continue

                            # Find domains that own these child storages
                            child_ids = [c["id"] for c in children]
                            child_domains = list(
                                r.table("domains")
                                .get_all(r.args(child_ids), index="storage_ids")
                                .pluck("user", "kind")
                                .run(self.conn)
                            )

                            # Prefer the template domain owner (backing files belong to templates)
                            template_owner = None
                            any_owner = None
                            for d in child_domains:
                                if d.get("kind") == "template":
                                    template_owner = d["user"]
                                    break
                                if any_owner is None:
                                    any_owner = d["user"]

                            owner = template_owner or any_owner
                            if owner:
                                r.table(table).get(sid).update({"user_id": owner}).run(
                                    self.conn
                                )
                                repaired_ids.add(sid)
                                print(
                                    f"--- Repaired storage {sid} from {'template' if template_owner else 'child'} domain owner ---"
                                )

                    # Phase 3: Delete truly orphaned records (no domain, no children with user_id)
                    still_broken = [
                        sid for sid in broken_ids if sid not in repaired_ids
                    ]
                    if still_broken:
                        print(
                            f"--- Deleting {len(still_broken)} unrepairable storage records ---"
                        )
                        r.table(table).get_all(r.args(still_broken)).delete().run(
                            self.conn
                        )

                # Ensure all records have perms and status_logs
                r.table(table).filter(lambda s: s.has_fields("perms").not_()).update(
                    {"perms": ["r", "w"]}
                ).run(self.conn)

                r.table(table).filter(
                    lambda s: s.has_fields("status_logs").not_()
                ).update({"status_logs": []}).run(self.conn)

            except Exception as e:
                print(e)

        if version == 187:
            table = "recycle_bin"
            try:
                # Add compound indexes for range queries on status + accessed time
                try:
                    r.table(table).index_create(
                        "status_accessed", [r.row["status"], r.row["accessed"]]
                    ).run(self.conn)
                except Exception:
                    pass
                try:
                    r.table(table).index_create(
                        "owner_category_status_accessed",
                        [
                            r.row["owner_category_id"],
                            r.row["status"],
                            r.row["accessed"],
                        ],
                    ).run(self.conn)
                except Exception:
                    pass
                r.table(table).index_wait().run(self.conn)
                print("--- Created recycle_bin compound indexes ---")

                # Backfill pre-computed count fields and last_log
                r.table(table).update(
                    lambda rb: {
                        "desktops_count": rb["desktops"].default([]).count(),
                        "templates_count": rb["templates"].default([]).count(),
                        "storages_count": rb["storages"].default([]).count(),
                        "deployments_count": rb["deployments"].default([]).count(),
                        "categories_count": rb["categories"].default([]).count(),
                        "groups_count": rb["groups"].default([]).count(),
                        "users_count": rb["users"].default([]).count(),
                        "last_log": rb["logs"].default([]).nth(-1).default(None),
                    }
                ).run(self.conn)
                print("--- Backfilled recycle_bin count fields ---")
            except Exception as e:
                print(e)

        if version == 197:
            # Cutover reconciliation: apiv4-only v187 recycle_bin compound
            # indexes (pentest-surfaced 500s when missing) + the v187
            # pre-computed count/last_log backfill.
            table = "recycle_bin"
            for index_name, index_def in (
                ("status_accessed", [r.row["status"], r.row["accessed"]]),
                (
                    "owner_category_status_accessed",
                    [
                        r.row["owner_category_id"],
                        r.row["status"],
                        r.row["accessed"],
                    ],
                ),
            ):
                try:
                    if index_name not in r.table(table).index_list().run(self.conn):
                        r.table(table).index_create(index_name, index_def).run(
                            self.conn
                        )
                        r.table(table).index_wait(index_name).run(self.conn)
                except Exception as e:
                    print(e)
            # Backfill pre-computed count fields + last_log on rows predating
            # apiv4 v187. Guarded on desktops_count absence -> no-op on
            # apiv4-lineage DBs. Consumers (helpers/recycle_bin.py) already
            # .default() to a live recompute, so this is perf-only.
            try:
                ids = list(
                    r.table(table)
                    .filter(lambda rb: rb.has_fields("desktops_count").not_())["id"]
                    .run(self.conn)
                )
                if ids:
                    r.table(table).get_all(r.args(ids)).update(
                        lambda rb: {
                            "desktops_count": rb["desktops"].default([]).count(),
                            "templates_count": rb["templates"].default([]).count(),
                            "storages_count": rb["storages"].default([]).count(),
                            "deployments_count": rb["deployments"].default([]).count(),
                            "categories_count": rb["categories"].default([]).count(),
                            "groups_count": rb["groups"].default([]).count(),
                            "users_count": rb["users"].default([]).count(),
                            "last_log": rb["logs"].default([]).nth(-1).default(None),
                        }
                    ).run(self.conn)
            except Exception as e:
                log.error(
                    f"v197 cutover: recycle_bin count/last_log backfill failed: {e}"
                )

        if version == 201:
            table = "storage"
            try:
                non_uuid_filter = (  # noqa: E731
                    lambda s: s["parent"]
                    .default("")
                    .type_of()
                    .eq("STRING")
                    .and_(s["parent"].default("").match(r"^/|\.qcow2$"))
                )
                total = r.table(table).filter(non_uuid_filter).count().run(self.conn)
                log.info(
                    f"--- Storage parent normalisation: {total} non-UUID rows to migrate ---"
                )
                if total > 0:
                    batch_size = 10_000
                    processed = 0
                    while True:
                        result = (
                            r.table(table)
                            .filter(non_uuid_filter)
                            .limit(batch_size)
                            .update(
                                lambda s: {
                                    "parent": s["parent"]
                                    .split("/")
                                    .nth(-1)
                                    .split(".")
                                    .nth(0)
                                }
                            )
                            .run(self.conn)
                        )
                        replaced = result.get("replaced", 0)
                        if replaced == 0:
                            break
                        processed += replaced
                        log.info(
                            f"--- Storage parent normalisation: {processed}/{total} migrated ---"
                        )
                    log.info(
                        f"--- Storage parent normalisation: complete ({processed} rows) ---"
                    )
            except Exception as e:
                print(e)

        return True

    def gpu_profiles(self, version):
        ## Moved to _system_upgrades function that it's taken into account once each engine restart
        ## so no more upgrades for gpu_profiles needed. But keeping the function to not break the code
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

    def bookings(self, version):
        table = "bookings"
        log.info("UPGRADING " + table + " VERSION " + str(version))
        if version == 148:
            try:
                r.table(table).index_create("item_type").run(self.conn)
                r.table(table).index_wait("item_type").run(self.conn)
            except Exception as e:
                print(e)

    """
    BOOKINGS PRIORITY TABLE UPGRADES
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

        if version == 163:
            try:
                categories = list(
                    r.table(table).pluck("allowed_domain", "id").run(self.conn)
                )

                for category in categories:
                    try:
                        allowed_domains = (
                            [category["allowed_domain"]]
                            if category.get("allowed_domain")
                            else []
                        )

                        self.add_keys(
                            table,
                            [
                                {
                                    "authentication": {
                                        "local": {
                                            "enabled": None,
                                            "allowed_domains": allowed_domains,
                                        },
                                        "google": {
                                            "enabled": None,
                                            "allowed_domains": allowed_domains,
                                        },
                                        "saml": {
                                            "enabled": None,
                                            "allowed_domains": allowed_domains,
                                        },
                                        "ldap": {
                                            "enabled": None,
                                            "allowed_domains": allowed_domains,
                                        },
                                    }
                                }
                            ],
                            id=category["id"],
                        )

                    except Exception as e:
                        print(e)

                r.table(table).replace(
                    lambda category: category.without("allowed_domain")
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 166:
            try:
                r.table(table).update(
                    {"authentication": {"local": {"allowed_domains": []}}}
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 167:
            try:
                self.del_keys("categories", ["max_delete_period"])
                deleted_job_categories = list(
                    r.table("scheduler_jobs")
                    .filter(lambda job: job["id"].match("\\.recycle_bin_delete$"))
                    .pluck("kwargs")["kwargs"]
                    .run(self.conn)
                )
                self.add_keys("categories", [{"recycle_bin_cutoff_time": None}])
                for category_job in deleted_job_categories:
                    r.table("categories").get(category_job["category"]).update(
                        {
                            "recycle_bin_cutoff_time": int(
                                category_job["max_delete_period"]
                            )
                        }
                    ).run(self.conn)
                r.table("scheduler_jobs").filter(
                    lambda job: job["id"].match("\\.recycle_bin_delete$")
                ).delete().run(self.conn)
            except Exception as e:
                print(e)

        if version == 170:
            try:
                r.table(table).update({"bastion_domain": None}).run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create("bastion_domain").run(self.conn)
            except Exception as e:
                print(e)

        if version == 184:
            categories_quota = list(
                r.table(table)
                .filter(lambda category: r.not_(category["quota"] == False))
                .run(self.conn)
            )
            for category in categories_quota:
                quota = category["quota"]
                self.add_keys(
                    table,
                    [
                        {
                            "quota": {
                                "deployment_users": quota.get(
                                    "deployment_desktops", 999
                                ),
                            }
                        },
                    ],
                    category["id"],
                )
                r.table(table).get(category["id"]).update(
                    {"quota": {"deployment_desktops": 999}}
                ).run(self.conn)

            categories_limits = list(
                r.table(table)
                .filter(lambda category: r.not_(category["limits"] == False))
                .run(self.conn)
            )
            for category in categories_limits:
                limits = category["limits"]
                self.add_keys(
                    table,
                    [
                        {
                            "limits": {
                                "deployment_users": limits.get(
                                    "deployment_desktops", 999
                                ),
                            }
                        },
                    ],
                    category["id"],
                )

        if version == 186:
            config_map = {
                None: {
                    "disabled": False,
                    "email_domain_restriction-enabled": False,
                },
                False: {
                    "disabled": True,
                    "email_domain_restriction-enabled": False,
                },
                True: {
                    "disabled": False,
                    "email_domain_restriction-enabled": True,
                },
            }
            categories = list(r.table(table).run(self.conn))
            for category in categories:
                for provider in category.get("authentication", {}).values():
                    mapped = config_map[provider.get("enabled", None)]
                    allowed_domains = provider.get("allowed_domains", [])
                    provider["disabled"] = mapped["disabled"]
                    provider["config_source"] = "global"
                    provider["email_domain_restriction"] = {
                        "enabled": mapped["email_domain_restriction-enabled"]
                        and bool(allowed_domains),
                        "allowed": allowed_domains,
                    }
                    provider.pop("allowed_domains", None)
                    provider.pop("enabled", None)
            r.table(table).insert(categories, conflict="replace").run(self.conn)

        if version == 195:
            provider_status = {
                "healthy": False,
                "msg": "",
                "last_updated": r.epoch_time(0),
            }
            categories = list(r.table(table).run(self.conn))
            for category in categories:
                for provider in category.get("authentication", {}).values():
                    if isinstance(provider, dict):
                        provider["status"] = dict(provider_status)
            r.table(table).insert(categories, conflict="replace").run(self.conn)

        if version == 197:
            # Cutover reconciliation (see release_version header): re-assert
            # the apiv4-only v184 deployment_users quota/limits split for
            # main-lineage DBs that never ran it. Guarded on key ABSENCE so an
            # apiv4-lineage DB (or an admin-tuned value) is never overwritten.
            # Server-side single pass per field (was a per-row Python loop ->
            # up to 20K round-trips on users). Select rows where the field is
            # set (!= False) and lacks deployment_users; fill it from the old
            # deployment_desktops (default 999). For quota, also reset
            # deployment_desktops to 999 in the SAME update -- the lambda reads
            # the original row, so deployment_users still captures the old value.
            try:
                for field in ("quota", "limits"):
                    selected = r.table(table).filter(
                        lambda row: r.not_(row[field] == False)
                        & row[field].default({}).has_fields("deployment_users").not_()
                    )
                    if field == "quota":
                        selected.update(
                            lambda row: {
                                "quota": {
                                    "deployment_users": row["quota"]
                                    .default({})["deployment_desktops"]
                                    .default(999),
                                    "deployment_desktops": 999,
                                }
                            }
                        ).run(self.conn)
                    else:
                        selected.update(
                            lambda row: {
                                field: {
                                    "deployment_users": row[field]
                                    .default({})["deployment_desktops"]
                                    .default(999)
                                }
                            }
                        ).run(self.conn)
            except Exception as e:
                log.error(
                    f"v197 cutover: {table} deployment_users quota/limits "
                    f"split failed: {e}"
                )
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
        if version == 145:
            try:
                r.table(table).get("limit50MBps").update(
                    {
                        "iotune": {
                            # throughput limit in bytes per second.
                            "read_bytes_sec": 50 * 1024 * 1024,
                            "write_bytes_sec": 50 * 1024 * 1024,
                            # maximum throughput limit in bytes per second.
                            "read_bytes_sec_max": 80 * 1024 * 1024,
                            "write_bytes_sec_max": 80 * 1024 * 1024,
                            # maximum duration in seconds for the write_bytes_sec_max burst period.
                            # Only valid when the bytes_sec_max is set.
                            "read_bytes_sec_max_length": 2,
                            "write_bytes_sec_max_length": 2,
                            # I/O operations per second.
                            "read_iops_sec": 10000,
                            "write_iops_sec": 10000,
                            # maximum read I/O operations per second.
                            "read_iops_sec_max": 15000,
                            "write_iops_sec_max": 15000,
                            "size_iops_sec": 4 * 1024,
                            # maximum duration in seconds for the read_iops_sec_max burst period.
                            # Only valid when the iops_sec_max is set.
                            "read_iops_sec_max_length": 2,
                            "write_iops_sec_max_length": 2,
                        },
                        "allowed": {
                            "roles": False,
                            "categories": False,
                            "groups": False,
                            "users": False,
                        },
                    }
                ).run(self.conn)
                r.table(table).get("unlimited").update(
                    {
                        "allowed": {
                            "roles": False,
                            "categories": False,
                            "groups": False,
                            "users": False,
                        },
                    }
                ).run(self.conn)
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

        if version == 202:
            # Written on every login-session row but read by no index query.
            for _dead in ("stopped_time", "owner_group_id"):
                try:
                    r.table(table).index_drop(_dead).run(self.conn)
                except Exception:
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

        if version == 152:
            try:
                r.table(table).index_create(
                    "owner_group_status",
                    [r.row["owner_group_id"], r.row["status"]],
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 184:
            try:
                r.table(table).index_create(
                    "status_accessed",
                    [r.row["status"], r.row["accessed"]],
                ).run(self.conn)
                r.table(table).index_wait("status_accessed").run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create(
                    "owner_category_status_accessed",
                    [
                        r.row["owner_category_id"],
                        r.row["status"],
                        r.row["accessed"],
                    ],
                ).run(self.conn)
                r.table(table).index_wait("owner_category_status_accessed").run(
                    self.conn
                )
            except Exception as e:
                print(e)

            try:
                r.table(table).update(
                    lambda doc: {
                        "desktops_count": doc["desktops"].count(),
                        "templates_count": doc["templates"].count(),
                        "storages_count": doc["storages"].count(),
                        "deployments_count": doc["deployments"].count(),
                        "users_count": doc["users"].count(),
                        "groups_count": doc["groups"].count(),
                        "categories_count": doc["categories"].count(),
                        "last_log": r.branch(
                            doc["logs"].count().gt(0),
                            doc["logs"].nth(-1),
                            None,
                        ),
                    }
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 202:
            # agent_status has no reader. The reverse-lookup multi indexes over
            # the delete-entry arrays (storage/desktop/template/user/group/
            # category) ARE consumed via the generic admin table endpoint's
            # get_all(id, index=<kind>), so they are KEPT.
            try:
                r.table(table).index_drop("agent_status").run(self.conn)
            except Exception:
                pass

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

        if version == 202:
            # Drop dead indexes that cost a B-tree write on every session insert
            # but are read by no query. Kept (consumed): desktop_id,
            # owner_user_id, owner_category_id, started_time, starting_time.
            for _dead in (
                "desktop_template_hierarchy",
                "stopped_time",
                "stopped_status",
                "started_by",
                "stopped_by",
                "owner_group_id",
                "deployment_id",
            ):
                try:
                    r.table(table).index_drop(_dead).run(self.conn)
                except Exception:
                    pass

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
                # By this point the v64 migration ("move hypervisor_pools paths to
                # storage_pool") has already (re)created the default pool with
                # absolute /isard/* paths and a lowercased name. Normalise it:
                #  - fresh install: populate.py seeded mountpoint
                #    /isard/storage_pools/default (preserved through v64's
                #    conflict="update") -> restore RELATIVE paths so disks land
                #    under that named mountpoint instead of /isard/groups;
                #  - existing install (default still at /isard) -> leave the legacy
                #    layout untouched;
                #  - no default at all -> (re)create the legacy /isard default.
                default_pool = (
                    r.table(table)
                    .get("00000000-0000-0000-0000-000000000000")
                    .run(self.conn)
                )
                if not default_pool:
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
                elif default_pool.get("mountpoint") == "/isard/storage_pools/default":
                    r.table(table).get("00000000-0000-0000-0000-000000000000").update(
                        {
                            "name": "Default",
                            "paths": {
                                "desktop": [{"path": "desktops", "weight": 100}],
                                "template": [{"path": "templates", "weight": 100}],
                                "media": [{"path": "media", "weight": 100}],
                                "volatile": [{"path": "volatile", "weight": 100}],
                            },
                        }
                    ).run(self.conn)
                elif not default_pool.get("mountpoint"):
                    # Direct upgrade from a version <121: v64 (re)created the
                    # default pool with absolute /isard/* paths and NO mountpoint,
                    # so "{mountpoint}/{path}" would later resolve to
                    # "None//isard/groups". Restore the legacy /isard mountpoint
                    # with relative paths so disks resolve under it.
                    r.table(table).get("00000000-0000-0000-0000-000000000000").update(
                        {
                            "mountpoint": "/isard",
                            "name": "Default",
                            "paths": {
                                "desktop": [{"path": "groups", "weight": 100}],
                                "template": [{"path": "templates", "weight": 100}],
                                "media": [{"path": "media", "weight": 100}],
                                "volatile": [{"path": "volatile", "weight": 100}],
                            },
                        }
                    ).run(self.conn)
            except Exception as e:
                print(e)
            try:
                r.table(table).index_create("name").run(self.conn)
            except Exception as e:
                pass

        if version == 151:
            try:
                storage_pools = r.table(table).run(self.conn)
                for storage_pool in storage_pools:
                    enabled_virt = storage_pool.get("enabled", False)
                    r.table(table).get(storage_pool["id"]).update(
                        {"enabled_virt": enabled_virt}
                    ).run(self.conn)
            except Exception as e:
                print(e)

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

        if version == 169:
            try:
                r.table(table).update({"role_id": "manager"}).run(self.conn)
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
        if version == 158:
            try:
                r.table(table).insert(
                    [
                        {
                            "default": "en",
                            "description": "Text that will be associated with each notification sent to the user when a desktop is not used for a long time and is sent to the recycle bin.",
                            "kind": "unused_desktops",
                            "lang": {
                                "ca": {
                                    "body": "<p>L'escriptori <b>{name}</b>, que va ser utilitzat per últim cop en data <b>{accessed}</b>.</p>",
                                    "footer": "Si us plau, esborreu els escriptoris que ja no s'utilitzaran.",
                                    "title": "Escriptoris sense utilitzar han estat eliminats",
                                },
                                "en": {
                                    "body": "<p>Desktop <b>{name}</b>, last time used at <b>{accessed}</b>.</p>",
                                    "footer": "Please, delete desktops that won't be used anymore.",
                                    "title": "Unused desktops have been deleted",
                                },
                                "es": {
                                    "body": "<p>El escritorio <b>{name}</b>, que fue utilizado por última vez en fecha <b>{accessed}</b>.</p>",
                                    "footer": "Por favor, elimine los escritorios que ya no se utilizarán.",
                                    "title": "Escritorios sin utilizar han sido eliminados",
                                },
                            },
                            "name": "Send unused desktops to recycle bin",
                            "system": {
                                "body": "<p>Desktop <b>{name}</b>, last time used at <b>{accessed}</b>.</p>",
                                "footer": "Please, delete desktops that won't be used anymore.",
                                "title": "Unused desktops have been deleted",
                            },
                            "vars": {
                                "name": "Testing environment",
                                "accessed": "12 Mar 2024 13:00",
                            },
                        },
                    ]
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 162:
            try:
                r.table(table).insert(
                    [
                        {
                            "default": "en",
                            "description": "Text that will be associated with each notification sent to the user when a deployment is not used for a long time and is sent to the recycle bin.",
                            "kind": "unused_deployments",
                            "lang": {
                                "ca": {
                                    "body": "<p>El desplegament <b>{name}</b>, que va ser utilitzat per últim cop en data <b>{accessed}</b>.</p>",
                                    "footer": "Si us plau, esborreu els desplegaments que ja no s'utilitzaran.",
                                    "title": "Desplegaments sense utilitzar han estat eliminats",
                                },
                                "en": {
                                    "body": "<p>Deployment <b>{name}</b>, last time used at <b>{accessed}</b>.</p>",
                                    "footer": "Please, delete deployments that won't be used anymore.",
                                    "title": "Unused deployments have been deleted",
                                },
                                "es": {
                                    "body": "<p>El despliegue <b>{name}</b>, que fue utilizado por última vez en fecha <b>{accessed}</b>.</p>",
                                    "footer": "Por favor, elimine los despliegues que ya no se utilizarán.",
                                    "title": "Despliegues sin utilizar han sido eliminados",
                                },
                            },
                            "name": "Send unused deployments to recycle bin",
                            "system": {
                                "body": "<p>Deployment <b>{name}</b>, last time used at <b>{accessed}</b>.</p>",
                                "footer": "Please, delete desployments that won't be used anymore.",
                                "title": "Unused deployments have been deleted",
                            },
                            "vars": {
                                "name": "Testing environment deployment",
                                "accessed": "12 Mar 2024 13:00",
                            },
                        },
                    ]
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 171:
            try:
                r.table(table).insert(
                    [
                        {
                            "default": "en",
                            "description": "Text that will be shown if bastion is enabled and the user is starting a desktop with bastion.",
                            "kind": "bastion_enabled_disclaimer",
                            "lang": {
                                "ca": {
                                    "body": "<p>The desktop <b>{desktop_name}</b>, has bastion enabled. Please, beware of its risks.</p>",
                                    "footer": "",
                                    "title": "Desktop with bastion enabled",
                                },
                                "en": {
                                    "body": "<p>The desktop <b>{desktop_name}</b>, has bastion enabled. Please, beware of its risks.</p>",
                                    "footer": "",
                                    "title": "Desktop with bastion enabled",
                                },
                                "es": {
                                    "body": "<p>The desktop <b>{desktop_name}</b>, has bastion enabled. Please, beware of its risks.</p>",
                                    "footer": "",
                                    "title": "Desktop with bastion enabled",
                                },
                            },
                            "name": "Bastion enabled disclaimer",
                            "system": {
                                "body": "<p>The desktop <b>{desktop_name}</b>, has bastion enabled. Please, beware of its risks.</p>",
                                "footer": "",
                                "title": "Desktop with bastion enabled",
                            },
                            "vars": {
                                "desktop_name": "Testing desktop",
                            },
                        },
                    ]
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 193:
            # Existence-guarded: a main-lineage DB ran the same id-less inserts as its v188 —
            # a blind re-run on the cutover path would duplicate them.
            if (
                r.table(table)
                .filter({"kind": "unused_deployment_desktops_owner"})
                .count()
                .run(self.conn)
                > 0
            ):
                return True
            try:
                r.table(table).insert(
                    [
                        {
                            "default": "en",
                            "description": "Text that will be associated with each notification sent to a deployment owner when a desktop of their deployment is not used for a long time and is sent to the recycle bin.",
                            "kind": "unused_deployment_desktops_owner",
                            "lang": {
                                "ca": {
                                    "body": "<p>L'escriptori <b>{desktop_name}</b> del desplegament <b>{deployment_name}</b>, propietat de <b>{desktop_owner}</b>, va ser utilitzat per últim cop el <b>{accessed}</b>.</p>",
                                    "footer": "Podeu restaurar-los des de la paperera si encara són necessaris.",
                                    "title": "Escriptoris de desplegament sense utilitzar han estat eliminats",
                                },
                                "en": {
                                    "body": "<p>Desktop <b>{desktop_name}</b> from deployment <b>{deployment_name}</b>, owned by <b>{desktop_owner}</b>, was last used at <b>{accessed}</b>.</p>",
                                    "footer": "You can restore them from the recycle bin if they are still needed.",
                                    "title": "Unused deployment desktops have been deleted",
                                },
                                "es": {
                                    "body": "<p>El escritorio <b>{desktop_name}</b> del despliegue <b>{deployment_name}</b>, propiedad de <b>{desktop_owner}</b>, fue utilizado por última vez el <b>{accessed}</b>.</p>",
                                    "footer": "Puede restaurarlos desde la papelera si aún son necesarios.",
                                    "title": "Escritorios de despliegue sin utilizar han sido eliminados",
                                },
                            },
                            "name": "Send unused deployment desktops to recycle bin (deployment owner)",
                            "system": {
                                "body": "<p>Desktop <b>{desktop_name}</b> from deployment <b>{deployment_name}</b>, owned by <b>{desktop_owner}</b>, was last used at <b>{accessed}</b>.</p>",
                                "footer": "You can restore them from the recycle bin if they are still needed.",
                                "title": "Unused deployment desktops have been deleted",
                            },
                            "vars": {
                                "desktop_name": "Testing desktop",
                                "desktop_owner": "John Doe",
                                "deployment_name": "Testing environment deployment",
                                "accessed": "12 Mar 2024 13:00",
                            },
                        },
                        {
                            "default": "en",
                            "description": "Text that will be associated with each notification sent to a desktop owner when their deployment desktop is not used for a long time and is moved to the deployment recycle bin (which is owned by the deployment creator).",
                            "kind": "unused_deployment_desktops_user",
                            "lang": {
                                "ca": {
                                    "body": "<p>El vostre escriptori <b>{desktop_name}</b> del desplegament <b>{deployment_name}</b> (propietat de <b>{deployment_owner}</b>) va ser utilitzat per últim cop el <b>{accessed}</b>.</p>",
                                    "footer": "Contacteu amb el propietari del desplegament si encara necessiteu l'escriptori.",
                                    "title": "El vostre escriptori de desplegament ha estat eliminat",
                                },
                                "en": {
                                    "body": "<p>Your desktop <b>{desktop_name}</b> from deployment <b>{deployment_name}</b> (owned by <b>{deployment_owner}</b>) was last used at <b>{accessed}</b>.</p>",
                                    "footer": "Contact the deployment owner if you still need the desktop.",
                                    "title": "Your deployment desktop has been deleted",
                                },
                                "es": {
                                    "body": "<p>Su escritorio <b>{desktop_name}</b> del despliegue <b>{deployment_name}</b> (propiedad de <b>{deployment_owner}</b>) fue utilizado por última vez el <b>{accessed}</b>.</p>",
                                    "footer": "Contacte con el propietario del despliegue si aún necesita el escritorio.",
                                    "title": "Su escritorio de despliegue ha sido eliminado",
                                },
                            },
                            "name": "Your deployment desktop has been sent to the recycle bin (desktop owner)",
                            "system": {
                                "body": "<p>Your desktop <b>{desktop_name}</b> from deployment <b>{deployment_name}</b> (owned by <b>{deployment_owner}</b>) was last used at <b>{accessed}</b>.</p>",
                                "footer": "Contact the deployment owner if you still need the desktop.",
                                "title": "Your deployment desktop has been deleted",
                            },
                            "vars": {
                                "desktop_name": "Testing desktop",
                                "deployment_name": "Testing environment deployment",
                                "deployment_owner": "John Doe",
                                "accessed": "12 Mar 2024 13:00",
                            },
                        },
                    ]
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
    UNUSED ITEMS TIMEOUT TABLE UPGRADES
    """

    def unused_item_timeout(self, version):
        table = "unused_item_timeout"
        log.info("UPGRADING " + table + " TABLE TO VERSION " + str(version))
        if version == 162:
            try:
                op = "send_unused_deployments_to_recycle_bin"
                exists = (
                    r.table(table)
                    .filter({"name": "default", "op": op})
                    .count()
                    .run(self.conn)
                )
                if not exists:
                    r.table(table).insert(
                        {
                            "name": "default",
                            "op": op,
                            "description": "Keep only the deployments that desktops that have been used in the last selected cutoff time. Send the rest of unused deployments to recycle bin automatically.",
                            "allowed": {
                                "roles": [],  ## Matches all
                                "categories": False,
                                "groups": False,
                                "users": False,
                            },
                            "priority": 0,
                            "cutoff_time": None,
                        }
                    ).run(self.conn)
            except Exception as e:
                print(e)
        if version == 193:
            # Existence-guarded: id-less insert, already present on main-lineage DBs via their v188 —
            # a blind re-run on the cutover path would duplicate them.
            if (
                r.table(table)
                .filter({"op": "send_unused_deployment_desktops_to_recycle_bin"})
                .count()
                .run(self.conn)
                > 0
            ):
                return True
            try:
                op = "send_unused_deployment_desktops_to_recycle_bin"
                exists = (
                    r.table(table)
                    .filter({"name": "default", "op": op})
                    .count()
                    .run(self.conn)
                )
                if not exists:
                    r.table(table).insert(
                        {
                            "name": "default",
                            "op": op,
                            "description": "Trim cold desktops belonging to deployments without removing the parent deployment. Rule is matched against the deployment creator.",
                            "allowed": {
                                "roles": [],  ## Matches all
                                "categories": False,
                                "groups": False,
                                "users": False,
                            },
                            "priority": 0,
                            "cutoff_time": None,
                        }
                    ).run(self.conn)
            except Exception as e:
                print(e)
        return True

    """
    USERS MIGRATIONS EXCEPTIONS TABLE UPGRADES
    """

    def users_migrations_exceptions(self, version):
        table = "users_migrations_exceptions"
        log.info("UPGRADING " + table + " TABLE TO VERSION " + str(version))
        if version == 165:
            try:
                items = list(
                    r.table(table).pluck("id", "item_type", "item_id").run(self.conn)
                )
                missing_items = [
                    item["id"]
                    for item in items
                    if not r.table(item["item_type"])
                    .get(item["item_id"])
                    .run(self.conn)
                ]
                if missing_items:
                    r.table(table).get_all(*missing_items).delete().run(self.conn)
            except Exception as e:
                print(e)
        return True

    """
    NOTIFICATIONS TABLE UPGRADES
    """

    def notifications(self, version):
        table = "notifications"
        log.info("UPGRADING " + table + " TABLE TO VERSION " + str(version))
        if version == 162:
            try:
                r.table(table).insert(
                    [
                        {
                            "name": "User unused deployments have been sent to the recycle bin",
                            "action_id": "unused_deployments",
                            "allowed": {
                                "roles": False,
                                "categories": False,
                                "groups": False,
                                "users": False,
                            },
                            "trigger": "login",
                            "item_type": "deployment",
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
                print(e)

        if version == 171:
            try:
                r.table(table).update({"compute": None}).run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).insert(
                    [
                        {
                            "name": "Starting desktop bastion notification",
                            "action_id": "start_desktop",
                            "allowed": {
                                "roles": [],
                                "categories": False,
                                "groups": False,
                                "users": False,
                            },
                            "trigger": "start_desktop",
                            "item_type": "desktop",
                            "template_id": "",  # Since it's a computed notification the template will be retrieved from the notification_tmpls table by kind
                            "display": ["modal"],
                            "order": 0,
                            "force_accept": False,
                            "enabled": False,
                            "ignore_after": r.epoch_time(
                                0
                            ),  # Defines the time the notification data will be ignored. In this case it will be specified in each notification_data entry
                            "keep_time": 0,  # Defines the amount of hours the notification data will be kept
                            "compute": "start_desktop_bastion",
                        }
                    ]
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 193:
            # Existence-guarded: id-less insert, already present on main-lineage DBs via their v188 —
            # a blind re-run on the cutover path would duplicate them.
            if (
                r.table(table)
                .filter({"action_id": "unused_deployment_desktops_owner"})
                .count()
                .run(self.conn)
                > 0
            ):
                return True
            try:
                r.table(table).insert(
                    [
                        {
                            "name": "Unused deployment desktops have been sent to the recycle bin (deployment owner)",
                            "action_id": "unused_deployment_desktops_owner",
                            "allowed": {
                                "roles": [],
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
                            "ignore_after": r.epoch_time(0),
                            "keep_time": 0,
                            "compute": None,
                        },
                        {
                            "name": "Your deployment desktop has been sent to the recycle bin (desktop owner)",
                            "action_id": "unused_deployment_desktops_user",
                            "allowed": {
                                "roles": [],
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
                            "ignore_after": r.epoch_time(0),
                            "keep_time": 0,
                            "compute": None,
                        },
                    ]
                ).run(self.conn)
            except Exception as e:
                print(e)

        return True

    """
    NOTIFICATIONS ACTION TABLE UPGRADES
    """

    def notifications_action(self, version):
        table = "notifications_action"
        log.info("UPGRADING " + table + " TABLE TO VERSION " + str(version))
        if version == 162:
            try:
                r.table(table).insert(
                    {
                        "description": "Unused deployments are automatically recycled by the system",
                        "id": "unused_deployments",
                        "kwargs": ["id", "user", "co_owners", "name", "accessed"],
                        "compute": None,
                    }
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 171:
            try:
                r.table(table).insert(
                    {
                        "description": "Start desktop",
                        "id": "start_desktop",
                        "compute": "start_desktop_notifications",
                    }
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 193:
            try:
                r.table(table).insert(
                    [
                        {
                            "description": "Unused deployment desktops are automatically recycled by the system. Notification sent to the deployment owner.",
                            "id": "unused_deployment_desktops_owner",
                            "kwargs": [
                                "desktop_name",
                                "desktop_owner",
                                "deployment_name",
                                "accessed",
                            ],
                            "compute": None,
                        },
                        {
                            "description": "Unused deployment desktops are automatically recycled by the system. Notification sent to the desktop owner.",
                            "id": "unused_deployment_desktops_user",
                            "kwargs": [
                                "desktop_name",
                                "deployment_name",
                                "deployment_owner",
                                "accessed",
                            ],
                            "compute": None,
                        },
                    ]
                ).run(self.conn)
            except Exception as e:
                print(e)

        return True

    """
    TARGETS TABLE UPGRADES
    """

    def targets(self, version):
        table = "targets"
        log.info("UPGRADING " + table + " TABLE TO VERSION " + str(version))

        if version == 170:
            try:
                r.table(table).update(
                    {
                        "domain": None,
                    }
                ).run(self.conn)
            except Exception as e:
                print(e)

            try:
                r.table(table).index_create("domain").run(self.conn)
            except Exception as e:
                print(e)

        if version == 178:
            # Migrate single 'domain' field to 'domains' array
            # Check for both None and empty string to avoid creating [""]
            try:
                r.table(table).update(
                    lambda row: {
                        "domains": r.branch(
                            row["domain"].ne(None) & row["domain"].ne(""),
                            [row["domain"]],
                            [],
                        )
                    }
                ).run(self.conn)
            except Exception as e:
                print(e)

            # Create multi-index for array lookup
            try:
                r.table(table).index_create("domains", multi=True).run(self.conn)
                r.table(table).index_wait("domains").run(self.conn)
            except Exception as e:
                print(e)

            # Drop old domain index
            try:
                r.table(table).index_drop("domain").run(self.conn)
            except Exception as e:
                print(e)

            # Remove old domain field
            self.del_keys(table, ["domain"])

        if version == 181:
            # Add proxy_protocol field to http configuration, defaults to False
            try:
                r.table(table).update(
                    lambda row: {"http": row["http"].merge({"proxy_protocol": False})}
                ).run(self.conn)
            except Exception as e:
                print(e)

        if version == 200:
            # Append the old domain if present
            r.table(table).update(
                lambda row: r.branch(
                    row["domain"].default("").ne(""),
                    {
                        "domains": r.branch(
                            row["domains"].default([]).contains(row["domain"]),
                            row["domains"].default([]),
                            row["domains"].default([]).append(row["domain"]),
                        )
                    },
                    {},
                )
            ).run(self.conn)

            # Fix rows with missing `domains` field
            r.table(table).filter(r.row["domains"].default(None).eq(None)).update(
                {"domains": []}
            ).run(self.conn)

            # Remove the old domain field
            self.del_keys(table, ["domain"])

        return True

    def vgpus(self, version):
        """vgpus table + vGPU-id canonicalization migrations.

        v189 does three things idempotently, combined so vgpus is iterated once:

        1. Seed operator-intent fields (``requested_profile``,
           ``operator_passthrough``) on rows that lack them. The reconcile-policy
           redesign reads them; without a seed the first reconcile would reset
           idle cards to the discovery default (and flip passthrough cards to a
           vGPU profile).
        2. Canonicalize dash-form vGPU ids to the underscore form
           (``...-1-2Q`` -> ``...-1_2Q``) across vgpus + the catalog + every
           reference, in lockstep with the release that makes discovery emit the
           canonical form. Without it, post-upgrade ``info.types`` are underscore
           while stored reservables/bookings stay dash and every MIG-backed
           profile change breaks. This migration replaces the former standalone
           ``normalize_vgpu_ids.py`` script (now removed) so the rewrite runs
           automatically, in lockstep with the release.
        3. Prune NON-full-utilization GPU profiles from the bookable catalog
           (``gpu_profiles``/``gpus.profiles_enabled``/``reservables_vgpus``):
           the plain GI-name MIG profiles (``1g.24gb`` & variants -- single GI,
           no usable mdev) AND the partial-framebuffer MIG-backed profiles
           (e.g. ``1_4Q`` on a 24 GB GI strands 20 GB). Only full-utilization
           modes stay: whole-card ``passthrough``, time-sliced ``<fb>Q``, and
           the max-framebuffer MIG-backed profile per tier (``1_24Q``/``2_48Q``/
           ``4_96Q``). Bookings, if any, are kept + logged.
        """
        log.info("UPGRADING vgpus TABLE TO VERSION " + str(version))

        # Gated on v197 here: upstream main ships this same migration as
        # v189 (MR !4496); on this branch v196 is the cross-lineage cutover
        # reconciliation. Idempotent, so a main-lineage DB that already ran
        # it as v189 re-runs it harmlessly. The v189_* helper names are
        # kept for cross-branch diffability.
        if version == 198:
            try:
                v189_backfill_and_canon_vgpus(self)
            except Exception as e:
                log.error(f"vgpus v197 backfill/canon failed: {e}")
            try:
                v189_canonicalize_vgpu_ids(self)
            except Exception as e:
                log.error(f"v197 vGPU-id canonicalization failed: {e}")
            try:
                v189_prune_non_full_use_gpu_profiles(self)
            except Exception as e:
                log.error(f"v197 non-full-use GPU profile prune failed: {e}")

        return True

    def redis_tasks_cleanup(self, version):
        """One-time purge of decommissioned ``core_worker`` RQ state (v199).

        The main -> apiv4-integration migration removed the ``isard-core_worker``
        RQ consumer (the ``core`` and ``core.feedback`` queues). With no live
        worker, RQ's own registry cleanup never runs on them, so their stale
        worker registrations, queues and job registries linger indefinitely
        (failed jobs keep RQ's ~1-year TTL). This idempotently removes that
        orphaned state. The live ``storage``/``notifier`` workers, their queues
        and the changefeed streams (db 2) are left untouched; ongoing old-task
        retention stays governed by the age-based ``Config.old_tasks`` cleanup.

        Deletion is done in bulk: job ids are read from each registry with a
        single range query and their hashes/results are dropped in batched
        ``UNLINK`` calls, instead of one round trip per job. On installs that
        accumulated hundreds of thousands of finished/failed core jobs this
        keeps the upgrade to seconds rather than blocking engine startup for
        minutes.
        """
        log.info("UPGRADING redis_tasks_cleanup TO VERSION " + str(version))

        if version == 199:
            try:
                from rq import Queue

                conn = Redis(
                    host=os.environ.get("REDIS_HOST") or "isard-redis",
                    port=int(os.environ.get("REDIS_PORT") or 6379),
                    password=os.environ.get("REDIS_PASSWORD", ""),
                    db=0,
                )
                dead_queues = ("core.feedback", "core")
                statuses = (
                    "failed",
                    "started",
                    "finished",
                    "deferred",
                    "scheduled",
                    "canceled",
                )
                removed_jobs = 0

                def _drop(keys):
                    # UNLINK reclaims memory in a background thread; fall back to
                    # DEL where UNLINK is unavailable.
                    if not keys:
                        return
                    try:
                        conn.unlink(*keys)
                    except Exception:
                        try:
                            conn.delete(*keys)
                        except Exception:
                            pass

                def _flush(batch, job_id):
                    batch.extend(
                        (
                            f"rq:job:{job_id}",
                            f"rq:results:{job_id}",
                            f"rq:job:{job_id}:dependencies",
                        )
                    )
                    if len(batch) >= 900:
                        _drop(batch)
                        del batch[:]

                for qname in dead_queues:
                    queue = Queue(qname, connection=conn)
                    job_ids = set()
                    registry_keys = []
                    # Pull job ids from every status registry with one range
                    # query each (no per-job round trips).
                    for status in statuses:
                        try:
                            registry = getattr(queue, f"{status}_job_registry")
                            registry_keys.append(registry.key)
                            job_ids.update(registry.get_job_ids())
                        except Exception:
                            pass
                    # Plus any still-queued jobs sitting in the queue list.
                    try:
                        job_ids.update(
                            j.decode() if isinstance(j, bytes) else j
                            for j in conn.lrange(queue.key, 0, -1)
                        )
                    except Exception:
                        pass

                    # Drop the job hashes (and their results/dependencies) in
                    # batched UNLINKs.
                    batch = []
                    for job_id in job_ids:
                        _flush(batch, job_id)
                    _drop(batch)
                    removed_jobs += len(job_ids)

                    # Drop the registries, the queue list and the queue's worker
                    # set, then unregister it from rq:queues.
                    _drop(registry_keys + [queue.key, f"rq:workers:{qname}"])
                    try:
                        conn.srem("rq:queues", f"rq:queue:{qname}")
                    except Exception:
                        pass

                # Safety net: sweep any orphaned job hashes still tagged with a
                # dead origin (registry entry lost), again in batched deletes.
                dead_origins = {b"core", b"core.feedback"}
                orphan_batch = []
                try:
                    for key in conn.scan_iter(match="rq:job:*", count=1000):
                        try:
                            if conn.hget(key, "origin") in dead_origins:
                                job_id = key.decode().split("rq:job:", 1)[1]
                                _flush(orphan_batch, job_id)
                                removed_jobs += 1
                        except Exception:
                            pass
                    _drop(orphan_batch)
                except Exception:
                    pass

                # Prune stale (heartbeat-expired) worker registrations.
                removed_workers = 0
                try:
                    for member in conn.smembers("rq:workers"):
                        if not conn.exists(member):
                            conn.srem("rq:workers", member)
                            removed_workers += 1
                except Exception:
                    pass

                log.info(
                    "redis_tasks_cleanup v199: removed "
                    f"{removed_jobs} core job(s) and "
                    f"{removed_workers} stale worker registration(s)"
                )
            except Exception as e:
                log.error(f"redis_tasks_cleanup v199 failed (non-fatal): {e}")

        return True
