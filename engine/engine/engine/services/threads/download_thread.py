# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import os
import pprint
import re
import signal
import subprocess
import threading
import uuid
from os.path import dirname
from time import sleep

import humanfriendly as hf
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
from engine.services.lib.download import test_url_for_download, test_url_google_drive
from engine.services.lib.functions import get_tid
from engine.services.lib.qcow import (
    create_cmds_delete_disk,
    get_host_disk_operations_from_path,
    get_path_to_disk,
)
from engine.services.lib.storage import create_storage, update_storage_status
from engine.services.log import logs
from isardvdi_common.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from rethinkdb import r

URL_DOWNLOAD_INSECURE_SSL = True
TIMEOUT_WAITING_HYPERVISOR_TO_DOWNLOAD = 10


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
                curl_cmd = f"curl -Lb {cookie_file} 'https://drive.google.com/uc?export=download&{confirm}&id={file_google_drive_id}' -o {self.path}"
                cmds_google = (
                    f"""curl -c {cookie_file} -s -L '{url_download}' ; """
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
                    f"mkdir -p '{path_dir}'; {cmds_google}",
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
                f"curl {insecure_option} -L -o '{self.path}' {headers} '{self.url}'"
            )
            ssh_command = [
                "ssh",
                "-oBatchMode=yes",
                "-p",
                self.port,
                f"{self.user}@{self.hostname}",
                f"mkdir -p '{dirname(self.path)}'; {curl_cmd}",
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
                update_domain_status("Updating", self.id, detail="downloaded disk")
            else:
                update_table_field(self.table, self.id, "path_downloaded", self.path)
                update_table_dict(
                    self.table,
                    self.id,
                    {
                        "status": "Downloaded",
                        "progress": {
                            "received": d_progress["total"],
                            "total_percent": 100,
                            "total_bytes": hf.parse_size(d_progress["total"] + "iB"),
                        },
                    },
                )
        self.finalished_threads.append(self.path)


class DownloadChangesThread(threading.Thread):
    def __init__(
        self,
        manager,
        pool_id,
        q_workers,
        threads_disk_operations,
        name="download_changes",
    ):
        threading.Thread.__init__(self)
        self.name = name
        self.stop = False
        self.r_conn = False
        self.manager = manager
        self.pool_id = pool_id
        self.q_workers = q_workers
        self.threads_disk_operations = threads_disk_operations

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
        table = dict_changes["table"]
        if table == "domains":
            type_path_selected = "desktop"
            disk = dict_changes["create_dict"]["hardware"]["disks"][0]
            relative_path = None
            extension = disk.get(
                "extension", disk.get("file", "qcow2").rsplit(".", 1)[-1]
            )

        else:
            type_path_selected = "media"
            relative_path = dict_changes["id"]
            extension = dict_changes["kind"]
        pool_id = dict_changes.get("create_dict", {}).get(
            "storage_pool", DEFAULT_STORAGE_POOL_ID
        )

        new_file_path, path_selected = get_path_to_disk(
            relative_path=relative_path,
            pool=pool_id,
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
            update_status_table(
                dict_changes["table"], "DownloadFailed", dict_changes["id"]
            )
        # and delete partial download
        cmds = create_cmds_delete_disk(new_file_path)

        # change for other pools when pools are implemented in all media
        try:
            next_hyp = self.manager.diskoperations_pools[
                self.pool_id
            ].balancer.get_next_diskoperations()
            logs.downloads.debug(
                "hypervisor where delete media {}: {}".format(new_file_path, next_hyp)
            )

            action = dict()
            action["id_media"] = dict_changes["id"]
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
        table = dict_changes["table"]
        id_down = dict_changes["id"]
        d_media = get_media(id_down)
        cmds = create_cmds_delete_disk(d_media["path_downloaded"])

        # change for other pools when pools are implemented in all media
        next_hyp = self.manager.diskoperations_pools[
            self.pool_id
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

        table = dict_changes["table"]
        id_down = dict_changes["id"]
        header_dict = {}

        # all disk downloads create a desktop

        if dict_changes.get("url-web", False) is not False:
            url = dict_changes["url-web"]

        elif dict_changes.get("url-isard", False) is not False:
            if self.url_code is False:
                if self.get_url_resources_and_code() is False:
                    logs.downloads.error(
                        f"not url_code, isard installation not registered"
                        f" to IsardVDI Downloads Service"
                    )
                    return False
            url_base = self.url_resources

            subdir_url = "storage"
            if len(subdir_url) > 0:
                url_base = url_base + "/" + subdir_url

            url_isard = dict_changes["url-isard"]
            url = url_base + "/" + table + "/" + url_isard
            if len(self.url_code) > 0:
                header_dict["Authorization"] = self.url_code
        else:
            logs.downloads.error(
                (
                    "web-url or isard-url must be keys in dictionary for domain {}"
                    + " to download disk file from internet. "
                ).format(id_down)
            )
            exit()

        if new_file_path in self.finalished_threads:
            if new_file_path in self.download_threads.keys():
                self.download_threads.pop(new_file_path)
            self.finalished_threads.remove(new_file_path)

        storage_id = None
        if table == "domains":
            d_update_domain = dict_changes["create_dict"]
            d_update_domain["hardware"]["disks"][0]["path_selected"] = path_selected
            d_update_domain["hardware"]["disks"][0]["file"] = new_file_path
            storage_id = create_storage(
                d_update_domain["hardware"]["disks"][0],
                get_domain(dict_changes.get("id")).get("user"),
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
                f"ready tu start DownloadThread --> url:{url} , path:{new_file_path}"
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

    def run(self):
        self.tid = get_tid()
        logs.downloads.debug("RUN-DOWNLOAD-THREAD-------------------------------------")
        pool_id = "default"
        first_loop = True
        if self.stop is False:
            if first_loop is True:
                # if domains or media have status Downloading when engine restart
                # we need to resetdownloading deleting file and
                first_loop = False
                # wait a hyp to downloads
                next_hyp = False
                while next_hyp is False:
                    # logs.downloads.info('waiting an hypervisor online to launch downloading actions')
                    next_hyp = self.manager.diskoperations_pools[
                        self.pool_id
                    ].balancer.get_next_diskoperations()
                    if next_hyp:
                        break
                    sleep(1)
                logs.downloads.info(f"hypervisor to launch download: {next_hyp}")

                domains_status_downloading = get_domains_with_status("Downloading")
                medias_status_downloading = get_media_with_status("Downloading")

                for id_domain in domains_status_downloading:
                    create_dict = get_domain(id_domain)["create_dict"]
                    dict_changes = {
                        "id": id_domain,
                        "table": "domains",
                        "create_dict": create_dict,
                    }
                    update_domain_status("ResetDownloading", id_domain)
                    self.abort_download(dict_changes, final_status="DownloadFailed")

                for id_media in medias_status_downloading:
                    dict_media = get_media(id_media)
                    dict_changes = {
                        "id": id_media,
                        "table": "media",
                        "path": dict_media["path"],
                        "hypervisors_pools": dict_media["hypervisors_pools"],
                    }
                    update_status_table("media", "ResetDownloading", id_media)
                    self.abort_download(dict_changes, final_status="DownloadFailed")

            self.r_conn = new_rethink_connection()
            update_table_field(
                "hypervisors_pools", pool_id, "download_changes", "Started"
            )
            for c in (
                r.table("media")
                .get_all(
                    r.args(
                        [
                            "Deleting",
                            "Deleted",
                            "Downloaded",
                            "DownloadFailed",
                            "DownloadStarting",
                            "Downloading",
                            "Download",
                            "DownloadAborting",
                            "ResetDownloading",
                        ]
                    ),
                    index="status",
                )
                .pluck("id", "kind", "url-isard", "url-web", "status")
                .merge({"table": "media"})
                .changes(include_initial=True)
                .union(
                    r.table("domains")
                    .get_all(
                        r.args(
                            [
                                "Downloaded",
                                "DownloadFailed",
                                "DownloadStarting",
                                "Downloading",
                                "DownloadAborting",
                                "ResetDownloading",
                            ]
                        ),
                        index="status",
                    )
                    .pluck("id", "create_dict", "url-isard", "url-web", "status")
                    .merge({"table": "domains"})
                    .changes(include_initial=True)
                )
                .union(
                    r.table("engine")
                    .pluck("threads", "status_all_threads")
                    .merge({"table": "engine"})
                    .changes()
                )
                .run(self.r_conn)
            ):
                if self.stop:
                    break
                if c.get("new_val", None) != None:
                    if c["new_val"].get("table", False) == "engine":
                        if c["new_val"]["status_all_threads"] == "Stopping":
                            break
                        else:
                            continue

                logs.downloads.debug("DOWNLOAD CHANGES DETECTED:")
                logs.downloads.debug(pprint.pformat(c))

                if c.get("old_val", None) is None:
                    if c["new_val"]["status"] == "DownloadStarting":
                        self.start_download(c["new_val"])
                elif c.get("new_val", None) is None:
                    if c["old_val"]["status"] in ["DownloadAborting"]:
                        self.remove_download_thread(c["old_val"])

                elif "old_val" in c and "new_val" in c:
                    if (
                        c["old_val"]["status"] == "DownloadFailed"
                        and c["new_val"]["status"] == "DownloadStarting"
                    ):
                        self.start_download(c["new_val"])

                    elif (
                        c["old_val"]["status"] == "Downloaded"
                        and c["new_val"]["status"] == "Deleting"
                    ):
                        if c["new_val"]["table"] == "media":
                            self.delete_media(c["new_val"])

                    elif (
                        c["old_val"]["status"] == "Deleting"
                        and c["new_val"]["status"] == "Deleted"
                    ):
                        if c["new_val"]["table"] == "media":
                            remove_media(c["new_val"]["id"])

                    elif (
                        c["old_val"]["status"] == "DownloadFailed"
                        and c["new_val"]["status"] == "Deleting"
                    ):
                        if c["new_val"]["table"] == "media":
                            remove_media(c["new_val"]["id"])

                    elif (
                        c["old_val"]["status"] == "Downloading"
                        and c["new_val"]["status"] == "DownloadFailed"
                    ):
                        pass

                    elif (
                        c["old_val"]["status"] == "DownloadStarting"
                        and c["new_val"]["status"] == "Downloading"
                    ):
                        pass

                    elif (
                        c["old_val"]["status"] == "Downloading"
                        and c["new_val"]["status"] == "Downloaded"
                    ):
                        pass

                    elif (
                        c["old_val"]["status"] == "Downloading"
                        and c["new_val"]["status"] == "DownloadAborting"
                    ):
                        self.abort_download(c["new_val"])

                    elif (
                        c["old_val"]["status"] == "Downloading"
                        and c["new_val"]["status"] == "ResetDownloading"
                    ):
                        self.abort_download(c["new_val"], final_status="DownloadFailed")


def launch_thread_download_changes(
    manager, pool_id, q_workers, threads_disk_operations
):
    # q_workers should be q_disk_operations?
    t = DownloadChangesThread(manager, pool_id, q_workers, threads_disk_operations)
    t.daemon = True
    t.start()
    return t
