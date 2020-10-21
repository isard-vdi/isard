# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

# coding=utf-8

import json
import string
import shlex
from random import choices
from pprint import pprint,pformat

from os.path import dirname as extract_dir_path

from engine.services.db.db import get_pool
from engine.services.lib.functions import exec_remote_cmd, size_format, get_threads_names_running, weighted_choice, \
    backing_chain_cmd
from engine.services.log import *
from engine.services.db import get_hyp_hostname_user_port_from_id, update_pool_round_robin
from engine.services.db.domains import get_custom_dict_from_domain, update_custom_all_dict
from engine.services.lib.functions import execute_commands
from engine import config
from engine.services.db.db import get_pools_from_hyp





VDESKTOP_DISK_OPERATINOS = CONFIG_DICT['REMOTEOPERATIONS']['host_remote_disk_operatinos']


def create_cmds_delete_disk(path_disk):
    cmds = list()
    cmd = 'ls -l "{}"'.format(path_disk)
    cmds.append(cmd)

    cmd = 'if [ -f "{}" ] ; then rm -f "{}"; fi'.format(path_disk, path_disk)
    log.debug('delete disk or media cmd: {}'.format(cmd))
    cmds.append(cmd)

    cmd = 'ls -l "{}"'.format(path_disk)
    cmds.append(cmd)

    return cmds


# def check_upload_folder():


def create_cmd_disk_from_scratch(path_new_disk,
                                 size_str,
                                 cluster_size = '4k',
                                 disk_type = 'qcow2',
                                 incremental = True,
                                 user_owner='qemu',
                                 group_owner='qemu'
                                 ):
    cmds1 = list()
    path_dir = extract_dir_path(path_new_disk)
    touch_test_path = path_dir + '/.touch_test'
    cmd_qemu_img = "qemu-img create -f {disk_type} -o cluster_size={cluster_size} {file_path} {size_str}".\
                               format(disk_type = disk_type,
                                       size_str = size_str,
                                   cluster_size = cluster_size,
                                      file_path = path_new_disk)

    cmds1.append({'title': 'mkdir dir', 'cmd': 'mkdir -p {}'.format(path_dir)})
    cmds1.append({'title': 'pre-delete touch', 'cmd': 'rm -f {}'.format(touch_test_path)})
    cmds1.append({'title': 'touch', 'cmd': 'touch {}'.format(touch_test_path)})
    cmds1.append({'title': 'readonly_touch', 'cmd': 'chmod a-wx,g+r,u+r {}'.format(touch_test_path)})
    cmds1.append({'title': 'chgrp_touch', 'cmd': 'chgrp {} {}'.format(group_owner, touch_test_path)})
    cmds1.append({'title': 'chown', 'cmd': 'chown {} {}'.format(user_owner, touch_test_path)})
    cmds1.append({'title': 'verify_touch',
                  'cmd': 'stat -c \'mountpoint:%m group:%G user:%U rights:%A\' {}'.format(touch_test_path)})
    cmds1.append({'title': 'df_mountpoint', 'cmd': 'df $(stat -c \'%m\' {})'.format(touch_test_path)})
    cmds1.append({'title': 'rm_touch', 'cmd': 'rm -f {}'.format(touch_test_path)})

    cmds1.append({'title': 'launch qemu-img', 'cmd': cmd_qemu_img})
    cmds1.append({'title': 'test_if_qcow_exists', 'cmd': 'stat -c \'%d\' {}'.format(path_new_disk)})

    return cmds1

def create_cmd_disk_from_virtbuilder(path_new_qcow,
                                     os_version,
                                     id_os_virt_install,
                                     name_domain_in_xml,
                                     size_str,
                                     memory_in_mb,
                                     options_cmd='',
                                     user_owner='qemu',
                                     group_owner='qemu'):
    cmds1 = list()
    path_dir = extract_dir_path(path_new_qcow)
    path_big_disk = path_new_qcow + '.big'
    path_dir_tmp_sparsify = path_dir + '/tmp'
    touch_test_path = path_dir + '/.touch_test'

    cmd_virt_builder = 'virt-builder {os}  --machine-readable --output {path} --size {size} --format qcow2 {options}' \
        .format(os=os_version, path=path_new_qcow, size=size_str, options=options_cmd)
    cmd_virt_sparsify = 'virt-sparsify --in-place {path_new_qcow}' \
        .format(path_new_qcow=path_new_qcow)
    cmd_virt_install = 'virt-install --import --dry-run --print-xml --disk {} --memory {} --os-variant {} --name {}' \
        .format(path_new_qcow, memory_in_mb, id_os_virt_install, name_domain_in_xml)

    cmds1.append({'title': 'mkdir dir', 'cmd': 'mkdir -p {}'.format(path_dir)})
    cmds1.append({'title': 'mkdir dir tmp sparsify', 'cmd': 'mkdir -p {}'.format(path_dir_tmp_sparsify)})
    cmds1.append({'title': 'pre-delete touch', 'cmd': 'rm -f {}'.format(touch_test_path)})
    cmds1.append({'title': 'touch', 'cmd': 'touch {}'.format(touch_test_path)})
    cmds1.append({'title': 'readonly_touch', 'cmd': 'chmod a-wx,g+r,u+r {}'.format(touch_test_path)})
    cmds1.append({'title': 'chgrp_touch', 'cmd': 'chgrp {} {}'.format(group_owner, touch_test_path)})
    cmds1.append({'title': 'chown', 'cmd': 'chown {} {}'.format(user_owner, touch_test_path)})
    cmds1.append({'title': 'verify_touch',
                  'cmd': 'stat -c \'mountpoint:%m group:%G user:%U rights:%A\' {}'.format(touch_test_path)})
    cmds1.append({'title': 'df_mountpoint', 'cmd': 'df $(stat -c \'%m\' {})'.format(touch_test_path)})
    cmds1.append({'title': 'rm_touch', 'cmd': 'rm -f {}'.format(touch_test_path)})

    # INFO TO DEVELOPER - todo: launch virt-builder and virt-sparify in other thread to capture output to detail
    cmds1.append({'title': 'launch virt-builder', 'cmd': cmd_virt_builder})
    cmds1.append({'title': 'launch virt-sparsify', 'cmd': cmd_virt_sparsify})

    cmds1.append({'title': 'rmdir tmp sparsify', 'cmd': 'rmdir {}'.format(path_dir_tmp_sparsify)})
    cmds1.append({'title': 'rm big qcow', 'cmd': 'rm -f {}'.format(path_big_disk)})
    cmds1.append({'title': 'test_if_qcow_exists', 'cmd': 'stat -c \'%d\' {}'.format(path_new_qcow)})
    cmds1.append({'title': 'xml from virt-install', 'cmd': cmd_virt_install})

    s = "\n".join([c['cmd'] for c in cmds1])
    print(s)
    return cmds1


def create_cmds_disk_from_base(path_base, path_new, clustersize='4k'):
    # INFO TO DEVELOPER todo: hay que verificar primero si el disco no existe, ya que si no lo machaca creo
    # no se bien cuaqndo hacerlo y si vale la pena, habríamos de manejarlo como una excepción
    # o hacer un stat una vez creado y verificar que devuelve algo

    cmds = list()
    path_dir = extract_dir_path(path_new)
    cmd = 'mkdir -p {}'.format(path_dir)
    cmds.append(cmd)

    cmd = create_disk_from_base_cmd(path_new, path_base, clustersize)
    log.debug('creating disk cmd: {}'.format(cmd))
    cmds.append(cmd)

    # INFO TO DEVELOPER todo: hay que verificar primero si el disco no existe, ya que si no lo machaca creo
    # no se bien cuaqndo hacerlo y si vale la pena

    cmd = backing_chain_cmd(path_new)
    cmds.append(cmd)

    return cmds

def add_cmds_if_custom(id_domain, path_new):
    d = get_custom_dict_from_domain(id_domain)
    pprint(d)

    if d is False or type(d) is not dict:
        return []
    else:
        path_custom_fd = f'{path_new}.custom.fd'
        d['path_custom_fd'] = path_custom_fd
        update_custom_all_dict(id_domain, d)
        d_cmds = create_cmds_custom_fd(path_new,d)
        cmds = [i['cmd'] for i in d_cmds]
        pprint(cmds)
        return cmds

def create_cmds_custom_fd(path_new_disk, d_vars_to_flopy):
    """
    create floppy disk to customize vars, for example: username:test, hostname:remote01
    add two files with filename as key, and bash echo string content as value
    in floppy formated as vfat (ms-dos)
    """
    cmds = list()

    path_dir = extract_dir_path(path_new_disk)
    path_custom_fd = f'{path_new_disk}.custom.fd'
    cmds.append({'title': 'mkdir_domain_disk_dir', 'cmd': f'mkdir -p {path_dir}'})
    cmds.append({'title': 'mknod loop0',
                 'cmd':   'mknod /dev/loop0 b 7 0'})
    cmds.append({'title': 'force detach loop device',
                 'cmd':   'losetup -d /dev/loop0'})
    cmds.append({'title': 'create floppy disk image',
                 'cmd':  f'dd bs=512 count=2880 if=/dev/zero of={path_custom_fd}'})
    cmds.append({'title': 'create floppy disk with custom parameters',
                 'cmd':  f'mkfs.vfat {path_custom_fd}'})
    cmds.append({'title': 'attach floppy to loop device loop0',
                 'cmd':  f'losetup /dev/loop0 {path_custom_fd}'})
    cmds.append({'title': 'force umount /mnt',
                 'cmd':   'umount /mnt'})
    cmds.append({'title': 'mount in /mnt loop0 device',
                 'cmd':   'mount /dev/loop0 /mnt'})

    #adding vars to files
    for k,v in d_vars_to_flopy.items():
        v = shlex.quote(str(v))
        path_filename = shlex.quote('/mnt/' + str(k))
        if k != 'path_custom_fd':
            cmds.append({'title': f'add filename {path_filename} to floppy with value {v}',
                         'cmd': f"echo {v} > {path_filename}"})

        ## OJO HARDCODEADO PARA CTTI PLANTILLA LINKAT
        if str(k) == 'remote_computer':
            log.info(f'PARALINKAT remote_computer: {k}')
            path_filename = '/mnt/hostname'
            cmds.append({'title': f'add filename {path_filename} to floppy with value {v}',
                         'cmd': f"echo {v} > {path_filename}"})

        ## OJO HARDCODEADO PARA CTTI PLANTILLA LINKAT
        if str(k) == 'user':
            log.info(f'PARALINKAT user: {k}')
            path_filename = '/mnt/username'
            cmds.append({'title': f'add filename {path_filename} to floppy with value {v}',
                         'cmd': f"echo {v} > {path_filename}"})

    cmds.append({'title': 'umount mnt',
                 'cmd': 'umount /mnt'})
    cmds.append({'title': 'detach loop0',
                 'cmd': 'losetup -d /dev/loop0'})

    # CODIGO PARA DEBUGAR
    try:
        print('#### commands to floppy')
        for c in cmds:
            print('#' + c['title'])
            print(c['cmd'])
    except Exception as e:
        print(e)

    return cmds


def create_cmds_disk_template_from_domain(path_template_disk, path_domain_disk, user_owner='qemu', group_owner='qemu',
                                          clustersize='4k'):
    # INFO TO DEVELOPER, OJO SI NOS PASAN UN PATH CON ESPACIOS,HABRÍA QUE PONER COMILLAS EN TODOS LOS COMANDOS
    cmds1 = list()
    path_dir_template = extract_dir_path(path_template_disk)
    touch_test_path = path_dir_template + '/.touch_test'

    cmds1.append({'title': 'mkdir_template_dir', 'cmd': 'mkdir -p {}'.format(path_dir_template)})
    cmds1.append({'title': 'pre-delete touch', 'cmd': 'rm -f {}'.format(touch_test_path)})
    cmds1.append({'title': 'touch', 'cmd': 'touch {}'.format(touch_test_path)})
    cmds1.append({'title': 'readonly_touch', 'cmd': 'chmod a-wx,g+r,u+r {}'.format(touch_test_path)})
    cmds1.append({'title': 'chgrp_touch', 'cmd': 'chgrp {} {}'.format(group_owner, touch_test_path)})
    cmds1.append({'title': 'chown', 'cmd': 'chown {} {}'.format(user_owner, touch_test_path)})
    cmds1.append({'title': 'verify_touch',
                  'cmd': 'stat -c \'mountpoint:%m group:%G user:%U rights:%A\' {}'.format(touch_test_path)})
    # with busybox stat -c %m is not an option and fail
    #cmds1.append({'title': 'df_template_mountpoint', 'cmd': 'df $(stat -c \'%m\' {})'.format(touch_test_path)})
    cmds1.append({'title': 'df_template_mountpoint', 'cmd': 'df {}'.format(touch_test_path)})
    cmds1.append({'title': 'size_template_disk', 'cmd': 'stat -c \'%s\' {}'.format(path_domain_disk)})
    cmds1.append({'title': 'rm_touch', 'cmd': 'rm -f {}'.format(touch_test_path)})
    # path_template_disk must be error
    cmds1.append({'title': 'test_if_template_exists', 'cmd': 'stat -c \'%d\' {}'.format(path_template_disk)})
    # compare file system to do mv or rsync with progress
    cmds1.append({'title': 'filesystem_template', 'cmd': 'stat -c \'%d\' {}'.format(path_dir_template)})
    cmds1.append({'title': 'filesystem_domain', 'cmd': 'stat -c \'%d\' {}'.format(path_domain_disk)})

    # #path_template_disk must be error
    # cmds1.append('stat -c \'%d\' {})'.format(path_template_disk))
    # #compare file system to do mv or rsync with progress
    # cmds1.append('fs_template=$(stat -c \'%d\' {})'.format(path_dir_template))
    # cmds1.append('fs_domain=$(stat -c \'%d\' {})'.format(path_domain_disk))
    # cmds1.append('if [ "$fs_template" == "$fs_domain" ]; then echo "equal filesystem"; else echo "disctint filesystem"; fi')


    # then move or rsync and recreate disk_domain with cmds2

    # INFO TO DEVELOPER, HABRÍA QUE VERIFICAR CON UN MD5 QUE NO LA LIA AL HACER LA COPIA Y QUE SON IDÉNTICAS A LA QUE SE HA MOVIDO??

    cmds2 = list()
    # path_domain_disk must be error
    cmds2.append({'title': 'test_if_disk_template_exists', 'cmd': 'stat -c \'%s\' {}'.format(path_template_disk)})
    cmds2.append({'title': 'test_if_disk_domain_exists', 'cmd': 'stat -c \'%s\' {}'.format(path_domain_disk)})

    cmds3 = list()
    cmds3.append({'title': 'create_disk_domain_from_new_template',
                  'cmd': create_disk_from_base_cmd(path_domain_disk, path_template_disk)})
    cmds3.append({'title': 'test_if_disk_domain_exists', 'cmd': 'stat -c \'%s\' {}'.format(path_domain_disk)})
    cmds3.append({'title': 'backing_chain_disk_domain', 'cmd': backing_chain_cmd(path_domain_disk)})
    cmds3.append({'title': 'backing_chain_disk_template', 'cmd': backing_chain_cmd(path_template_disk)})

    return cmds1, cmds2, cmds3


def extract_list_backing_chain(out_cmd_qemu_img, json_format=True):
    out = out_cmd_qemu_img

    if json_format is True:
        if type(out) is not str:
            out = out.decode('utf-8')
        try:
            out = json.loads(out)
        except Exception as e:
            log.info('error reading backing chain, disk is created??')
            log.info(e)
            return []
        return out
    else:
        return backing_chain_parse_list(out)


def verify_output_cmds3(cmds_done, path_domain_disk, path_template_disk, id_domain):
    error = None
    backing_chain_domain = None
    backing_chain_template = None

    d = [a for a in cmds_done if a['title'] == 'create_disk_domain_from_new_template'][0]
    if len(d['err']) > 0:
        log.error('create disk from new template failed. Something was wrong. Error: {}'.format(d['err']))
        log.error('cmd: {}, out: {}, err: {}'.format(d['cmd'], d['out'], d['err']))

        error = 'Hard'

    d = [a for a in cmds_done if a['title'] == 'test_if_disk_domain_exists'][0]
    if len(d['err']) > 0:
        log.error('disk from new template error when stat. Something was wrong. Error: {}'.format(d['err']))
        log.error('cmd: {}, out: {}, err: {}'.format(d['cmd'], d['out'], d['err']))

        error = 'Crashed'

    d = [a for a in cmds_done if a['title'] == 'backing_chain_disk_domain'][0]
    if len(d['err']) > 0 and error != 'Hard':
        log.error(
            'Backing chain query fail in new disk domain {}. Something was wrong. Error: {}'.format(path_domain_disk,
                                                                                                    d['err']))
        log.error('cmd: {}, out: {}, err: {}'.format(d['cmd'], d['out'], d['err']))
        error = 'Crashed'
    elif error is None:
        # REPLACED BY JSON OUT
        # backing_chain_domain = extract_list_backing_chain(d['out'])
        backing_chain_domain = d['out']

    d = [a for a in cmds_done if a['title'] == 'backing_chain_disk_template'][0]
    if len(d['err']) > 0 and error != 'Hard':
        log.error(
            'Backing chain query fail in disk template {}. Something was wrong. Error: {}'.format(path_template_disk,
                                                                                                  d['err']))
        log.error('cmd: {}, out: {}, err: {}'.format(d['cmd'], d['out'], d['err']))
        error = 'Crashed'
    elif error is None:
        # backing_chain_template = extract_list_backing_chain(d['out'])
        backing_chain_template = d['out']

    return error, backing_chain_domain, backing_chain_template


def verify_output_cmds2(cmds_done, path_domain_disk, path_template_disk, id_domain):
    error = None
    d = [a for a in cmds_done if a['title'] == 'test_if_disk_template_exists'][0]
    if len(d['err']) > 0:
        log.error(
            'template disk {} doesn\'t exist??. Something was wrong. Error: {}'.format(path_template_disk, d['err']))
        log.debug('cmd: {}, out: {}, err: {}'.format(d['cmd'], d['out'], d['err']))
        new_template_disk_created = False

        error = 'Hard'
    else:
        new_template_disk_created = True
        file_size_template_disk = int(d['out'])

    d = [a for a in cmds_done if a['title'] == 'test_if_disk_domain_exists'][0]
    if len(d['err']) > 0:
        # domain disk has dissapeared
        if (new_template_disk_created == True):
            log.debug('Domain disk {} has been moved to {}. Ok.'.format(path_domain_disk, path_template_disk))
        else:
            log.error(
                'Where is Domain disk {}? The disk would have moved to {} but it is nowhere!!'.format(path_domain_disk,
                                                                                                      path_template_disk))
            error = 'Crashed'
    else:
        # domain disk remain in place
        file_size_domain_disk = int(d['out'])
        if (new_template_disk_created == True):
            log.error(
                'Domain disk {} would have to be moved, but it is in place. Template disk {} have beeen created, but with all the data??'.format(
                    path_domain_disk, path_template_disk))
            log.error('Domain disk {} Size: {} ({})'.format(path_domain_disk, file_size_domain_disk,
                                                            size_format(file_size_domain_disk)))
            log.error('Template disk {} Size: {} ({})'.format(path_template_disk, file_size_template_disk,
                                                              size_format(file_size_template_disk)))
            error = 'Crashed'
        else:
            log.error(
                'Domain disk {} would have to be moved, but it is in place. Template disk {} not created, but domain disk with all the data??'.format(
                    path_domain_disk, path_template_disk))
            log.error('Domain disk {} Size: {} ({})'.format(path_domain_disk, file_size_domain_disk,
                                                            size_format(file_size_domain_disk)))
            error = 'Hard'

    return error


def verify_output_cmds1_template_from_domain(cmds_done, path_domain_disk, path_template_disk, id_domain):
    move_tool = None
    cmd_to_move = None
    path_dir_template = extract_dir_path(path_template_disk)
    error_severity = None

    d = [a for a in cmds_done if a['title'] == 'filesystem_domain'][0]
    if len(d['err']) > 0:
        log.error(
            'domain disk {} doesn\'t exist or permissions access error. Domain:{}. Error: {}'.format(path_domain_disk,
                                                                                                     id_domain,
                                                                                                     d['err']))
        log.debug('cmd: {}, out: {}, err: {}'.format(d['cmd'], d['out'], d['err']))
        error_severity = 'Hard'
    else:
        fs_domain_code = int(d['out'])

    d = [a for a in cmds_done if a['title'] == 'filesystem_template'][0]
    if len(d['err']) > 0 and error_severity != 'Hard':
        log.error(
            'directory for template disk {} can not be created or permissions access error. Domain:{}. Error: {}'.format(
                path_template_disk, id_domain, d['err']))
        log.debug('cmd: {}, out: {}, err: {}'.format(d['cmd'], d['out'], d['err']))
        error_severity = 'Hard'
    elif error_severity != 'Hard':
        fs_template_code = int(d['out'])
        if fs_template_code == fs_domain_code:
            move_tool = 'mv'
        else:
            move_tool = 'rsync'

    d = [a for a in cmds_done if a['title'] == 'touch'][0]
    if len(d['err']) > 0 and error_severity != 'Hard':
        log.error('When try to write in directory {} fail with error: {} '.format(path_dir_template, d['err']))
        log.debug('cmd: {}, out: {}, err: {}'.format(d['cmd'], d['out'], d['err']))
        error_severity = 'Hard'

    d = [a for a in cmds_done if a['title'] == 'df_template_mountpoint'][0]
    if len(d['err']) > 0 and error_severity != 'Hard':
        log.error('When try to know disk free space previous to create template in template directory, command fail')
        log.debug('cmd: {}, out: {}, err: {}'.format(d['cmd'], d['out'], d['err']))
        error_severity = 'Hard'
    elif error_severity != 'Hard':
        try:
            df_bytes = int(d['out'].splitlines()[-1].split()[3]) * 1024
        except:
            #if mount point is too large df split output in two lines
            try:
                df_bytes = int(d['out'].splitlines()[-1].split()[2]) * 1024
            except:
                log.info('When try to know disk free space previous to create template output is not standard')
                log.debug('cmd: {}, out: {}, err: {}'.format(d['cmd'], d['out'], d['err']))
                df_bytes = 999999999
        log.debug('disk free for create template from domain {}: {}'.format(id_domain, size_format(df_bytes)))

    d = [a for a in cmds_done if a['title'] == 'size_template_disk'][0]
    if len(d['err']) > 0 and error_severity != 'Hard':
        log.error('When try to access domain file disk {} fail with error: {} '.format(path_domain_disk, d['err']))
        log.debug('cmd: {}, out: {}, err: {}'.format(d['cmd'], d['out'], d['err']))
        error_severity = 'Hard'
    elif error_severity != 'Hard':
        disk_size_bytes = int(d['out'])
        log.debug('disk {} size: {} , template filesystem df: {}'.format(path_domain_disk, size_format(disk_size_bytes),
                                                                         size_format(df_bytes)))
        if disk_size_bytes >= df_bytes:
            log.error('Not enough free space to create template from {}'.format(id_domain))
            log.debug('cmd: {}, out: {}, err: {}'.format(d['cmd'], d['out'], d['err']))
            error_severity = 'Hard'

    d = [a for a in cmds_done if a['title'] == 'test_if_template_exists'][0]
    if len(d['err']) == 0:
        log.error('File template that must be created and it exists!! File path: {}'.format(path_template_disk))
        log.debug('cmd: {}, out: {}, err: {}'.format(d['cmd'], d['out'], d['err']))
        error_severity = 'Hard'

    d = [a for a in cmds_done if a['title'] == 'verify_touch'][0]
    if len(d['err']) > 0 and error_severity != 'Hard':
        if d['out'].find('rights:-r--r--r--') > 0:
            log.debug('change rights readonly test passed for create template from domain {}'.format(id_domain))
            log.debug('cmd: {}, out: {}, err: {}'.format(d['cmd'], d['out'], d['err']))
        else:
            log.error('PROBLEM change rights readonly test passed for create template from domain {}'.format(id_domain))
            log.error('cmd: {}, out: {}, err: {}'.format(d['cmd'], d['out'], d['err']))
            error_severity = 'Soft'
            # INFO TO DEVELOPER, DE MOMENTO NO MIRAMOS SI EL PROPIETARIO Y GRUPO ES qemu, si se cree importante aquí habría que implementarlo

    if error_severity == None and move_tool != None:
        if move_tool == 'mv':
            cmd_to_move = 'mv {} {}'.format(path_domain_disk, path_template_disk)
        if move_tool == 'rsync':
            # cmd_to_move = 'rsync -aP --remove-source-files "{}" "{}"'.format(path_domain_disk,path_template_disk)
            cmd_to_move = 'rsync -aP --inplace --remove-source-files "{}" "{}"'.format(path_domain_disk,
                                                                                                       path_template_disk)

    return error_severity, move_tool, cmd_to_move


def create_disk_from_base_cmd(filename, basename, clustersize='4k'):
    cmd = 'qemu-img create -f qcow2 -o cluster_size={clustersize} -b \"{basename}\" -F qcow2 \"{filename}\"'
    cmd = cmd.format(filename=filename, basename=basename, clustersize=clustersize)
    return cmd


def backing_chain_parse_list(out_cmd):
    l = [t.split('\n')[0] for t in out_cmd.split('image: ')[1:]]
    return l


def backing_chain(path_disk, disk_operations_hostname, json_format=True):
    '''
    return list of backing chain: list[0] is the most newer,
    and list[-1] the last qcow in backing chain
    '''
    cmd = backing_chain_cmd(path_disk)

    d = exec_remote_cmd(cmd, disk_operations_hostname)
    if len(d['err']) == 0:
        output = extract_list_backing_chain(d['out'], json_format=json_format)
        if len(output) == 0:
            log.info(
                'backing_chain info for disk {} fail when executing in host {} and command is {}'.format(path_disk,
                                                                                                         VDESKTOP_DISK_OPERATINOS,
                                                                                                         cmd))
        return output
    else:
        log.error('backing_chain info for disk {} fail when executing in host {} and command is {}'.format(path_disk,
                                                                                                           VDESKTOP_DISK_OPERATINOS,
                                                                                                           cmd))


def get_path_to_disk(relative_path, pool='default', type_path='groups'):
    pool_paths = get_pool(pool)['paths']
    paths_for_type = pool_paths[type_path]
    list_paths_with_weights = [{'w': v['weight'], 'k': v['path']} for v in paths_for_type]
    weights = [v['w'] for v in list_paths_with_weights]
    index_list_path_selected = weighted_choice(weights)
    path_selected = list_paths_with_weights[index_list_path_selected]['k']
    path_absolute = path_selected + '/' + relative_path
    return path_absolute, path_selected


def get_host_long_operations_from_path(path_selected, pool='default', type_path='groups'):
    l_threads = get_threads_names_running()
    pool_paths = get_pool(pool)['paths']
    paths_for_type = pool_paths[type_path]
    hyps = [v['disk_operations'] for v in paths_for_type if v['path'] == path_selected][0]
    # TODO must be revised to return random or less cpuload hypervisor
    for h in hyps:
        if 'long_op_' + h in l_threads:
            return h

    log.error('There are not hypervisors with disk_operations thread for path {}'.format(path_selected))
    return False


def get_host_disk_operations_from_path(path_selected, pool='default', type_path='groups'):
    l_threads = get_threads_names_running()
    d_pool = get_pool(pool)
    pool_paths = d_pool['paths']
    paths_for_type = pool_paths[type_path]
    #TODO must find by weight
    pprint(d_pool)
    print('path_selected:')
    pprint(path_selected)

    if 'round_robin_indexes' in d_pool.keys():
        round_robin_index = d_pool['round_robin_indexes'].get(type_path,0)
    else:
        round_robin_index = 0

    print(f'round robin index from pool: {round_robin_index}')

    try:
        hyps = [v['disk_operations'] for v in paths_for_type if v['path'] == path_selected][0]
        print(f'hypervisores para disk-operations en path {path_selected}, type_path {type_path}')
        pprint(l_threads)
        pprint(hyps)
    except IndexError:
        log.error('no disk operations hypervisors for path {} in pool {} with type_path {}'.format(path_selected,pool,type_path))
        return False
    # TODO must be revised to return random or less cpuload hypervisor

    # select hypers for this path and if they are running
    d_threads_h = {'disk_op_' + h: h for h in hyps}
    hyps_candidate =  sorted([d_threads_h[k] for k in set(l_threads).intersection(set(d_threads_h.keys()))])

    if len(hyps_candidate) == 0:
        log.error('There are not hypervisors with disk_operations thread for path {}'.format(path_selected))
        return False

    print('##HYPS CANDIDATE')
    pprint(hyps_candidate)
    if round_robin_index >= len(hyps_candidate):
        round_robin_index = 0

    if (round_robin_index + 1) >= len(hyps_candidate):
        round_robin_next = 0
    else:
        round_robin_next = round_robin_index + 1
    print(f'#ROUND ROBIN INDEX: {round_robin_index}')
    print(f'#ROUND ROBIN NEXT: {round_robin_next}')

    update_pool_round_robin(type_path=type_path,
                            round_robin_index=round_robin_next)

    print(f'round_robin: {round_robin_index}, type_path: {type_path} ,hyp_selected: ' + hyps_candidate[round_robin_index])

    return hyps_candidate[round_robin_index]
    # for h in hyps:
    #     #print('------------------- hyp selected')
    #     #print(h)
    #     if 'disk_op_' + h in l_threads:
    #         return h
    




def get_host_and_path_diskoperations_to_write_in_path(type_path, relative_path, pool='default'):
    if type_path not in ['bases', 'groups', 'templates']:
        log.error('type disk operations must be bases, groups or templates')
        return False
    pool_paths = get_pool(pool)['paths']
    paths_for_type = pool_paths[type_path]
    list_paths_with_weights = [{'w': v['weight'], 'k': k} for k, v in paths_for_type.items()]
    weights = [v['w'] for v in list_paths_with_weights]
    index_list_path_selected = weighted_choice(weights)
    path_selected = list_paths_with_weights[index_list_path_selected]['k']
    host_disk_operations_selected = False
    for h in paths_for_type[path_selected]['disk_operations']:
        if ('disk_op_' + h) in get_threads_names_running():
            host_disk_operations_selected = h
            log.debug('host {} selected in pool {}, type_path: {}, path: {}'.format(
                host_disk_operations_selected,
                pool,
                type_path,
                path_selected))
            break
    if host_disk_operations_selected is False:
        log.error('no host with thread for disk_operations in pool {}, type_path: {}, path: {}'.format(
            pool,
            type_path,
            path_selected))
        return False
    else:
        path_absolute = path_selected + '/' + relative_path
        return host_disk_operations_selected, path_absolute

def test_hypers_disk_operations(hyps_disk_operations):
    list_hyps_ok = list()
    str_random = ''.join(choices(string.ascii_uppercase + string.digits, k=8))
    for hyp_id in hyps_disk_operations:
        d_hyp = get_hyp_hostname_user_port_from_id(hyp_id)
        cmds1 = list()
        for pool_id in get_pools_from_hyp(hyp_id):
            # test write permissions in root dir of all paths defined in pool
            paths = {k: [l['path'] for l in d] for k, d in get_pool(pool_id)['paths'].items()}
            for k, p in paths.items():
                for path in p:
                    cmds1.append({'title': f'try create dir if not exists - pool:{pool_id}, hypervisor: {hyp_id}, path_kind: {k}',
                                  'cmd': f'mkdir -p {path}'})
                    cmds1.append({'title': f'touch random file - pool:{pool_id}, hypervisor: {hyp_id}, path_kind: {k}',
                                  'cmd': f'touch {path}/test_random_{str_random}'})
                    cmds1.append({'title': 'delete random file - pool:{pool_id}, hypervisor: {hyp_id}, path_kind: {k}',
                                  'cmd': f'rm -f {path}/test_random_{str_random}'})
        try:
            array_out_err = execute_commands(d_hyp['hostname'],
                                             ssh_commands=cmds1,
                                             dict_mode=True,
                                             user=d_hyp['user'],
                                             port=d_hyp['port'])
            #if error in some path hypervisor is not valid
            if len([d['err'] for d in array_out_err if len(d['err']) > 0]) > 0:
                logs.main.error(f'Hypervisor {hyp_id} can not be disk_operations, some errors when testing if can create files in all paths_')
                for d_cmd_err  in [d for d in array_out_err if len(d['err']) > 0]:
                    cmd = d_cmd_err['cmd']
                    err = d_cmd_err['err']
                    logs.main.error(f'Command: {cmd} --  Error: {err}')
            else:
                list_hyps_ok.append(hyp_id)

        except Exception as e:
            if __name__ == '__main__':
                logs.main.err(f'Error when launch commands to test hypervisor {hyp_id} disk_operations: {e}')

    return list_hyps_ok



