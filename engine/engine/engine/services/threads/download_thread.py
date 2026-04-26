# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import os
import pprint
import re
import shlex
import signal
import subprocess
import threading
import uuid
from os.path import dirname
from shlex import quote
from time import sleep

import humanfriendly as hf
from changefeed_subscribers import TABLE_TO_SUBSCRIBER
from engine.config import CONFIG_DICT
from engine.services.db import (
    delete_domain,
    get_config_branch,
    get_domain,
    get_hyp_hostname_user_port_from_id,
    update_domain_dict_create_dict,
    update_table_field,
)
from engine.services.db.db import (
    get_media_with_status,
    new_rethink_connection,
    remove_media,
    update_table_dict,
)
from engine.services.db.domains import get_domains_with_status, update_domain_status
from engine.services.db.downloads import (
    get_media,
    update_download_percent,
    update_status_table,
)
from engine.services.db.storage_pool import get_category_storage_pool_id
from engine.services.lib.download import test_url_for_download, test_url_google_drive
from engine.services.lib.functions import get_tid
from engine.services.lib.qcow import (
    create_cmds_delete_disk,
    get_host_disk_operations_from_path,
    get_path_to_disk,
)
from engine.services.lib.storage import create_storage, update_storage_status
from engine.services.log import logs
from isardvdi_common.helpers.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.redis_stream import RedisStreamConsumer
from rethinkdb import r

URL_DOWNLOAD_INSECURE_SSL = True
TIMEOUT_WAITING_HYPERVISOR_TO_DOWNLOAD = 10
FILETYPES_MEDIA_OK = ["application/x-iso9660-image"]


class DownloadThread(threading.Thread, object):
    def __init__(
        self,
        url,
        path,
        path_selected,
        table,
        id_down,
        dict_header,
        finalished_threads,
        threads_disk_operations,
        pool_id,
        type_path_selected,
        storage_id=None,
        manager=None,
    ):
        threading.Thread.__init__(self)
        self.name = "_".join([table, id_down])
        self.table = table
        self.path = path
        self.path_selected = path_selected
        self.id = id_down
        self.url = url
        self.dict_header = dict_header
        self.stop = False
        self.finalished_threads = finalished_threads
        self.storage_id = storage_id

        self.threads_disk_operations = threads_disk_operations
        self.hostname = None
        self.user = None
        self.port = None
        self.pool_id = pool_id
        self.type_path_selected = type_path_selected
        self.manager = manager

    def run(self):
        # if self.table == 'domains':
        #     type_path_selected = 'groups'
        # elif self.table in ['isos']:
        #     type_path_selected = 'isos'
        # else:
        #     type_path_selected = 'media'
        #
        # new_file, path_selected = get_path_to_disk(self.path, pool=self.pool, type_path=type_path_selected)
        # logs.downloads.debug("PATHS ___________________________________________________________________")
        # logs.downloads.debug(new_file)
        # logs.downloads.debug(path_selected)
        # logs.downloads.debug(pprint.pformat(self.__dict__))
        #
        # hyp_to_disk_create = get_host_disk_operations_from_path(path_selected, pool=self.pool,
        #                                                                 type_path=type_path_selected)

        # hypervisor to launch download command
        # wait to threads disk_operations are alive
        time_elapsed = 0
        path_selected = self.path_selected
        while True:
            if len(self.threads_disk_operations) > 0:
                hyp_to_disk_create = get_host_disk_operations_from_path(
                    self.manager, pool=self.pool_id, type_path=self.type_path_selected
                )
                logs.downloads.debug(
                    f"Thread download started to in hypervisor: {hyp_to_disk_create}"
                )
                if (
                    self.threads_disk_operations.get(hyp_to_disk_create, False)
                    is not False
                ):
                    if self.threads_disk_operations[hyp_to_disk_create].is_alive():
                        d = get_hyp_hostname_user_port_from_id(hyp_to_disk_create)
                        self.hostname = d["hostname"]
                        self.user = d["user"]
                        self.port = d["port"]
                        break
            sleep(0.2)
            time_elapsed += 0.2
            if time_elapsed > TIMEOUT_WAITING_HYPERVISOR_TO_DOWNLOAD:
                logs.downloads.info(
                    f"Timeout ({TIMEOUT_WAITING_HYPERVISOR_TO_DOWNLOAD} sec) waiting hypervisor online to download. Maybe there is no disk_operations selected in Hypervisors???"
                )
                if self.table == "domains":
                    update_domain_status(
                        "DownloadFailed",
                        self.id,
                        detail="No hypervisor could do the disk_operations.",
                    )
                else:
                    update_status_table(self.table, "DownloadFailed", self.id)
                self.finalished_threads.append(self.path)
                return False

        header_template = "--header '{header_key}: {header_value}' "
        headers = ""

        if URL_DOWNLOAD_INSECURE_SSL == True:
            insecure_option = "--insecure"
        else:
            insecure_option = ""

        dict_header = {}
        for k, v in self.dict_header.items():
            headers += header_template.format(header_key=k, header_value=v)
            dict_header[k] = v

        if self.url.find("drive.google.com") > 0:
            url_download = re.sub(
                r"https://drive\.google\.com/file/d/(.*?)/.*?\?usp=sharing",
                r"https://drive.google.com/uc?export=download&id=\1",
                self.url,
            )
            try:
                file_google_drive_id = re.search(
                    "https://drive\.google\.com/file/d/(.*?)/.*?\?usp=sharing", self.url
                ).group(1)
            except AttributeError:
                logs.downloads.error(
                    "file google drive id not fount by regex for url: " + self.url
                )
                file_google_drive_id = "drive_id_not_found"

            ok, error_msg = test_url_google_drive(url_download)
            if ok is not False:
                confirm = ok

                cookie_file = "./cookie_download_" + str(uuid.uuid4())
                google_drive_url_to_file = quote(
                    "https://drive.google.com/uc"
                    f"?export=download&{confirm}"
                    f"&id={file_google_drive_id}"
                )
                curl_cmd = f"curl -Lb {cookie_file} {google_drive_url_to_file} -o {shlex.quote(self.path)}"
                cmds_google = (
                    f"curl -c {cookie_file} -s -L {quote(url_download)};"
                    f"{curl_cmd};"
                    f"""rm -f {cookie_file}"""
                )
                path_dir = dirname(self.path)

                ssh_command = [
                    "ssh",
                    "-oBatchMode=yes",
                    "-p",
                    self.port,
                    f"{self.user}@{self.hostname}",
                    "/bin/bash",
                    "-c",
                    f"mkdir -p {shlex.quote(path_dir)}; {cmds_google}",
                ]
            else:
                logs.downloads.error(
                    f"URL check failed for url from google drive: {self.url}"
                )
                logs.downloads.error(f"Failed url check reason: {error_msg}")
                print(self.id)
                print(self.table)
                update_status_table(
                    self.table, "DownloadFailed", self.id, detail=error_msg
                )
                return False

        else:
            # TEST IF url return an stream of data
            ok, error_msg = test_url_for_download(
                self.url,
                url_download_insecure_ssl=URL_DOWNLOAD_INSECURE_SSL,
                timeout_time_limit=TIMEOUT_WAITING_HYPERVISOR_TO_DOWNLOAD,
                dict_header=dict_header,
            )

            if ok is False:
                logs.downloads.error(f"URL check failed for url: {self.url}")
                logs.downloads.error(f"Failed url check reason: {error_msg}")
                print(self.id)
                print(self.table)
                update_status_table(
                    self.table, "DownloadFailed", self.id, detail=error_msg
                )
                return False

            curl_cmd = (
                f"curl {insecure_option} -L --max-redirs 5 "
                f"--connect-timeout 30 --no-netrc "
                f"-o {shlex.quote(self.path)} {headers} {shlex.quote(self.url)}"
            )
            ssh_command = [
                "ssh",
                "-oBatchMode=yes",
                "-p",
                self.port,
                f"{self.user}@{self.hostname}",
                f"mkdir -p {shlex.quote(dirname(self.path))}; {curl_cmd}",
            ]

        logs.downloads.debug("SSH COMMAND: {}".format(ssh_command))

        p = subprocess.Popen(
            ssh_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
        )
        rc = p.poll()
        update_status_table(
            self.table,
            "Downloading",
            self.id,
            "downloading in hypervisor: {}".format(self.hostname),
        )
        update_storage_status(self.storage_id, "downloading")
        if rc is None:
            header = p.stderr.readline().decode("utf8")
            header2 = p.stderr.readline().decode("utf8")
            keys = [
                "total_percent",
                "total",
                "received_percent",
                "received",
                "xferd_percent",
                "xferd",
                "speed_download_average",
                "speed_upload_average",
                "time_total",
                "time_spent",
                "time_left",
                "speed_current",
            ]

            line = ""

            while rc is None:
                c = p.stderr.read(1).decode("utf8")
                if self.stop is True:
                    # for pkill curl order is cleaned
                    curl_cmd = curl_cmd.replace("'", "")
                    curl_cmd = curl_cmd.replace("  ", " ")

                    ssh_cmd_kill_curl = [
                        "ssh",
                        "-p",
                        self.port,
                        f"{self.user}@{self.hostname}",
                        f'pkill -f "^{re.escape(curl_cmd)}"',
                    ]

                    logs.downloads.info(
                        "download {} aborted, ready to send ssh kill to curl in hypervisor {}".format(
                            self.path, self.hostname
                        )
                    )

                    # destroy curl in hypervisor
                    p_kill_curl = subprocess.Popen(ssh_cmd_kill_curl)
                    p_kill_curl.wait(timeout=5)
                    # destroy ssh command
                    try:
                        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
                    except Exception as e:
                        logs.exception_id.debug("0055")
                        logs.downloads.debug("ssh process not killed, has finalished")

                    if self.table == "media":
                        remove_media(self.id)
                    if self.table == "domains":
                        delete_domain(self.id)
                    # update_status_table(self.table, 'DownloadFailed', self.id, detail="download aborted")
                    return False
                if not c:
                    rc = p.poll()
                    break
                if c == "\r":
                    if len(line) > 60:
                        values = line.split()
                        logs.downloads.debug(self.url)
                        logs.downloads.debug(line)
                        d_progress = dict(zip(keys, values))
                        try:
                            d_progress["total_percent"] = int(
                                float(d_progress["total_percent"])
                            )
                            d_progress["received_percent"] = int(
                                float(d_progress["received_percent"])
                            )
                            if d_progress["received_percent"] > 1:
                                pass
                        except:
                            d_progress["total_percent"] = 0
                            d_progress["received_percent"] = 0
                        update_download_percent(d_progress, self.table, self.id)
                        line = p.stderr.read(60).decode("utf8")

                else:
                    line = line + c

                rc = p.poll()

        if self.stop is True:
            return False
        elif rc != 0:
            error_msg = f"Download failed with status code {rc}"
            logs.downloads.info(f"{error_msg}: {self.id}, {self.url}")
            update_status_table(self.table, "DownloadFailed", self.id, detail=error_msg)
        else:
            logs.downloads.info("File downloaded: {}".format(self.path))
            if self.table == "domains":
                update_domain_status("Downloaded", self.id, detail="downloaded disk")
                update_storage_status(self.storage_id, "ready")
                update_domain_status("Stopped", self.id, detail="downloaded disk")
            else:
                # test if downloaded is an iso
                ssh_command = [
                    "ssh",
                    "-p",
                    self.port,
                    f"{self.user}@{self.hostname}",
                    f"file -b --mime-type {shlex.quote(self.path)}",
                ]

                logs.downloads.debug("SSH COMMAND: {}".format(ssh_command))

                p = subprocess.Popen(
                    ssh_command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    preexec_fn=os.setsid,
                )
                p.poll()
                s_error = p.stderr.readline().decode("utf8")
                s_out = p.stdout.readline().decode("utf8")
                logs.downloads.info(f"Filetype of path {self.path}: {s_out}")

                if len(s_error) > 0 or s_out.strip() not in FILETYPES_MEDIA_OK:
                    if len(s_error) > 0:
                        logs.downloads.error(
                            f"error in filetype verification: {s_error}"
                        )
                    logs.downloads.error(
                        f"Filetype of path {self.path} verification failed: {s_out}"
                    )
                    update_table_dict(
                        self.table,
                        self.id,
                        {
                            "path_downloaded": self.path,
                            "status": "DownloadFailedInvalidFormat",
                        },
                    )
                else:
                    update_to_status = "Downloaded"

                    update_table_dict(
                        self.table,
                        self.id,
                        {
                            "path_downloaded": self.path,
                            "status": update_to_status,
                            "progress": {
                                "received": d_progress["total"],
                                "total_percent": 100,
                                "total_bytes": hf.parse_size(
                                    d_progress["total"] + "iB"
                                ),
                            },
                        },
                    )

        self.finalished_threads.append(self.path)


class DownloadChangesThread(threading.Thread):
    def __init__(
        self,
        manager,
        q_workers,
        threads_disk_operations,
        name="download_changes",
    ):
        threading.Thread.__init__(self)
        self.name = name
        self.stop = False
        self.r_conn = False
        self.manager = manager
        self.q_workers = q_workers
        self.threads_disk_operations = threads_disk_operations

        self.storage_pending = {}

        cfg = get_config_branch("resources")
        if cfg is not False:
            self.url_resources = cfg["url"]
            if "code" in cfg:
                self.url_code = cfg["code"]
            else:
                self.url_code = ""
        else:
            logs.downloads.error(
                "resources dict not in config, stopping thread download changes"
            )
            self.stop = True

        self.download_threads = {}
        self.finalished_threads = []

    def get_url_resources_and_code(self):
        cfg = get_config_branch("resources")
        if cfg is not False:
            if "code" in cfg:
                self.url_resources = cfg["url"]
                self.url_code = cfg["code"]
            else:
                return False
        else:
            return False

    def get_file_path(self, dict_changes):
        table = dict_changes.table
        if table == "domains":
            type_path_selected = "desktop"
            disk = (
                (dict_changes.create_dict or {})
                .get("hardware", {})
                .get("disks", [{}])[0]
            )
            relative_path = None
            extension = disk.get(
                "extension", disk.get("file", "qcow2").rsplit(".", 1)[-1]
            )
        else:
            type_path_selected = "media"
            relative_path = dict_changes.id
            extension = dict_changes.kind

        pool_id = get_category_storage_pool_id(dict_changes.category)
        if pool_id is None:
            logs.downloads.error(
                f"DOWNLOAD_CHANGES_THREAD: pool_id not available for category {dict_changes.category}"
            )
            return
        new_file_path, path_selected = get_path_to_disk(
            relative_path=relative_path,
            category_id=dict_changes.category,
            type_path=type_path_selected,
            extension=extension,
        )
        return new_file_path, path_selected, type_path_selected, pool_id

    def killall_curl(self, hyp_id):
        action = {"type": "killall_curl"}
        self.q_workers[hyp_id].put(action)

    def abort_download(self, dict_changes, final_status="Deleted"):
        logs.downloads.debug("aborting download function")
        new_file_path, path_selected, type_path_selected, pool_id = self.get_file_path(
            dict_changes
        )
        if new_file_path in self.download_threads.keys():
            self.download_threads[new_file_path].stop = True
        else:
            update_status_table(dict_changes.table, "DownloadFailed", dict_changes.id)
        # and delete partial download
        cmds = create_cmds_delete_disk(new_file_path)

        # change for other pools when pools are implemented in all media
        try:
            next_hyp = self.manager.diskoperations_pools[
                pool_id
            ].balancer.get_next_diskoperations()
            logs.downloads.debug(
                "hypervisor where delete media {}: {}".format(new_file_path, next_hyp)
            )

            action = dict()
            action["id_media"] = dict_changes.id
            action["path"] = new_file_path
            action["type"] = "delete_media"
            action["final_status"] = final_status
            action["ssh_commands"] = cmds

            self.q_workers[next_hyp].put(action)
            return True
        except Exception as e:
            logs.exception_id.debug("0056")
            logs.downloads.error("next hypervisor fail: " + str(e))

    def delete_media(self, dict_changes):
        table = dict_changes.table
        id_down = dict_changes.id
        d_media = get_media(id_down)
        cmds = create_cmds_delete_disk(d_media["path_downloaded"])

        # change for other pools when pools are implemented in all media
        pool_id = get_category_storage_pool_id(dict_changes.category)
        if pool_id is None:
            logs.downloads.error(
                f"DOWNLOAD_CHANGES_THREAD: pool_id not available for category {dict_changes.category}"
            )
            return
        next_hyp = self.manager.diskoperations_pools[
            pool_id
        ].balancer.get_next_diskoperations()
        logs.downloads.debug(
            "hypervisor where delete media {}: {}".format(
                d_media["path_downloaded"], next_hyp
            )
        )

        action = dict()
        action["id_media"] = id_down
        action["path"] = d_media["path_downloaded"]
        action["type"] = "delete_media"
        action["ssh_commands"] = cmds

        self.q_workers[next_hyp].put(action)

        ## call disk_operations thread_to_delete

    def remove_download_thread(self, dict_changes):
        new_file_path, path_selected, type_path_selected, pool_id = self.get_file_path(
            dict_changes
        )
        if new_file_path in self.download_threads.keys():
            self.download_threads.pop(new_file_path)

    def start_download(self, dict_changes):
        new_file_path, path_selected, type_path_selected, pool_id = self.get_file_path(
            dict_changes
        )

        table = dict_changes.table
        id_down = dict_changes.id
        header_dict = {}

        # url_web / url_isard are declared on MediaRow, but DomainsRow
        # keeps them in additional_properties. Check both.
        props = dict_changes.additional_properties or {}
        url_web = getattr(dict_changes, "url_web", None) or props.get("url-web")
        url_isard = getattr(dict_changes, "url_isard", None) or props.get("url-isard")

        if url_web:
            url = url_web
        elif url_isard:
            if self.url_code is False:
                if self.get_url_resources_and_code() is False:
                    logs.downloads.error(
                        "not url_code, isard installation not registered"
                        " to IsardVDI Downloads Service"
                    )
                    return False
            url_base = self.url_resources + "/storage"
            url = url_base + "/" + table + "/" + url_isard
            if len(self.url_code) > 0:
                header_dict["Authorization"] = self.url_code
        else:
            logs.downloads.error(
                "web-url or isard-url must be keys in dictionary for %s"
                " to download disk file from internet. Skipping.",
                id_down,
            )
            return False

        if new_file_path in self.finalished_threads:
            if new_file_path in self.download_threads.keys():
                self.download_threads.pop(new_file_path)
            self.finalished_threads.remove(new_file_path)

        storage_id = None
        if table == "domains":
            d_update_domain = dict_changes.create_dict
            if not d_update_domain or "hardware" not in d_update_domain:
                logs.downloads.error(
                    f"Domain {id_down} has no create_dict.hardware, cannot proceed with download"
                )
                update_domain_status(
                    "DownloadFailed", id_down, detail="Missing create_dict.hardware"
                )
                return
            d_update_domain["hardware"]["disks"][0]["path_selected"] = path_selected
            d_update_domain["hardware"]["disks"][0]["file"] = new_file_path
            storage_id = create_storage(
                d_update_domain["hardware"]["disks"][0],
                get_domain(dict_changes.id).get("user"),
                force_parent=None,
            )
            d_update_domain["hardware"]["disks"][0] = {"storage_id": storage_id}
            update_domain_dict_create_dict(id_down, d_update_domain)

        if new_file_path in self.download_threads:
            old_thread = self.download_threads.pop(new_file_path)
            del old_thread

        if new_file_path not in self.download_threads:
            # launching download threads
            logs.downloads.debug(
                f"Starting DownloadThread for --> url:{url} , path:{new_file_path}"
            )
            self.download_threads[new_file_path] = DownloadThread(
                url,
                new_file_path,
                path_selected,
                table,
                id_down,
                header_dict,
                self.finalished_threads,
                self.threads_disk_operations,
                pool_id,
                type_path_selected,
                storage_id,
                self.manager,
            )
            self.download_threads[new_file_path].daemon = True
            self.download_threads[new_file_path].start()

        else:
            logs.downloads.error(
                "download thread launched previously to this path: {}".format(
                    new_file_path
                )
            )

    def execute(self, action, dict_changes, extra=None):
        pool_id = get_category_storage_pool_id(dict_changes.category)
        if pool_id is None:
            logs.downloads.error(
                f"DOWNLOAD_CHANGES_THREAD: pool_id not available for category {dict_changes.category}"
            )
            return
        next_diskop = self.manager.diskoperations_pools[
            pool_id
        ].balancer.get_next_diskoperations()
        if next_diskop is False:
            if pool_id not in self.storage_pending.keys():
                self.storage_pending[pool_id] = []
            self.storage_pending[pool_id].append(
                {"action": action, "item": dict_changes}
            )
            logs.downloads.error(
                f"DOWNLOAD: No disk operations active for pool {pool_id} to execute action {action} with id {dict_changes.id}, storing in pending list. Actual list has {len(self.storage_pending[pool_id])} items"
            )
        else:
            if action == "start_download":
                self.start_download(dict_changes)
            elif action == "abort_download":
                self.abort_download(dict_changes)
            elif action == "abort_download_final_status_download_failed":
                self.abort_download(dict_changes, final_status="DownloadFailed")
            elif action == "delete_media":
                self.delete_media(dict_changes)
            elif action == "remove_download_thread":
                self.remove_download_thread(dict_changes)
            else:
                logs.downloads.error(
                    f"DOWNLOAD: action {action} not implemented for id {dict_changes.id}"
                )
            pending = self.storage_pending.get(pool_id, [])
            entry = {"action": action, "item": dict_changes}
            try:
                pending.remove(entry)
            except ValueError:
                logs.downloads.warning(
                    f"DOWNLOAD: no pending entry to remove for action "
                    f"{action} id {dict_changes.id} in pool {pool_id}"
                )

    def restart_pending_downloads(self):
        for pool_id in self.storage_pending.keys():
            next_hyp = self.manager.diskoperations_pools[
                pool_id
            ].balancer.get_next_diskoperations()
            if next_hyp is not False:
                logs.downloads.debug(
                    f"DOWNLOAD: Restarting pending {len(self.storage_pending[pool_id])} downloads for pool {pool_id}."
                )
                for item in self.storage_pending[pool_id]:
                    self.execute(item["action"], item["item"])
            else:
                logs.downloads.debug(
                    f"DOWNLOAD: Unable to restart pending {len(self.storage_pending[pool_id])} downloads for pool {pool_id}. No disk operations available"
                )

    # Statuses that the old RethinkDB changefeed watched with include_initial=True
    DOWNLOAD_STATUSES = [
        "Downloaded",
        "DownloadFailed",
        "DownloadStarting",
        "Downloading",
        "Download",
        "DownloadAborting",
        "ResetDownloading",
    ]

    def _recover_initial_state(self):
        """Query DB for items in active download states — replaces include_initial=True."""
        r_conn = new_rethink_connection()
        try:
            for table, pluck_fields in [
                ("media", ["id", "kind", "url-isard", "url-web", "status", "category"]),
                (
                    "domains",
                    ["id", "create_dict", "url-isard", "url-web", "status", "category"],
                ),
            ]:
                items = list(
                    r.table(table)
                    .get_all(r.args(self.DOWNLOAD_STATUSES), index="status")
                    .pluck(*pluck_fields)
                    .run(r_conn)
                )
                for item in items:
                    item["table"] = table
                    logs.downloads.debug(
                        f"DOWNLOAD RECOVERY ({table}): {item['id']} status={item['status']}"
                    )
                    subscriber = TABLE_TO_SUBSCRIBER.get(table)
                    if subscriber is None:
                        continue
                    envelope = subscriber.parse_dict(
                        {
                            "table": table,
                            "change": {"old_val": None, "new_val": item},
                        }
                    )
                    self._process_change(envelope.change)
        finally:
            from engine.services.db.db import close_rethink_connection

            close_rethink_connection(r_conn)

    def run(self):
        self.tid = get_tid()
        logs.downloads.debug("RUN-DOWNLOAD-THREAD-------------------------------------")
        self.downloads_with_storage_pending = {}
        if self.stop is False:
            # Recover items with active download states (replaces include_initial=True)
            self._recover_initial_state()

            stop_event = threading.Event()
            self._stop_event = stop_event
            consumer = RedisStreamConsumer(
                streams=["stream:media", "stream:domains", "stream:engine"],
                group="engine-downloads",
            )

            def handler(data):
                table = data.get("table")
                subscriber = TABLE_TO_SUBSCRIBER.get(table)
                if subscriber is None:
                    return
                envelope = subscriber.parse_dict(data)
                self._process_change(envelope.change)

            consumer.run(handler, stop_event=stop_event)
            logs.downloads.debug("finished thread download changes")

    def _process_change(self, change):
        """Process a single media/domains/engine change."""
        if self.stop:
            if hasattr(self, "_stop_event"):
                self._stop_event.set()
            return

        new_val = change.new_val
        old_val = change.old_val

        if new_val is not None and new_val.table == "engine":
            engine_props = new_val.additional_properties or {}
            if engine_props.get("status_all_threads") == "Stopping":
                if hasattr(self, "_stop_event"):
                    self._stop_event.set()
                return
            self.restart_pending_downloads()
            return
        if old_val is not None and old_val.table == "engine":
            return

        # Filter: only process download-related statuses
        new_status = new_val.status if new_val is not None else None
        old_status = old_val.status if old_val is not None else None
        if (
            new_status not in self.DOWNLOAD_STATUSES
            and old_status not in self.DOWNLOAD_STATUSES
        ):
            return

        logs.downloads.debug("DOWNLOAD CHANGES DETECTED:")
        logs.downloads.debug(pprint.pformat(change))
        self.restart_pending_downloads()

        if new_val is not None and old_val is None:
            if new_val.status == "DownloadStarting":
                self.execute("start_download", new_val)
            if new_val.status == "Downloading":
                if new_val.table == "media":
                    self.reset_downloading("media", new_val)
                elif new_val.table == "domains":
                    self.reset_downloading("domains", new_val)

        if old_val is not None and new_val is None:
            if old_val.status in ["DownloadAborting"]:
                self.execute("remove_download_thread", old_val)

        if old_val is not None and new_val is not None:
            if (
                old_val.status == "DownloadFailed"
                and new_val.status == "DownloadStarting"
            ):
                self.execute("start_download", new_val)

            elif old_val.status == "Downloaded" and new_val.status == "Deleting":
                if new_val.table == "media":
                    self.execute("delete_media", new_val)

            elif old_val.status == "DownloadFailed" and new_val.status == "Deleting":
                if new_val.table == "media":
                    self.execute("delete_media", new_val)

            elif old_val.status == "Downloading" and new_val.status == "DownloadFailed":
                pass

            elif (
                old_val.status == "DownloadStarting" and new_val.status == "Downloading"
            ):
                pass

            elif old_val.status == "Downloading" and new_val.status == "Downloaded":
                pass

            elif (
                old_val.status == "Downloading" and new_val.status == "DownloadAborting"
            ):
                self.execute("abort_download", new_val)

            elif (
                old_val.status == "Downloading" and new_val.status == "ResetDownloading"
            ):
                self.execute(
                    "abort_download_final_status_download_failed",
                    new_val,
                )

    def reset_downloading(self, kind, dict_changes):
        if kind == "domains":
            update_domain_status("ResetDownloading", dict_changes.id)
            self.abort_download(dict_changes, final_status="DownloadFailed")
        elif kind == "media":
            update_status_table("media", "ResetDownloading", dict_changes.id)
            self.abort_download(dict_changes, final_status="DownloadFailed")

            # update_table_field(
            #     "hypervisors_pools", pool_id, "download_changes", "Started"
            # )


def launch_thread_download_changes(manager, q_workers, threads_disk_operations):
    # q_workers should be q_disk_operations?
    t = DownloadChangesThread(manager, q_workers, threads_disk_operations)
    t.daemon = True
    t.start()
    return t
