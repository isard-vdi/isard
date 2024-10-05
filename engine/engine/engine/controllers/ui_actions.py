# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

import itertools
import time
import traceback
from os.path import dirname as extract_dir_path
from pprint import pformat

# from qcow import create_disk_from_base, backing_chain, create_cmds_disk_from_base
from time import sleep

from engine.models.domain_xml import (
    BUS_TYPES,
    DomainXML,
    populate_dict_hardware_from_create_dict,
    recreate_xml_if_gpu,
    recreate_xml_if_start_paused,
    recreate_xml_to_start,
    update_xml_from_dict_domain,
)
from engine.services.db import (
    create_disk_template_created_list_in_domain,
    delete_domain,
    domains_with_attached_disk,
    domains_with_attached_storage_id,
    get_dict_from_item_in_table,
    get_domain,
    get_domain_forced_hyp,
    get_domain_hyp_started,
    get_hypers_in_pool,
    get_table_field,
    get_table_fields,
    insert_domain,
    remove_dict_new_template_from_domain,
    remove_disk_template_created_list_in_domain,
    update_domain_dict_hardware,
    update_domain_force_update,
    update_domain_forced_hyp,
    update_domain_hyp_started,
    update_domain_hyp_stopped,
    update_domain_status,
    update_origin_and_parents_to_new_template,
    update_table_field,
    update_vgpu_uuid_domain_action,
)
from engine.services.db.storage_pool import get_category_storage_pool_id
from engine.services.lib.functions import exec_remote_list_of_cmds
from engine.services.lib.qcow import (
    add_cmds_if_custom,
    create_cmd_disk_from_scratch,
    create_cmds_delete_disk,
    create_cmds_disk_from_base,
    get_host_disk_operations_from_path,
    get_path_to_disk,
)
from engine.services.lib.storage import (
    create_storage,
    get_storage_id_filename,
    insert_storage,
    update_storage_deleted_domain,
)
from engine.services.log import *
from isardvdi_common.domain import Domain

DEFAULT_HOST_MODE = "host-passthrough"

# normal priority in PriorityQueueIsard is 100
# lower number => more priority
Q_PRIORITY_START = 50
Q_PRIORITY_STARTPAUSED = 60
Q_PRIORITY_DELETE = 150
Q_PRIORITY_STOP = 40  # Destroy
Q_PRIORITY_SHUTDOWN = 80  # Soft Shut-Down
Q_PRIORITY_PERSONAL_UNIT = 130  # Mount personal unit inside a desktop

Q_LONGOPERATIONS_PRIORITY_CREATE_TEMPLATE_DISK = 50
Q_LONGOPERATIONS_PRIORITY_CREATE_DISK_FROM_TEMPLATE = 40
Q_LONGOPERATIONS_PRIORITY_DOMAIN_FROM_TEMPLATE = 40


class UiActions(object):
    def __init__(self, manager):
        log.info("Backend uiactions created")
        self.manager = manager
        self.round_robin_index_non_persistent = 0

    def action_from_api(self, action, parameters):
        if action == "start_domain":
            if "ssl" in parameters.keys() and parameters["ssl"] == False:
                ssl_spice = False
            if "domain_id" in parameters.keys():
                self.start_domain_from_id(parameters["domain_id"], ssl_spice)

    ### STARTING DOMAIN
    def start_domain_from_id(self, id_domain, ssl=True, starting_paused=False):
        # INFO TO DEVELOPER, QUE DE UN ERROR SI EL ID NO EXISTE

        domain = get_table_fields(
            "domains",
            id_domain,
            [
                "kind",
                "name",
                {"create_dict": {"hardware": "memory", "reservables": True}},
                "forced_hyp",
                "favourite_hyp",
                "hypervisors_pools",
                "force_gpus",
                "force_update",
            ],
        )
        if not domain:
            log.error(f"Domain {id_domain} not found. Can't start. Maybe deleted?")
            return False

        if not Domain(id_domain).storage_ready:
            update_domain_status(
                "Stopped",
                id_domain,
                detail=f"Desktop storage not ready",
            )
            return False

        # memory = domain.get("create_dict", {}).get("hardware", {}).get("memory", 0)
        # if type(memory) is int or type(memory) is float:
        #     memory_in_gb = memory / 1024 / 1024
        # else:
        #     memory_in_gb = 0
        if domain["kind"] != "desktop":
            log.error(
                f"DANGER, domain {id_domain} ({domain['name']}) is a template and can't be started"
            )
            update_domain_status(
                "Stopped",
                id_domain,
                detail="Template can not be started",
            )
            return False

        try:
            pool_id = domain.get("hypervisors_pools", ["default"])[0]
        except:
            pool_id = "default"
            log.error(
                f"Domain {id_domain} has no hypervisors_pools. Using default pool."
            )

        cpu_host_model = self.manager.pools[pool_id].conf.get(
            "cpu_host_model", DEFAULT_HOST_MODE
        )

        if domain.get("force_update"):
            if self.update_hardware_dict_and_xml_from_create_dict(id_domain):
                update_domain_force_update(id_domain, False)
            else:
                return False

        try:
            xml = recreate_xml_to_start(id_domain, ssl, cpu_host_model)
        except Exception as e:
            logs.exception_id.debug("0010")
            log.error("recreate_xml_to_start in domain {}".format(id_domain))
            log.error("Traceback: \n .{}".format(traceback.format_exc()))
            log.error("Exception message: {}".format(e))
            xml = False

        if xml is False:
            update_domain_status(
                "Failed",
                id_domain,
                detail="DomainXML can not parse and modify xml to start",
            )
            return False
        else:
            if starting_paused is True:
                hyp = self.start_paused_domain_from_xml(
                    xml,
                    id_domain,
                    pool_id=pool_id,
                    forced_hyp=domain.get("forced_hyp"),
                    favourite_hyp=domain.get("favourite_hyp"),
                    force_gpus=domain.get("force_gpus"),
                    reservables=domain.get("create_dict", {}).get("reservables", {}),
                )
            else:
                hyp = self.start_domain_from_xml(
                    xml,
                    id_domain,
                    pool_id=pool_id,
                    forced_hyp=domain.get("forced_hyp"),
                    favourite_hyp=domain.get("favourite_hyp"),
                    force_gpus=domain.get("force_gpus"),
                    reservables=domain.get("create_dict", {}).get("reservables", {}),
                )
            return hyp

    def start_paused_domain_from_xml(
        self,
        xml,
        id_domain,
        pool_id="default",
        forced_hyp=None,
        favourite_hyp=None,
        force_gpus=None,
        reservables=None,
    ):
        # def start_paused_domain_from_xml(self, xml, id_domain, pool_id, start_after_created=False):
        return self.start_domain_from_xml(
            xml,
            id_domain,
            pool_id,
            action="start_paused_domain",
            forced_hyp=forced_hyp,
            favourite_hyp=favourite_hyp,
            # We set force_gpus and reservables to None because we'll override all the
            # GPU configuration in order to be able to create GPU desktops without having
            # an hypervisor online hypervisor with GPUs
            force_gpus=None,
            reservables=None,
        )

    def start_domain_from_xml(
        self,
        xml,
        id_domain,
        pool_id="default",
        action="start_domain",
        forced_hyp=None,
        favourite_hyp=None,
        force_gpus=None,
        reservables=None,
    ):
        failed = False
        if pool_id in self.manager.pools.keys():
            next_hyp, extra_info = self.manager.pools[
                pool_id
            ].balancer.get_next_hypervisor(
                forced_hyp=forced_hyp,
                favourite_hyp=favourite_hyp,
                reservables=reservables,
                force_gpus=force_gpus,
            )
            if next_hyp is not False:
                if action == "start_paused_domain":
                    # in updates start paused doesn't try gpus
                    extra_info = {}

                if extra_info.get("nvidia", False) is True:
                    xml = recreate_xml_if_gpu(xml, extra_info["uid"])
                    # nvidia_uid = extra_info["uid"]
                    # update_vgpu_reserved(extra_info["gpu_id"], extra_info["profile"], nvidia_uid, id_domain)
                    update_vgpu_uuid_domain_action(
                        extra_info["gpu_id"],
                        extra_info["uid"],
                        "domain_reserved",
                        domain_id=id_domain,
                        profile=extra_info["profile"],
                    )

                if LOG_LEVEL == "DEBUG":
                    print(f"%%%% DOMAIN: {id_domain} -- action: {action} %%%%")
                    print(
                        f"%%%% DOMAIN: {id_domain} -- XML TO START IN HYPERVISOR: {next_hyp} %%%%"
                    )
                    print(xml)
                    update_table_field("domains", id_domain, "xml_to_start", xml)
                    print(
                        "%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%"
                    )

                dict_action = {
                    "type": action,
                    "xml": xml,
                    "id_domain": id_domain,
                }

                if extra_info.get("nvidia", False) is True:
                    dict_action["nvidia_uid"] = extra_info.get("uid", False)
                    dict_action["profile"] = extra_info.get("profile", False)
                    dict_action["vgpu_id"] = extra_info["gpu_id"]

                priority = Q_PRIORITY_START

                if action == "start_paused_domain":
                    # start_paused only with 256 of memory
                    dict_action["xml"] = recreate_xml_if_start_paused(xml)
                    update_domain_status(
                        status="CreatingDomain",
                        id_domain=id_domain,
                        hyp_id=False,
                        detail="Waiting to try starting paused in hypervisor {} in pool {} ({} operations in queue)".format(
                            next_hyp, pool_id, self.manager.q.workers[next_hyp].qsize()
                        ),
                    )
                    priority = Q_PRIORITY_STARTPAUSED

                self.manager.q.workers[next_hyp].put(dict_action, priority)

            else:
                failed = True
        else:
            log.error("pool_id {} does not exists??".format(pool_id))
            failed = True

        if failed is True:
            if (
                reservables
                and reservables.get("vgpus")
                and len(reservables.get("vgpus", []))
            ):
                detail = f"desktop not started: no hypervisors online with GPU model available and profile"
            else:
                detail = f"desktop not started: no hypervisors online in pool {pool_id}"
            update_domain_status(
                status="Failed", id_domain=id_domain, hyp_id=next_hyp, detail=detail
            )
            return False
        else:
            return next_hyp

    def destroy_domain_from_id(self, id):
        pass

    def stop_domain_from_id(self, id):
        # INFO TO DEVELOPER. puede pasar que alguna actualización en algún otro hilo del status haga que
        # durante un corto período de tiempo devuelva None,para evitarlo durante un segundo vamos a ir pidiendo cada
        # 100 ms que nos de el hypervisor
        time_wait = 0.0
        while time_wait <= 20.0:
            hyp_id = get_domain_hyp_started(id)
            if hyp_id != None:
                if len(hyp_id) > 0:
                    break
            else:
                time_wait = time_wait + 0.1
                sleep(0.1)
                log.debug(
                    "waiting {} seconds to find hypervisor started for domain {}".format(
                        time_wait, id
                    )
                )
        log.debug("stop domain id {} in {}".format(id, hyp_id))
        # hyp_id = get_domain_hyp_started(id)
        # log.debug('stop domain id {} in {}'.format(id,hyp_id))
        if hyp_id is None:
            hyp_id = ""
        if len(hyp_id) <= 0:
            log.debug("hypervisor where domain {} is started not found".format(id))
            update_domain_status(
                status="Unknown",
                id_domain=id,
                hyp_id=None,
                detail="hypervisor where domain {} is started not found".format(id),
            )
        else:
            self.stop_domain(id, hyp_id)

    def shutdown_domain(self, id_domain, hyp_id, delete_after_stopped=False):
        action = {
            "type": "shutdown_domain",
            "id_domain": id_domain,
            "delete_after_stopped": delete_after_stopped,
        }

        self.manager.q.workers[hyp_id].put(action, Q_PRIORITY_SHUTDOWN)
        logs.main.debug(
            f"desktop {id_domain} in queue to soft off with shutdown ACPI action in hyp {hyp_id}"
        )

        return True

    def stop_domain(
        self, id_domain, hyp_id, delete_after_stopped=False, not_change_status=False
    ):
        action = {
            "type": "stop_domain",
            "id_domain": id_domain,
            "delete_after_stopped": delete_after_stopped,
            "not_change_status": not_change_status,
        }
        self.manager.q.workers[hyp_id].put(action, Q_PRIORITY_STOP)
        logs.main.debug(
            f"desktop {id_domain} in queue to destroy action in hyp {hyp_id}"
        )
        return True

    def reset_domain(self, id_domain, hyp_id):
        action = {
            "type": "reset_domain",
            "id_domain": id_domain,
        }
        self.manager.q.workers[hyp_id].put(action, Q_PRIORITY_STOP)
        logs.main.debug(f"desktop {id_domain} added to queue to be reset in {hyp_id}")
        return True

    def delete_domain(self, id_domain):
        pass

    # quitar también las estadísticas y eventos

    def delete_template(self, id_template):
        pass

    # return false si hay alguna derivada

    def update_template(
        self, id_template, name, description, cpu, ram, id_net=None, force_server=None
    ):
        pass

    def update_domain(
        self,
        id_old,
        id_new,
        # user,
        # category,
        # group,
        name,
        description,
        cpu,
        ram,
        id_net=None,
        force_server=None,
        # only_cmds=False,
        # path_to_disk_dir=None,
        disk_filename=None,
    ):
        # INFO TO DEVELOPER: ojo al renombrar el id del dominio, Hay que eliminar y recrear el
        # dominio en rethink y cambiar el nombre del fichero que me lo pasará ui
        # la ui siempre me pasa todoas
        # si id_old == id_new solo update, si no eliminar y rehacer disco
        pass

        # alberto: comentar con josep maria,

    # en principio crea todo lo que se necesita en la base de datos
    # esta función sólo ha de crear el disco derivado donde le diga el campo de la base de datos
    # recrear el xml y verificar que se define o arranca ok
    # yo crearía el disco con una ruta relativa respecto a una variable de configuración
    # y el path que se guarda en el disco podría ser relativo, aunque igual no vale la pena...

    def deleting_disks_from_domain(self, id_domain, not_change_status=False):
        try:
            dict_domain = get_domain(id_domain)
            if dict_domain is None:
                log.error(
                    "DELETE_DOMAIN_DISKS: Domain {} not found in database. Not removing any disk.".format(
                        id_domain
                    )
                )
                return False

            if dict_domain["kind"] != "desktop":
                log.warning(
                    "DELETE_DOMAIN_DISKS: Domain {} is a template!. It's disks will be deleted. Disks who depends on this one will be unusabe and should be deleted.".format(
                        id_domain
                    )
                )

            wait_for_disks_to_be_deleted = False
            if dict_domain.get("hardware"):
                if len(dict_domain["hardware"]["disks"]) > 0:
                    index_disk = 0

                    for d in dict_domain["hardware"]["disks"]:
                        storage_id = d.get("storage_id")
                        if not storage_id:
                            # Old disks in domain
                            disk_path = d.get("file")
                            if not disk_path:
                                log.error(
                                    "DELETE_DOMAIN_DISKS: Domain {} disk in old format and not found the file key in db entry. Unable to delete disk entry: \n {}".format(
                                        id_domain, pformat(d)
                                    )
                                )
                                index_disk += 1
                                continue
                            # Check for duplicates
                            if len(domains_with_attached_disk(disk_path)) > 1:
                                log.debug(
                                    "DELETE_DOMAIN_DISKS: Others than this domain {} have this old format disk {} attached. Skipping deleting disk.".format(
                                        id_domain, disk_path
                                    )
                                )
                                index_disk += 1
                                continue
                        else:
                            # New disks in storage
                            disk_path = get_storage_id_filename(storage_id)
                            if not disk_path:
                                log.error(
                                    "DELETE_DOMAIN_DISKS: Domain {} storage_id {} missing disk path or not in storage table. This should not happen.".format(
                                        id_domain, storage_id
                                    )
                                )
                                index_disk += 1
                                continue
                            # Check for duplicates
                            if (
                                len(domains_with_attached_storage_id(d["storage_id"]))
                                > 1
                            ):
                                log.debug(
                                    "DELETE_DOMAIN_DISKS: Others than this domain {} have this storage_id {} attached. Skipping deleting disk.".format(
                                        id_domain, storage_id
                                    )
                                )
                                index_disk += 1
                                continue

                        pool_id = dict_domain["hypervisors_pools"][0]
                        if pool_id not in self.manager.pools.keys():
                            log.error(
                                "DELETE_DOMAIN_DISKS: Hypervisor pool {} not available in manager. Unable to delete domain {} disk {} in pool.".format(
                                    pool_id, id_domain, disk_path
                                )
                            )
                            return False

                        # Which hypervisors are online in this pool?
                        (
                            hyps_to_start,
                            hyps_only_forced,
                            hyps_all,
                        ) = get_hypers_in_pool(pool_id, only_online=True)
                        if not len(hyps_all):
                            log.error(
                                "DELETE_DOMAIN_DISKS: No hypervisors online in pool {} to delete disk {}".format(
                                    pool_id, disk_path
                                )
                            )
                            return False

                        # Choose a hypervisor to delete the disk
                        forced_hyp, favourite_hyp = get_domain_forced_hyp(id_domain)
                        if forced_hyp in hyps_all:
                            next_hyp = forced_hyp
                        elif favourite_hyp in hyps_all:
                            next_hyp = favourite_hyp
                        else:
                            next_hyp = hyps_all[0]

                        if type(next_hyp) is tuple:
                            h = next_hyp[0]
                            next_hyp = h
                        log.debug(
                            "DELETE_DOMAIN_DISKS: Preparing disk {} to be enqueued in hypervisor {}...".format(
                                disk_path, next_hyp
                            )
                        )
                        mv_to_extension_deleted = self.manager.pools[pool_id].conf.get(
                            "mv_to_extension_deleted", False
                        )
                        cmds = create_cmds_delete_disk(
                            disk_path, mv_to_extension_deleted=mv_to_extension_deleted
                        )

                        action = dict()
                        action["id_domain"] = id_domain
                        action["not_change_status"] = not_change_status
                        action["type"] = "delete_disk"
                        action["disk_path"] = disk_path
                        action["domain"] = id_domain
                        action["ssh_commands"] = cmds
                        action["index_disk"] = index_disk
                        action["storage_id"] = (
                            dict(
                                enumerate(
                                    dict_domain.get("create_dict", {})
                                    .get("hardware", {})
                                    .get("disks", [])
                                )
                            )
                            .get(index_disk, {})
                            .get("storage_id")
                        )

                        try:
                            if not_change_status is False:
                                update_domain_status(
                                    status="DeletingDomainDisk",
                                    id_domain=id_domain,
                                    hyp_id=next_hyp,
                                    detail="Domain disk {} queued in hypervisor {} to be deleted".format(
                                        disk_path, next_hyp
                                    ),
                                )
                            else:
                                update_storage_deleted_domain(
                                    action["storage_id"], dict_domain
                                )
                            log.info(
                                "DELETE_DOMAIN_DISKS: Domain {} disk {} queued in hypervisor {} to be deleted".format(
                                    id_domain, disk_path, next_hyp
                                )
                            )
                            self.manager.q.workers[next_hyp].put(
                                action, Q_PRIORITY_DELETE
                            )
                            wait_for_disks_to_be_deleted = True
                        except Exception as e:
                            logs.exception_id.debug("0011")
                            if not_change_status is False:
                                update_domain_status(
                                    status="Stopped",
                                    id_domain=id_domain,
                                    hyp_id=False,
                                    detail="Domain disk {} failed to be queued in hypervisor {} to be deleted".format(
                                        disk_path, next_hyp
                                    ),
                                )
                            log.error(
                                "DELETE_DOMAIN_DISKS: Unable to enqueue disk {} to be deleted in hypervisor {}. Exception: {}".format(
                                    disk_path, next_hyp, e
                                )
                            )
                            return False
                        index_disk += 1
                else:
                    log.debug(
                        "DELETE_DOMAIN_DISKS: No disks to delete in domain {}".format(
                            id_domain
                        )
                    )
            else:
                log.error(
                    "DELETE_DOMAIN_DISKS: No hardware dict in domain to delete {}. This should not happen".format(
                        id_domain
                    )
                )
            if not wait_for_disks_to_be_deleted:
                delete_domain(id_domain)
            return True
        except Exception as e:
            logs.exception_id.debug("0071")
            log.error(
                "DELETE_DOMAIN_DISKS: Internal error when deleting disks for domain {}".format(
                    id_domain
                )
            )
            log.error("Traceback: \n .{}".format(traceback.format_exc()))
            log.error("Exception message: {}".format(e))
            return False

    def update_info_after_stopped_domain(self, domain_id):
        hyp_to_disk_info = get_table_field("domains", domain_id, "last_hyp_id")
        action = {"domain_id": domain_id, "type": "update_storage_size"}
        if hyp_to_disk_info in self.manager.q_disk_operations.keys():
            self.manager.q_disk_operations[hyp_to_disk_info].put(action)

    def create_template_disks_from_domain(self, id_domain):
        dict_domain = get_domain(id_domain)
        if dict_domain is None:
            log.error(
                "CREATE_TEMPLATE_DISKS_FROM_DOMAIN: Domain {} not found in database. Not creating any disk.".format(
                    id_domain
                )
            )
            return False
        create_dict = dict_domain["create_dict"]

        pool_id = get_category_storage_pool_id(dict_domain.get("category"))

        try:
            dict_new_template = create_dict["template_dict"]
        except KeyError as e:
            update_domain_status(
                status="Stopped",
                id_domain=id_domain,
                hyp_id=False,
                detail="Action Creating Template from domain failed. No template_json in domain dictionary",
            )
            log.error(
                "No template_dict in keys of domain dictionary, when creating template form domain {}. Exception: {}".format(
                    id_domain, str(e)
                )
            )
            return False

        if not Domain(id_domain).storage_ready:
            update_domain_status(
                "Stopped",
                id_domain,
                detail="Desktop storages aren't ready",
            )
            return False

        disk_index_in_bus = 0
        if "disks" in dict_domain["hardware"]:
            disk_list = [d for d in create_dict["hardware"]["disks"]]
            create_disk_template_created_list_in_domain(id_domain)
            for i in range(len(disk_list)):
                # for disk in dict_domain['hardware']['disks']:
                path_domain_disk = dict_domain["hardware"]["disks"][i]["file"]
                type_path_selected = "template"

                new_file, path_selected = get_path_to_disk(
                    category_id=dict_domain.get("category"),
                    type_path=type_path_selected,
                    extension=dict_new_template["create_dict"]["hardware"]["disks"][i][
                        "extension"
                    ],
                )
                path_absolute_template_disk = new_file = new_file.replace("//", "/")
                dict_new_template["create_dict"]["hardware"]["disks"][i][
                    "file"
                ] = new_file
                dict_new_template["create_dict"]["hardware"]["disks"][i][
                    "path_selected"
                ] = path_selected

                disk = dict_new_template["create_dict"]["hardware"]["disks"][i]
                create_storage(
                    disk, dict_domain.get("user"), force_parent=None, perms=["r"]
                )
                update_table_field("domains", id_domain, "create_dict", create_dict)

                action = {}
                action["id_domain"] = id_domain
                action["type"] = "create_template_disk_from_domain"
                action["path_template_disk"] = path_absolute_template_disk
                action["path_domain_disk"] = path_domain_disk
                action["disk_index"] = disk_index_in_bus
                action["storage_id"] = disk.get("storage_id")

                hyp_to_disk_create = get_host_disk_operations_from_path(
                    self.manager,
                    pool=pool_id,
                    type_path=type_path_selected,
                )

                # INFO TO DEVELOPER: falta terminar de ver que hacemos con el pool para crear
                # discos, debería haber un disk operations por pool
                try:
                    update_domain_status(
                        status="CreatingTemplateDisk",
                        id_domain=id_domain,
                        hyp_id=False,
                        detail="Creating template disk operation is launched in hostname {} ({} operations in queue)".format(
                            hyp_to_disk_create,
                            self.manager.q_disk_operations[hyp_to_disk_create].qsize(),
                        ),
                    )
                    self.manager.q_disk_operations[hyp_to_disk_create].put(
                        action, Q_LONGOPERATIONS_PRIORITY_CREATE_TEMPLATE_DISK
                    )
                except Exception as e:
                    logs.exception_id.debug("0012")
                    update_domain_status(
                        status="Stopped",
                        id_domain=id_domain,
                        hyp_id=False,
                        detail="Creating template operation failed when insert action in queue for disk operations",
                    )
                    log.error(
                        "Creating disk operation failed when insert action in queue for disk operations in host {}. Exception: {}".format(
                            hyp_to_disk_create, e
                        )
                    )
                    return False

                    disk_index_in_bus = disk_index_in_bus + 1

            return True

            # first: move and rename disk to templates folder

    def create_template_in_db(self, id_domain):
        domain_dict = get_domain(id_domain)
        if domain_dict is None:
            log.error(
                "CREATE_TEMPLATE_IN_DB_FROM_DOMAIN: Domain {} not found in database. Not creating any disk.".format(
                    id_domain
                )
            )
            return False
        template_dict = domain_dict["create_dict"]["template_dict"]
        template_dict["status"] = "CreatingNewTemplateInDB"
        template_id = template_dict["id"]
        for d_disk in template_dict["create_dict"]["hardware"].get("disks", {}):
            if "storage_id" in d_disk.keys():
                for k in list(d_disk.keys()):
                    if k != "storage_id":
                        d_disk.pop(k)
        if insert_domain(template_dict)["inserted"] == 1:
            hw_dict = domain_dict["hardware"].copy()
            for i in range(len(hw_dict["disks"])):
                hw_dict["disks"][i] = template_dict["create_dict"]["hardware"]["disks"][
                    i
                ]
            update_table_field(
                "domains", template_id, "hardware", hw_dict, merge_dict=False
            )
            xml_parsed = update_xml_from_dict_domain(
                id_domain=template_id, xml=domain_dict["xml"]
            )
            if xml_parsed is False:
                update_domain_status(
                    status="Failed",
                    id_domain=template_id,
                    hyp_id=False,
                    detail="XML Parser Error, xml is not valid",
                )
                return False
            remove_disk_template_created_list_in_domain(id_domain)
            remove_dict_new_template_from_domain(id_domain)
            if "parents" in domain_dict.keys():
                domain_parents_chain_update = domain_dict["parents"].copy()
            else:
                domain_parents_chain_update = []

            domain_parents_chain_update.append(template_id)
            update_table_field(
                "domains", id_domain, "parents", domain_parents_chain_update
            )
            update_origin_and_parents_to_new_template(id_domain, template_id)
            # update_table_field('domains', template_id, 'xml', xml_parsed, merge_dict=False)
            update_domain_status(
                status="Stopped",
                id_domain=template_id,
                hyp_id=False,
                detail="Template created, ready to create domains from this template",
            )
            update_domain_status(
                status="Stopped",
                id_domain=id_domain,
                hyp_id=False,
                detail="Template created from this domain, now domain is ready to start again",
            )

        else:
            log.error(
                "template {} can not be inserted in rethink, domain_id duplicated??".format(
                    template_id
                )
            )
            return False

    def creating_disk_from_scratch(self, id_new):
        dict_domain = get_domain(id_new)
        if dict_domain is None:
            log.error(
                "CREATING_DISK_FROM_SCRATCH: Domain {} not found in database. Not creating any disk.".format(
                    id_new
                )
            )
            return False
        pool_id = get_category_storage_pool_id(dict_domain.get("category"))

        dict_to_create = dict_domain["create_dict"]

        if "disks" in dict_to_create["hardware"].keys():
            if len(dict_to_create["hardware"]["disks"]) > 0:
                # for index_disk in range(len(dict_to_create['hardware']['disks'])):
                #     relative_path = dict_to_create['hardware']['disks'][index_disk]['file']
                #     path_new_file, path_selected = get_path_to_disk(relative_path, pool=pool_id)
                #     # UPDATE PATH IN DOMAIN
                #     dict_to_create['hardware']['disks'][index_disk]['file'] = new_file
                #     dict_to_create['hardware']['disks'][index_disk]['path_selected'] = path_selected

                path_new_disk, path_selected = get_path_to_disk(
                    category_id=dict_domain.get("category"),
                    extension=dict_to_create["hardware"]["disks"][0]["extension"],
                )
                # UPDATE PATH IN DOMAIN

                d_update_domain = {"hardware": {"disks": [{}]}}
                if len(dict_to_create["hardware"]["disks"]) > 0:
                    ## supplementary disks
                    for i, dict_other_disk in enumerate(
                        dict_to_create["hardware"]["disks"][1:]
                    ):
                        path_other_disk, path_other_disk_selected = get_path_to_disk(
                            relative_path=dict_other_disk["file"],
                            category_id=dict_domain.get("category"),
                            type_path=dict_other_disk["type_path"],
                        )
                        d_update_domain["hardware"]["disks"].append({})
                        d_update_domain["hardware"]["disks"][i + 1][
                            "file"
                        ] = path_other_disk
                        d_update_domain["hardware"]["disks"][i + 1][
                            "path_selected"
                        ] = path_other_disk_selected
                        d_update_domain["hardware"]["disks"][i + 1]["bus"] = (
                            dict_other_disk.get("bus", "virtio")
                        )
                        if dict_other_disk.get("readonly", True) is True:
                            d_update_domain["hardware"]["disks"][i + 1][
                                "readonly"
                            ] = True
                        else:
                            pass
                            # TODO
                            # update_media_write_access_by_domain(id_media,id_domain)

                d_update_domain["hardware"]["disks"][0]["file"] = path_new_disk
                d_update_domain["hardware"]["disks"][0]["path_selected"] = path_selected
                d_update_domain["hardware"]["disks"][0]["size"] = dict_to_create[
                    "hardware"
                ]["disks"][0]["size"]
                if "bus" in dict_to_create["hardware"]["disks"][0].keys():
                    if dict_to_create["hardware"]["disks"][0]["bus"] in BUS_TYPES:
                        d_update_domain["hardware"]["disks"][0]["bus"] = dict_to_create[
                            "hardware"
                        ]["disks"][0]["bus"]
                update_domain_dict_hardware(id_new, d_update_domain)
                # update_domain_dict_create_dict(id_new, d_update_domain)
                storage_id = create_storage(
                    d_update_domain["hardware"]["disks"][0],
                    dict_domain.get("user"),
                    force_parent=None,
                )
                update_table_field("domains", id_new, "create_dict", d_update_domain)

                size_str = dict_to_create["hardware"]["disks"][0]["size"]

                hyp_to_disk_create = get_host_disk_operations_from_path(
                    self.manager,
                    pool=pool_id,
                    type_path="desktop",
                )

                cmds = create_cmd_disk_from_scratch(
                    path_new_disk=path_new_disk, size_str=size_str
                )

                action = {}
                action["type"] = "create_disk_from_scratch"
                action["disk_path"] = path_new_disk
                action["index_disk"] = 0
                action["domain"] = id_new
                action["ssh_commands"] = cmds
                action["storage_id"] = storage_id
                try:
                    update_domain_status(
                        status="CreatingDiskFromScratch",
                        id_domain=id_new,
                        hyp_id=False,
                        detail="Creating disk commands are launched in hypervisor {} ({} operations in queue)".format(
                            hyp_to_disk_create,
                            self.manager.q_disk_operations[hyp_to_disk_create].qsize(),
                        ),
                    )
                    self.manager.q_disk_operations[hyp_to_disk_create].put(action)

                except Exception as e:
                    logs.exception_id.debug("0013")
                    update_domain_status(
                        status="Failed",
                        id_domain=id_new,
                        hyp_id=False,
                        detail="Creating disk operation failed when insert action in queue for disk operations",
                    )
                    log.error(
                        "Creating disk operation failed when insert action in queue for disk operations. Exception: {}".format(
                            e
                        )
                    )

        else:
            update_domain_status(
                status="CreatingDomain",
                id_domain=id_new,
                hyp_id=False,
                detail="Creating domain withouth disks",
            )

    def force_deleting(self, domain_id, old_status):
        if old_status in ["Started", "Shutting-down", "Stopping", "Paused"]:
            hyp_id = get_domain_hyp_started(domain_id)

            if hyp_id is not None and hyp_id is not False:
                self.stop_domain(domain_id, hyp_id, not_change_status=True)

        self.deleting_disks_from_domain(domain_id, not_change_status=True)

        result = delete_domain(domain_id)
        log.info(
            f"domain {domain_id} force deleting, launched force destroy domain if started and delete disks in threads."
        )
        if result["deleted"] == 1:
            log.info(f"domain {domain_id} deleted from table domain")
        else:
            log.error(f"domain {domain_id} does not exist in table domain")
        return result

    def creating_disks_from_template(self, id_new):
        dict_domain = get_domain(id_new)
        if dict_domain is None:
            log.error(
                "CREATING_DISKS_FROM_TEMPLATE: Domain {} not found in database. Not creating any disk.".format(
                    id_new
                )
            )
            return False
        persistent = dict_domain.get("persistent", True)
        if persistent:
            path_type = "desktop"
        else:
            path_type = "volatile"
        if "create_dict" in dict_domain.keys():
            dict_to_create = dict_domain["create_dict"]

        pool_id = get_category_storage_pool_id(dict_domain.get("category"))

        # INFO TO DEVELOPER DEBERÍA SER UN FOR PARA CADA DISCO
        # y si el disco no tiene backing_chain, crear un disco vacío
        # del tamaño que marcase
        # d['hardware']['disks'][0]['size']
        # el backing_file debería estar asociado a cada disco:
        # d['hardware']['disks'][0]['backing_file']

        for index_disk in range(len(dict_to_create["hardware"]["disks"])):
            new_file, path_selected = get_path_to_disk(
                category_id=dict_domain.get("category"),
                type_path=path_type,
                extension=dict_to_create["hardware"]["disks"][index_disk].pop(
                    "extension"
                ),
            )
            # UPDATE PATH IN DOMAIN
            dict_to_create["hardware"]["disks"][index_disk]["file"] = new_file
            dict_to_create["hardware"]["disks"][index_disk][
                "path_selected"
            ] = path_selected
            create_storage(
                dict_to_create["hardware"]["disks"][index_disk], dict_domain.get("user")
            )

        update_table_field("domains", id_new, "create_dict", dict_to_create)
        update_table_field(
            "storage",
            dict_to_create["hardware"]["disks"][index_disk]["storage_id"],
            "perms",
            ["r", "w"],
        )

        # TODO: REVISAR SI RELAMENTE ES NECESARIO o esta acción responde a versiones antiguas de nuestras funciones de creación
        hardware_update = {}
        hardware_update["disks"] = dict_to_create["hardware"]["disks"]
        update_domain_dict_hardware(id_new, hardware_update)
        ##################

        for index_disk in range(len(dict_to_create["hardware"]["disks"])):
            disk = dict_to_create["hardware"]["disks"][index_disk]
            insert_storage(disk, perms=["r"])
            backing_file = dict_to_create["hardware"]["disks"][index_disk]["parent"]
            new_file = dict_to_create["hardware"]["disks"][index_disk]["file"]
            path_selected = dict_to_create["hardware"]["disks"][index_disk][
                "path_selected"
            ]
            hyp_to_disk_create = get_host_disk_operations_from_path(
                self.manager,
                pool=pool_id,
                type_path=path_type,
            )
            if persistent is False:
                print(f"desktop not persistent, forced hyp: {hyp_to_disk_create}")
                update_domain_forced_hyp(id_domain=id_new, hyp_id=hyp_to_disk_create)

            cmds = create_cmds_disk_from_base(path_base=backing_file, path_new=new_file)
            log.debug(
                "commands to disk create to launch in disk_operations: \n{}".format(
                    "\n".join(cmds)
                )
            )
            action = {}
            action["type"] = "create_disk"
            action["disk_path"] = new_file
            action["index_disk"] = index_disk
            action["domain"] = id_new
            action["storage_id"] = disk.get("storage_id")

            if index_disk == 0:
                cmds += add_cmds_if_custom(id_domain=id_new, path_new=new_file)
                # from pprint import pformat
                # log.info(pformat(cmds))
            action["ssh_commands"] = cmds

            try:
                update_domain_status(
                    status="CreatingDisk",
                    id_domain=id_new,
                    hyp_id=False,
                    detail="Creating disk operation is launched in hypervisor {} ({} operations in queue)".format(
                        hyp_to_disk_create,
                        self.manager.q_disk_operations[hyp_to_disk_create].qsize(),
                    ),
                )
                self.manager.q_disk_operations[hyp_to_disk_create].put(
                    action, Q_LONGOPERATIONS_PRIORITY_CREATE_DISK_FROM_TEMPLATE
                )

            except Exception as e:
                logs.exception_id.debug("0015")
                update_domain_status(
                    status="Failed",
                    id_domain=id_new,
                    hyp_id=False,
                    detail="Creating disk operation failed when insert action in queue for disk operations",
                )
                log.error(
                    "Creating disk operation failed when insert action in queue for disk operations. Exception: {}".format(
                        e
                    )
                )

    def update_hardware_dict_and_xml_from_create_dict(self, id_domain):
        try:
            populate_dict_hardware_from_create_dict(id_domain)
        except Exception as e:
            logs.exception_id.debug("0016")
            log.error(
                "error when populate dict hardware from create dict in domain {}".format(
                    id_domain
                )
            )
            log.error("Traceback: \n .{}".format(traceback.format_exc()))
            log.error("Exception message: {}".format(e))
            update_domain_status(
                "Failed",
                id_domain,
                detail="Updating aborted, failed when populate hardware dictionary",
            )
            return False

        try:
            xml_raw = update_xml_from_dict_domain(id_domain)
            if xml_raw is False:
                update_domain_status(
                    status="Failed",
                    id_domain=id_domain,
                    detail="XML Parser Error, xml is not valid",
                )
                return False

        except Exception as e:
            logs.exception_id.debug("0017")
            log.error(
                "error when populate dict hardware from create dict in domain {}".format(
                    id_domain
                )
            )
            log.error("Traceback: \n .{}".format(traceback.format_exc()))
            log.error("Exception message: {}".format(e))
            update_domain_status(
                "Failed",
                id_domain,
                detail="Updating aborted, failed when updating xml from hardware dictionary",
            )
            return False
        return True

    def updating_from_create_dict(self, id_domain, ssl=True):
        if self.update_hardware_dict_and_xml_from_create_dict(id_domain):
            update_domain_status(
                "Updating",
                id_domain,
                detail="xml and hardware dict updated, waiting to test if domain start paused in hypervisor",
            )
            domain = get_table_fields(
                "domains",
                id_domain,
                [
                    "kind",
                    "name",
                    {"create_dict": {"hardware": "memory", "reservables": True}},
                    "forced_hyp",
                    "favourite_hyp",
                    "hypervisors_pools",
                ],
            )
            pool_id = domain.get("hypervisors_pools")
            if not pool_id or len(pool_id) == 0:
                update_domain_status(
                    "Failed",
                    id_domain,
                    detail="Updating aborted, domain missing hypervisors pool",
                )
                return False
            if len(pool_id):
                pool_id = pool_id[0]
            if domain.get("kind") == "desktop":
                cpu_host_model = self.manager.pools[pool_id].conf.get(
                    "cpu_host_model", DEFAULT_HOST_MODE
                )
                try:
                    xml = recreate_xml_to_start(id_domain, ssl, cpu_host_model)
                except Exception as e:
                    logs.exception_id.debug("0018")
                    log.error("recreate_xml_to_start in domain {}".format(id_domain))
                    log.error("Traceback: \n .{}".format(traceback.format_exc()))
                    log.error("Exception message: {}".format(e))
                    xml = False
                if xml is False:
                    update_domain_status(
                        "Failed",
                        id_domain,
                        detail="DomainXML can not parse and modify xml to start",
                    )
                    return False

                self.start_paused_domain_from_xml(
                    xml=xml,
                    id_domain=id_domain,
                    pool_id=pool_id,
                    forced_hyp=domain.get("forced_hyp"),
                    favourite_hyp=domain.get("favourite_hyp"),
                    reservables=domain.get("create_dict", {}).get("reservables", {}),
                )
            else:
                update_domain_status(
                    "Stopped",
                    id_domain,
                    detail="Created",
                )

                return True

    def creating_and_test_xml_start(
        self,
        id_domain,
        creating_from_create_dict=False,
        xml_from_virt_install=False,
        xml_string=None,
        ssl=True,
        start_paused=True,
    ):
        if creating_from_create_dict is True:
            try:
                populate_dict_hardware_from_create_dict(id_domain)
            except Exception as e:
                logs.exception_id.debug("0019")
                log.error(
                    "error when populate dict hardware from create dict in domain {}".format(
                        id_domain
                    )
                )
                log.error("Traceback: \n .{}".format(traceback.format_exc()))
                log.error("Exception message: {}".format(e))
                return False

        domain = get_domain(id_domain)
        if domain is None:
            log.error(
                "CREATING_AND_TEST_XML_START_DOMAIN: Domain {} not found in database. Not creating any xml.".format(
                    id_domain
                )
            )
            return False
        # create_dict_hw = domain['create_dict']['hardware']
        # for media in ['isos','floppies']
        #     if 'isos' in create_dict_hw.keys():
        #         for index_disk in range(len(create_dict_hw['isos'])):
        #             update_hw['hardware']['isos'][index_disk]['file'] = new_file

        if type(xml_string) is str:
            xml_from = xml_string

        elif "create_from_virt_install_xml" in domain["create_dict"]:
            xml_from = get_dict_from_item_in_table(
                "virt_install", domain["create_dict"]["create_from_virt_install_xml"]
            )["xml"]

        elif xml_from_virt_install is False:
            id_template = domain["create_dict"]["origin"]
            template = get_domain(id_template)
            if template is None:
                logs.main.error(
                    "##### Traceback: creating_and_test_xml_start, xml_from...\n{}\n ...template {} not found when creating domain...\n {}\n...\n{}\n...".format(
                        xml_from, id_template, domain, traceback.format_exc()
                    )
                )
                update_domain_status(
                    "Failed",
                    id_domain,
                    detail=f"Can't create domain from template {id_template}, template not found. Was deleted during domain creation?",
                )
                return False
            xml_from = template["xml"]
            parents_chain = template.get("parents", []) + domain.get("parents", [])
            # when creating template from domain, the domain would be inserted as a parent while template is creating
            # parent_chain never can't have id_domain as parent
            if id_domain in parents_chain:
                for i in range(parents_chain.count("a")):
                    parents_chain.remove(id_domain)

            update_table_field("domains", id_domain, "parents", parents_chain)

        elif xml_from_virt_install is True:
            xml_from = domain["xml_virt_install"]

        else:
            return False

        update_table_field("domains", id_domain, "xml", xml_from)

        try:
            xml_raw = update_xml_from_dict_domain(id_domain)
        except Exception as e:
            logs.exception_id.debug("0020")
            logs.main.info(f"Exception updating xml from dict_domain: {e}")
            update_domain_status(
                status="Failed",
                id_domain=id_domain,
                detail="XML Parser Error, xml is not valid",
            )
            logs.main.error(
                "##### Traceback: \n .{} \n######".format(traceback.format_exc())
            )
            return False

        if xml_raw is False:
            update_domain_status(
                status="Failed",
                id_domain=id_domain,
                detail="XML Parser Error, xml is not valid",
            )
            return False
        update_domain_status(
            "CreatingDomain",
            id_domain,
            detail="xml and hardware dict updated, waiting to test if domain start paused in hypervisor",
        )
        try:
            pool_id = domain.get("hypervisors_pools", ["default"])[0]
        except:
            pool_id = "default"
            log.error(
                f"Domain {id_domain} has no hypervisors_pools. Using default pool."
            )

        if "start_after_created" in domain.keys():
            if domain["start_after_created"] is True:
                update_domain_status(
                    "StartingDomainDisposable",
                    id_domain,
                    detail="xml and hardware dict updated, starting domain disposable",
                )

                # update_domain_status('Starting', id_domain,
                #                      detail='xml and hardware dict updated, starting domain disposable')

                self.start_domain_from_id(id_domain)

        else:
            # change viewer password, remove selinux options and recreate network interfaces
            try:
                cpu_host_model = self.manager.pools[pool_id].conf.get(
                    "cpu_host_model", DEFAULT_HOST_MODE
                )
                xml = recreate_xml_to_start(id_domain, ssl, cpu_host_model)
            except Exception as e:
                logs.exception_id.debug("0021")
                log.error("recreate_xml_to_start in domain {}".format(id_domain))
                log.error("Traceback: \n .{}".format(traceback.format_exc()))
                log.error("Exception message: {}".format(e))
                xml = False

            if xml is False:
                update_domain_status(
                    "Failed",
                    id_domain,
                    detail="DomainXML can't parse and modify xml to start",
                )
            else:
                # If comes from creating disk do not start paused
                if start_paused is True:
                    self.start_paused_domain_from_xml(
                        xml=xml,
                        id_domain=id_domain,
                        pool_id=pool_id,
                        forced_hyp=domain.get("forced_hyp"),
                        favourite_hyp=domain.get("favourite_hyp"),
                        reservables=domain.get("create_dict", {}).get(
                            "reservables", {}
                        ),
                    )
                else:
                    update_domain_status(
                        "Stopped",
                        id_domain,
                        detail="Updating finalished, ready to derivate desktops",
                    )

    def domain_from_template(
        self,
        id_template,
        id_new,
        user,
        category,
        group,
        name,
        description,
        cpu,
        ram,
        current_ram=-1,
        id_net=None,
        force_server=None,
        only_cmds=False,
        path_to_disk_dir=None,
        disk_filename=None,
        create_domain_in_db=True,
    ):
        # INFO TO DEVELOPER: falta verificar que el id no existe y si existe salir enseguida, ya que si no haríamos updates y
        # creaciónes de disco peligrosas
        dict_domain_template = get_domain(id_template)
        if dict_domain_template is None:
            log.error(
                "CREATE_TEMPLATE_DISKS_FROM_DOMAIN: Template {} not found in database. Not creating any domain.".format(
                    id_template
                )
            )
            return False
        dict_domain_new = dict_domain_template.copy()
        dict_domain_new["id"] = id_new
        dict_domain_new["user"] = user
        dict_domain_new["category"] = category
        dict_domain_new["group"] = group
        dict_domain_new["kind"] = "desktop"
        dict_domain_new["name"] = name
        dict_domain_new["description"] = description
        dict_domain_new["status"] = "CreatingDisk"
        dict_domain_new["detail"] = "Defining new domain"

        if force_server == True:
            dict_domain_new["server"] = True
        elif force_server == False:
            dict_domain_new["server"] = False
        else:
            dict_domain_new["server"] = dict_domain_template["server"]

        try:
            x = DomainXML(dict_domain_template["xml"], id_domain=id_new)
        except:
            log.error("error when parsing xml")
            dict_domain_new["status"] = "Failed"
            dict_domain_new["detail"] = "XML Parser have failed, xml with errors"
            return False

        x.set_name(id_new)
        x.set_title(name)
        x.set_description(description)

        old_path_disk = dict_domain_template["hardware"]["disks"][0]["file"]
        old_path_dir = extract_dir_path(old_path_disk)

        # DEFAULT_GROUP_DIR = CONFIG_DICT['REMOTEOPERATIONS']['default_group_dir']

        if path_to_disk_dir is None:
            path_to_disk_dir = (
                DEFAULT_GROUP_DIR
                + "/"
                + dict_domain_template["category"]
                + "/"
                + dict_domain_template["group"]
                + "/"
                + dict_domain_template["user"]
            )

        if len(old_path_disk[len(old_path_dir) + 1 : -1].split(".")) > 1:
            extension = old_path_disk[len(old_path_dir) + 1 : -1].split(".")[1]
        else:
            extension = "qcow"

        if disk_filename is None:
            disk_filename = id_new + "." + extension

        new_path_disk = path_to_disk_dir + "/" + disk_filename

        x.set_vcpu(cpu)
        x.set_memory(ram, current=current_ram)
        x.set_vdisk(new_path_disk)
        x.randomize_vm()

        dict_domain_new["hardware"] = x.vm_dict
        dict_domain_new["xml"] = x.return_xml()

        cmds = create_cmds_disk_from_base(
            old_path_disk,
            new_path_disk,
        )

        if only_cmds is True:
            dict_domain_new["status"] = "Crashed"
            dict_domain_new["detail"] = (
                "Disk not created, only for testing ui purpose, create command is not launched"
            )
            return dict_domain_new, cmds

        else:
            action = {}
            action["type"] = "create_disk"
            action["disk_path"] = new_path_disk
            action["domain"] = id_new
            action["ssh_commands"] = cmds
            if hasattr(self.pool, "queue_disk_operation"):
                self.pool.queue_disk_operation.put(
                    action, Q_LONGOPERATIONS_PRIORITY_DOMAIN_FROM_TEMPLATE
                )
                # err,out = create_disk_from_base(old_path_disk,new_path_disk)
                dict_domain_new["status"] = "CreatingDisk"
                dict_domain_new["detail"] = (
                    "Creating disk operation is launched ({} operations in queue)".format(
                        self.pool.queue_disk_operation.qsize()
                    )
                )
                # list_backing_chain = backing_chain(new_path_disk)

                # dict_domain_new['backing_chain'] = list_backing_chain
            else:
                log.error("queue disk operation is not created")
                dict_domain_new["status"] = "Crashed"
                dict_domain_new["detail"] = (
                    "Disk not created, queue for disk creation does not exist"
                )

            if create_domain_in_db is True:
                insert_domain(dict_domain_new)

            return dict_domain_new

    def ferrary_from_domain(
        self,
        id_domain,
        num_domains,
        start_index=0,
        dir_to_ferrary_disks=None,
        prefix=None,
    ):
        if dir_to_ferrary_disks is None:
            dir_to_ferrary_disks = CONFIG_DICT["FERRARY"][
                "DIR_TO_FERRARY_DISKS".lower()
            ]
        if prefix is None:
            prefix = CONFIG_DICT["FERRARY"]["PREFIX".lower()]
        ferrary = []
        for i in range(start_index, num_domains + start_index):
            d = dict()
            d["index"] = str(i).zfill(3)
            d["id"] = prefix + id_domain + d["index"]
            d["dict_domain"], d["cmd"] = self.domain_from_template(
                id_template=id_domain,
                id_new=d["id"],
                only_cmds=True,
                path_to_disk_dir=dir_to_ferrary_disks,
            )
            ferrary.append(d)

        cmds = []
        cmds.append(ferrary[0]["cmd"][0])
        cmds = cmds + list(itertools.chain([d["cmd"][1] for d in ferrary]))

        before = int(time.time())

        cmds_result = exec_remote_list_of_cmds(VDESKTOP_DISK_OPERATINOS, cmds)
        after = int(time.time())
        duration = after - before
        log.debug(
            "FERRARY: {} disks created in {} with name in {} seconds".format(
                num_domains, dir_to_ferrary_disks, prefix + id_domain + "XXX", duration
            )
        )

        for dict_domain_new in [d["dict_domain"] for d in ferrary]:
            insert_domain(dict_domain_new)

        return ferrary

    def start_ferrary(self, ferrary):
        ids = [f["id"] for f in ferrary]
        for id in ids:
            hyp = self.start_domain_from_id(id)
            update_domain_hyp_started(id, hyp)

    def stop_ferrary(self, ferrary):
        ids = [f["id"] for f in ferrary]
        for id in ids:
            hyp_id = get_domain_hyp_started(id)
            self.stop_domain(id, hyp_id)
            update_domain_hyp_stopped(id)

    def delete_ferrary(self, ferrary):
        cmds = [
            "rm -f " + f["dict_domain"]["hardware"]["disks"][0]["file"] for f in ferrary
        ]

        before = int(time.time())

        cmds_result = exec_remote_list_of_cmds(VDESKTOP_DISK_OPERATINOS, cmds)

        after = int(time.time())
        duration = after - before

        ids = [f["id"] for f in ferrary]
        for id in ids:
            delete_domain(id)

        first_disk = ferrary[0]["dict_domain"]["hardware"]["disks"][0]["file"]
        last_disk = ferrary[-1]["dict_domain"]["hardware"]["disks"][0]["file"]
        log.debug(
            "FERRARY: {} disks deleted from {} to {} in {} seconds".format(
                len(cmds), first_disk, last_disk, duration
            )
        )

        return cmds_result

        ## FERRARY

        ### Hypers

        # def set_default_hyper(self,hyp_id):
        #     return change_hyp_disk_operations(hyp_id)
