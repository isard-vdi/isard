# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

# Manage domain's xml

# coding=utf-8

# TODO: INFO TO DEVELOPER revisar si hacen falta todas estas librerías para este módulo

import random
import string
import traceback
import uuid
from io import StringIO
from pprint import pprint

from lxml import etree

from engine.services.db import get_dict_from_item_in_table, update_table_field, update_domain_dict_hardware
from engine.services.db import get_interface, get_domain, update_domain_viewer_started_values, get_graphics_types
from engine.services.db.downloads import get_media
from engine.services.lib.functions import randomMAC
from engine.services.log import *

DEFAULT_SPICE_VIDEO_COMPRESSION = 'auto_glz'

CPU_MODEL_FALLBACK = 'core2duo'

DEFAULT_BALLOON = 0.80

BUS_TYPES =  ['sata', 'ide', 'virtio']

BUS_LETTER = {'ide':'h','sata':'s','virtio':'v'}

XML_SNIPPET_NETWORK = '''
    <interface type="network">
      <source network="default"/>
      <mac address="xx:xx:xx:xx:xx:xx"/>
      <model type="virtio"/>
    </interface>
'''

XML_SNIPPET_BRIDGE = '''
    <interface type='bridge'>
      <source bridge='n2m-bridge'/>
      <mac address='52:54:00:eb:b1:aa'/>
      <model type='virtio'/>
    </interface>
'''

XML_SNIPPET_CDROM = '''
    <disk type="file" device="cdrom">
      <driver name="qemu" type="raw"/>
      <source file="{path_cdrom}"/>
      <target dev="hd{suffix_descriptor}" bus="ide"/>
      <readonly/>
    </disk>
'''

XML_SNIPPET_DISK_VIRTIO = '''
    <disk type="file" device="disk">
      <driver name="qemu" type="qcow2"/>
      <source file="/path/to/disk.qcow"/>
      <target dev="vd{}" bus="virtio"/>
    </disk>
'''

XML_SNIPPET_DISK_CUSTOM = '''
    <disk type="file" device="disk">
      <driver name="qemu" type="{type_disk}"/>
      <source file="{path_disk}"/>
      <target dev="{preffix_descriptor}d{suffix_descriptor}" bus="{bus}"/>
    </disk>
'''

CPU_MODEL_NAMES = ['486',
 'pentium',
 'pentium2',
 'pentium3',
 'pentiumpro',
 'coreduo',
 'n270',
 'core2duo',
 'qemu32',
 'kvm32',
 'cpu64-rhel5',
 'cpu64-rhel6',
 'kvm64',
 'qemu64',
 'Conroe',
 'Penryn',
 'Nehalem',
 'Nehalem-IBRS',
 'Westmere',
 'Westmere-IBRS',
 'SandyBridge',
 'SandyBridge-IBRS',
 'IvyBridge',
 'IvyBridge-IBRS',
 'Haswell-noTSX',
 'Haswell-noTSX-IBRS',
 'Haswell',
 'Haswell-IBRS',
 'Broadwell-noTSX',
 'Broadwell-noTSX-IBRS',
 'Broadwell',
 'Broadwell-IBRS',
 'Skylake-Client',
 'Skylake-Client-IBRS',
 'Skylake-Server',
 'Skylake-Server-IBRS',
 'athlon',
 'phenom',
 'Opteron_G1',
 'Opteron_G2',
 'Opteron_G3',
 'Opteron_G4',
 'Opteron_G5',
 'EPYC',
 'EPYC-IBPB']


index_to_char_suffix_disks = 'a,b,c,d,e,f,g,h,i,j,k,l,m,n'.split(',')

class DomainXML(object):
    def __init__(self, xml):
        # self.tree = etree.parse(StringIO(xml))

        parser = etree.XMLParser(remove_blank_text=True)
        try:
            self.tree = etree.parse(StringIO(xml), parser)
            self.parser = True
        except Exception as e:
            log.error('Exception when parse xml: {}'.format(e))
            log.error('xml that fail: \n{}'.format(xml))
            log.error('Traceback: {}'.format(traceback.format_exc()))
            self.parser = False
            return None

        self.vm_dict = self.dict_from_xml(self.tree)

        self.index_disks = {}
        self.index_disks['virtio'] = 0
        self.index_disks['ide'] = 0
        self.index_disks['sata'] = 0
        self.d_graphics_types = None

    # def update_xml(self,**kwargs):
    #     if kwargs.__contains__('vcpus'):
    #         log.debug(1.)

    def new_domain_uuid(self):
        'Create new uuid from random function uuid.uuid4() '
        new_uuid = str(uuid.uuid4())
        self.tree.xpath('/domain/uuid')[0].text = new_uuid
        return new_uuid

    def new_random_mac(self):
        new_mac = randomMAC()
        self.reset_mac_address(mac=new_mac)
        return new_mac

    def reset_mac_address(self, dev_index=0, mac=None):
        '''delete the mac address from xml. In the next boot libvirt create a random mac
         If you want to fix mac address mac parameter is optional.
         If there are more than one network device, the dev_index indicates the network device position
         in the xml definition. dev_index = 0 is the first network interface defined in xml.'''

        if mac is None:
            mac = randomMAC()

        self.tree.xpath('/domain/devices/interface')[dev_index].xpath('mac')[dev_index].set('address', mac)

    def dict_from_xml(self, xml_tree=False):
        ## TODO INFO TO DEVELOPER: hay que montar excepciones porque si no el xml peta
        ## cuando no existe un atributo
        vm_dict = {}
        if xml_tree is False:
            xml_tree = self.tree

        if xml_tree.xpath('/domain/devices/graphics'):
            element_graphics = xml_tree.xpath('/domain/devices/graphics')[0]

            if 'type' in self.tree.xpath('/domain/devices/graphics')[0].keys():
                type = self.tree.xpath('/domain/devices/graphics')[0].get('type')
            else:
                type = None

            if 'defaultMode' in self.tree.xpath('/domain/devices/graphics')[0].keys():
                defaultMode = self.tree.xpath('/domain/devices/graphics')[0].get('defaultMode')
            else:
                defaultMode = None

            vm_dict['graphics'] = {}
            vm_dict['graphics']['type'] = type
            vm_dict['graphics']['defaultMode'] = defaultMode

        # if 'passwd' in self.tree.xpath('/domain/devices/graphics')[0].keys():
        #     if 'viewer' not in vm_dict.keys():
        #         vm_dict['viewer'] = {}
        #     vm_dict['viewer']['passwd'] = self.tree.xpath('/domain/devices/graphics')[0].get('passwd')

        if xml_tree.xpath('/domain/name'):
            vm_dict['name'] = xml_tree.xpath('/domain/name')[0].text

        if xml_tree.xpath('/domain/uuid'):
            vm_dict['uuid'] = xml_tree.xpath('/domain/uuid')[0].text

        if xml_tree.xpath('/domain/os/type'):
            if xml_tree.xpath('/domain/os/type')[0].get('machine'):
                vm_dict['machine'] = xml_tree.xpath('/domain/os/type')[0].get('machine')

        if xml_tree.xpath('/domain/memory'):
            vm_dict['memory'] = int(xml_tree.xpath('/domain/memory')[0].text)
            vm_dict['memory_unit'] = xml_tree.xpath('/domain/memory')[0].get('unit') \
                if xml_tree.xpath('/domain/memory')[0].get('unit') is None else 'KiB'

        if xml_tree.xpath('/domain/currentMemory'):
            vm_dict['currentMemory'] = int(xml_tree.xpath('/domain/currentMemory')[0].text)
            vm_dict['currentMemory_unit'] = xml_tree.xpath('/domain/currentMemory')[0].get('unit') \
                if xml_tree.xpath('/domain/currentMemory')[0].get('unit') is None else 'KiB'

        if xml_tree.xpath('/domain/maxMemory'):
            vm_dict['maxMemory'] = xml_tree.xpath('/domain/maxMemory')[0].text
            vm_dict['maxMemory_unit'] = xml_tree.xpath('/domain/maxMemory')[0].get('unit') \
                if xml_tree.xpath('/domain/maxMemory')[0].get('unit') is None else 'KiB'

        if xml_tree.xpath('/domain/vcpu'):
            vm_dict['vcpus'] = int(xml_tree.xpath('/domain/vcpu')[0].text)

        if xml_tree.xpath('/domain/devices/video/model'):
            vm_dict['video'] = {}
            for key in ('type', 'ram', 'vram', 'vgamem', 'heads'):
                if key in self.tree.xpath('/domain/devices/video/model')[0].keys():
                    vm_dict['video'][key] = xml_tree.xpath('/domain/devices/video/model')[0].get(key)

        if xml_tree.xpath('/domain/devices/disk[@device="disk"]'):
            vm_dict['disks'] = list()
            for tree in xml_tree.xpath('/domain/devices/disk[@device="disk"]'):
                list_dict = {}
                list_dict['type'] = tree.xpath('driver')[0].get('type')
                list_dict['file'] = tree.xpath('source')[0].get('file')
                list_dict['dev'] = tree.xpath('target')[0].get('dev')
                list_dict['bus'] = tree.xpath('target')[0].get('bus')
                vm_dict['disks'].append(list_dict)


        if xml_tree.xpath('/domain/devices/disk[@device="floppy"]'):
            vm_dict['floppies'] = list()
            for tree in xml_tree.xpath('/domain/devices/disk[@device="floppy"]'):
                list_dict = {}
                # list_dict['type'] = tree.xpath('driver')[0].get('type')
                if len(tree.xpath('source')) != 0:
                    list_dict['file'] = tree.xpath('source')[0].get('file')
                list_dict['dev'] = tree.xpath('target')[0].get('dev')
                # list_dict['bus'] = tree.xpath('target')[0].get('bus')
                vm_dict['floppies'].append(list_dict)


        if xml_tree.xpath('/domain/devices/disk[@device="cdrom"]'):
            vm_dict['cdroms'] = list()
            for tree in xml_tree.xpath('/domain/devices/disk[@device="cdrom"]'):
                list_dict = {}
                # list_dict['type'] = tree.xpath('driver')[0].get('type')
                if len(tree.xpath('source')) != 0:
                    list_dict['file'] = tree.xpath('source')[0].get('file')
                list_dict['dev'] = tree.xpath('target')[0].get('dev')
                # list_dict['bus'] = tree.xpath('target')[0].get('bus')
                vm_dict['cdroms'].append(list_dict)

        if xml_tree.xpath('/domain/devices/interface'):
            vm_dict['interfaces'] = list()
            for tree in xml_tree.xpath('/domain/devices/interface'):
                list_dict = {}

                list_dict['type'] = tree.get('type')

                if tree.xpath('mac'):
                    list_dict['mac'] = tree.xpath('mac')[0].get('address')

                if list_dict['type'] == 'network' and tree.xpath('source'):
                    list_dict['id'] = tree.xpath('source')[0].get('network')

                if list_dict['type'] == 'bridge' and tree.xpath('source'):
                    list_dict['id'] = tree.xpath('source')[0].get('bridge')

                if tree.xpath('model'):
                    list_dict['model'] = tree.xpath('model')[0].get('type')

                vm_dict['interfaces'].append(list_dict)

        vm_dict['boot_order'] = [x.get('dev') for x in tree.xpath('/domain/os/boot[@dev]')]
        vm_dict['boot_menu_enable'] = [x.get('dev') for x in tree.xpath('/domain/os/bootmenu[@enable]')]



        ## OJO!!!!!!!!!!!!!!

        # EN SPICE SIEMPRE TIENE QUE ESTAR autoport='yes' listen='0.0.0.0'

        # CUANDO ESTÁ CORRIENDO APARECE EL PUERTO, PASSWORD
        # GENERAR EL PASSWORD ALEATORIAMENTE Y PASÁRSELO
        # Y OJO PORQUE HAY QUE CAMBIARLO A TLS Y GENERAR TICKETS
        # ESTÁ EN IMAGINARI
        self.vm_dict = vm_dict

        return vm_dict

    def set_description(self, description):
        if self.tree.xpath('/domain/description'):
            self.tree.xpath('/domain/description')[0].text = description

        else:
            element = etree.parse(StringIO('<description>{}</description>'.format(description))).getroot()

            if self.tree.xpath('/domain/title'):
                self.tree.xpath('/domain/title')[0].addnext(element)
            else:
                if self.tree.xpath('/domain/name'):
                    self.tree.xpath('/domain/name')[0].addnext(element)

    def set_title(self, title):
        if self.tree.xpath('/domain/title'):
            self.tree.xpath('/domain/title')[0].text = title

        else:
            element = etree.parse(StringIO('<title>{}</title>'.format(title))).getroot()

            if self.tree.xpath('/domain/name'):
                self.tree.xpath('/domain/name')[0].addnext(element)

    def set_memory(self, memory, unit='KiB', current=-1, max=-1):

        if self.tree.xpath('/domain/memory'):
            self.tree.xpath('/domain/memory')[0].set('unit', unit)
            self.tree.xpath('/domain/memory')[0].text = str(memory)
        else:
            element = etree.parse(StringIO('<memory unit=\'{}\'>{}</memory>'.format(unit, memory)))
            self.tree.xpath('/domain/name')[0].addnext(element)

#        if current > 0:
#            if self.tree.xpath('/domain/currentMemory'):
#                self.tree.xpath('/domain/currentMemory')[0].set('unit', unit)
#                self.tree.xpath('/domain/currentMemory')[0].text = str(current)
#            else:
#                element = etree.parse(StringIO('<currentMemory unit=\'{}\'>{}</currentMemory>'.format(unit, current)))
#                self.tree.xpath('/domain/memory')[0].addnext(element)
#
#        else:
#            if self.tree.xpath('/domain/currentMemory'):
#                self.remove_branch('/domain/currentMemory')

        if max > 0:
            if self.tree.xpath('/domain/maxMemory'):
                self.tree.xpath('/domain/maxMemory')[0].set('unit', unit)
                self.tree.xpath('/domain/maxMemory')[0].text = str(max)
            else:
                element = etree.parse(StringIO('<maxMemory unit=\'{}\'>{}</maxMemory>'.format(unit, max)))
                self.tree.xpath('/domain/maxMemory')[0].addnext(element)

        else:
            if self.tree.xpath('/domain/maxMemory'):
                self.remove_branch('/domain/maxMemory')

    def set_vcpu(self, vcpus, placement='static'):

        # example from libvirt.org  <vcpu placement='static' cpuset="1-4,^3,6" current="1">2</vcpu>
        if self.tree.xpath('/domain/vcpu'):
            # self.tree.xpath('/domain/vcpu')[0].attrib.pop('placement')
            self.tree.xpath('/domain/vcpu')[0].set('placement', placement)
            self.tree.xpath('/domain/vcpu')[0].text = str(vcpus)
        else:
            element = etree.parse(StringIO('<vcpu placement=\'{}\'>{}</vcpu>'.format(placement, vcpus))).getroot()
            self.tree.xpath('/domain/name')[0].addnext(element)

    def add_to_domain(self, xpath_same, element_tree, xpath_next='', xpath_previous='', xpath_parent='/domain'):
        if self.tree.xpath(xpath_parent):
            if self.tree.xpath(xpath_same):
                self.tree.xpath(xpath_same)[-1].addnext(element_tree)

            elif xpath_next and self.tree.xpath(xpath_next):
                self.tree.xpath(xpath_next)[0].addprevious(element_tree)

            elif xpath_previous and self.tree.xpath(xpath_previous):
                self.tree.xpath(xpath_previous)[-1].addnext(element_tree)

            else:
                self.tree.xpath(xpath_parent)[0].insert(1, element_tree)

        else:
            log.debug('element {} not found in xml_tree when adding to the domain'.format(xpath_parent))

    def add_device(self, xpath_same, element_tree, xpath_next='', xpath_previous=''):
        # mejor añadir a la vez cds y discos para verificar que no hay lio con los hda, hdb...

        if not self.add_to_domain(xpath_same, element_tree, xpath_next, xpath_previous, '/domain/devices'):
            return False

    def add_disk(self,index=0,path_disk='/path/to/disk.qcow',type_disk='qcow2',bus='virtio'):
        global index_to_char_suffix_disks

        prefix = BUS_LETTER[bus]
        index_bus = self.index_disks[bus]
        xml_snippet = XML_SNIPPET_DISK_CUSTOM.format(type_disk=type_disk,
                                                     path_disk=path_disk,
                                                     preffix_descriptor=prefix,
                                                     suffix_descriptor=index_to_char_suffix_disks[index_bus],
                                                     bus=bus)
        disk_etree = etree.parse(StringIO(xml_snippet))
        new_disk = disk_etree.xpath('/disk')[0]
        xpath_same = '/domain/devices/disk[@device="disk"]'
        xpath_next = '/domain/devices/disk[@device="cdrom"]'
        xpath_previous = '/domain/devices/emulator'
        self.add_device(xpath_same, new_disk, xpath_next=xpath_next, xpath_previous=xpath_previous)
        self.index_disks[bus] += 1


    def add_cdrom(self,index=0,path_cdrom='/path/to/cdrom'):
        global index_to_char_suffix_disks
        #default bus ide

        index_bus = self.index_disks['ide']
        xml_snippet = XML_SNIPPET_CDROM.format(suffix_descriptor=index_to_char_suffix_disks[index_bus],
                                               path_cdrom=path_cdrom)
        disk_etree = etree.parse(StringIO(xml_snippet))
        new_disk = disk_etree.xpath('/disk')[0]
        xpath_same = '/domain/devices/disk[@device="cdrom"]'
        xpath_previous = '/domain/devices/disk[@device="disk"]'
        xpath_next = '/domain/devices/controller'
        self.add_device(xpath_same, new_disk, xpath_next=xpath_next, xpath_previous=xpath_previous)
        self.index_disks['ide'] += 1

    def add_interface(self, type, id, mac=None, model_type='virtio'):
        '''
        :param type:' bridge' OR 'network' .
                     If bridge inserts xml code for bridge,
                     If network insert xml code for virtual network
        :return:
        '''
        if mac is None:
            mac = randomMAC()

        if type == 'bridge':
            interface_etree = etree.parse(StringIO(XML_SNIPPET_BRIDGE))
            interface_etree.xpath('/interface')[0].xpath('source')[0].set('bridge', id)

        elif type == 'network':
            interface_etree = etree.parse(StringIO(XML_SNIPPET_NETWORK))
            interface_etree.xpath('/interface')[0].xpath('source')[0].set('network', id)

        else:
            log.error('type of interface incorrect when adding interface in xml')
            return -1

        interface_etree.xpath('/interface')[0].xpath('mac')[0].set('address', mac)
        interface_etree.xpath('/interface')[0].xpath('model')[0].set('type', model_type)

        new_interface = interface_etree.xpath('/interface')[0]

        xpath_same = '/domain/devices/interface'
        xpath_next = '/domain/devices/input'
        xpath_previous = '/domain/devices/controller'

        self.add_device(xpath_same, new_interface, xpath_next=xpath_next, xpath_previous=xpath_previous)

    def reset_interface(self, type, id, mac=None, model_type='virtio'):
        '''
        :param type:' bridge' OR 'network' .
                     If bridge inserts xml code for bridge,
                     If network insert xml code for virtual network
        :return:
        '''
        xpath = '/domain/devices/interface'

        while len(self.tree.xpath(xpath)):
            self.remove_branch(xpath)

        self.add_interface(type, id, mac, model_type)

    def reset_viewer_passwd(self, ssl=True):
        passwd = ''.join([random.choice(string.ascii_letters + string.digits) for n in range(16)])
        self.set_viewer_passwd(passwd, ssl)

    def set_cpu_host_model(self, cpu_host_model='host-model'):
        """update cpu host_model from xml original in domain,
        by default cpu_host_model is host-model (see libvirt xml help)
        cpu_host_mode: not-change, custom, host-model, host-passthrough"""

        if cpu_host_model == 'not-change':
            return False


        fallback = etree.parse(StringIO("<model fallback='allow'>{}</model>".format(CPU_MODEL_FALLBACK))).getroot()

        if cpu_host_model == 'host-model' or cpu_host_model is False:
            #cpu = etree.Element('cpu', mode='host-model', check='partial')
            #cpu.append(etree.Element('model', fallback='allow'))

            #cpu = etree.parse(StringIO("<cpu mode='host-model' check='partial'>").getroot()
            cpu = etree.parse(StringIO("<cpu mode='host-model' > </cpu>")).getroot()
            cpu.append(fallback)

        elif cpu_host_model == 'host-passthrough':
            cpu = etree.parse(StringIO("<cpu mode='{}' > </cpu>".format(cpu_host_model))).getroot()
            cpu.append(fallback)

        elif cpu_host_model in CPU_MODEL_NAMES:
            exact_cpu = etree.parse(StringIO("<model>{}</model>".format(cpu_host_model))).getroot()
            cpu = etree.parse(StringIO("<cpu mode='custom' > </cpu>")).getroot()
            cpu.append(exact_cpu)

        else:
            log.error('cpu_host_model not supported, cpu section not modified: ' + cpu_host_model)
            return False

        #delete old cpu section
        domain = self.tree.xpath('/domain')[0]

        cpu_old = domain.xpath('cpu')
        if len(cpu_old) == 1:
            domain.remove(cpu_old[0])

        #insert new cpu section
        xpath_same = '/domain/cpu'
        xpath_previous = '/domain/features'
        xpath_next = '/domain/clock'
        self.add_to_domain(xpath_same, cpu, xpath_next, xpath_previous)

    def set_video_type(self, type_video):
        self.tree.xpath('/domain/devices/video/model')[0].set('type', type_video)

    def add_vlc_with_websockets(self):
        xpath_same = '/domain/devices/graphics'
        xpath_previous = '/domain/devices/interface'
        xpath_next = '/domain/devices/video'
        passwd = self.viewer_passwd

        xpath_vlc = '/domain/devices/graphics[@type="vnc"]'

        #remove if exist vlc
        if self.tree.xpath('/domain/devices'):
            if self.tree.xpath(xpath_vlc):
                self.tree.xpath(xpath_vlc)[0].getparent().remove(self.tree.xpath(xpath_vlc)[0])
        else:
            log.debug('element /domain/devices not found in xml_etree when adding disk')
            return False

        #vlc_string_xml = "<graphics type='vnc' port=auto autoport='no' websocket='-1' listen='0.0.0.0'>. <listen type='address' address='0.0.0.0'/>"

        vlc_string_xml  = f"    <graphics type='vnc' passwd='{passwd}' autoport='yes' websocket='-1' listen='0.0.0.0' > \n" + \
                           "        <listen type='address' address='0.0.0.0'/> \n" + \
                           "    </graphics>"
        vlc = etree.parse(StringIO(vlc_string_xml)).getroot()
        self.add_to_domain(xpath_same, vlc, xpath_next, xpath_previous)

    def set_spice_video_options(self,id_graphics='default'):
        xpath_spice = '/domain/devices/graphics[@type="spice"]'

        self.d_graphics_types = get_graphics_types(id_graphics)

        if self.d_graphics_types is None:
            d_spice_options = {
                'image': {'compression': 'auto_glz'},
                'jpeg': {'compression': 'always'},
                'playback': {'compression': 'off'},
                'streaming': {'mode': 'all'},
                'zlib': {'compression': 'always'},
            }
        else:
            d_spice_options = self.d_graphics_types['spice']['options']

        # add spice graphics if not exists
        if not self.tree.xpath(xpath_spice):
            self.add_spice_graphics_if_not_exist()

        # remove all options in spice
        tree_spice = self.tree.xpath(xpath_spice)[0]
        for i in tree_spice.getchildren():
            tree_spice.remove(i)

        # add all options in spice
        for p,v in d_spice_options.items():
            element = etree.Element(p, **v)
            tree_spice.insert(-1,element)

    def add_spice_graphics_if_not_exist(self,video_compression=None):
        xpath_spice = '/domain/devices/graphics[@type="spice"]'

        if not self.tree.xpath(xpath_spice):
            xpath_same = '/domain/devices/graphics'
            xpath_previous = '/domain/devices/interface'
            xpath_next = '/domain/devices/video'

            if video_compression is None:
                video_compression = DEFAULT_SPICE_VIDEO_COMPRESSION

            string_xml = '    <graphics type="spice" port="-1" tlsPort="-1" autoport="yes">\n' + \
                         f'        <image compression="{video_compression}"/>\n' + \
                         '    </graphics>'

            spice_graphics = etree.parse(StringIO(string_xml)).getroot()
            self.add_to_domain(xpath_same, spice_graphics, xpath_next, xpath_previous)

    def set_viewer_passwd(self, passwd, ssl=True):
        # if self.tree.xpath('/domain/devices/graphics')[0].get('type') == 'spice':
        if 'password' in self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].keys():
            self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].attrib.pop('password')
        self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].set('passwd', passwd)
        self.viewer_passwd = passwd
        if ssl is True:
            # mode secure if you not use websockets
            # self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].set('defaultMode','secure')
            # defaultMode=any is the default value, if you pop defaultMode attrib is the same
            self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].set('defaultMode', 'any')
        else:
            if 'defaultMode' in self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].keys():
                self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].attrib.pop('defaultMode')
                # else:
                #     log.error('domain {} has not spice graphics and can not change password of spice connection'.format(self.vm_dict['name']))

    def remove_disk(self, order=-1):
        xpath = '/domain/devices/disk[@device="disk"]'
        self.remove_device(xpath, order_num=order)

    def remove_cdrom(self, order=-1):
        xpath = '/domain/devices/disk[@device="cdrom"]'
        self.remove_device(xpath, order_num=order)

    def remove_floppy(self, order=-1):
        xpath = '/domain/devices/disk[@device="floppy"]'
        self.remove_device(xpath, order_num=order)

    def remove_interface(self, order=-1):
        xpath = '/domain/devices/interface'
        self.remove_device(xpath, order_num=order)


    def remove_device(self, xpath, order_num=-1):
        if self.tree.xpath('/domain/devices'):
            if self.tree.xpath(xpath):
                l = len(self.tree.xpath(xpath))
                if order_num >= -1 and order_num < l:
                    self.tree.xpath(xpath)[order_num].getparent().remove(self.tree.xpath(xpath)[order_num])
                    return True
                else:
                    log.debug('index error in remove_device function')
            else:
                log.debug('remove disk fail, there are not more disks to remove')
        else:
            log.debug('element /domain/devices not found in xml_etree when adding disk')
            return False

    def create_dict(self):
        self.vm_dict['name'] = self.name
        self.vm_dict['uuid'] = self.uuid
        self.vm_dict['machine'] = self.machine
        self.vm_dict['disk'] = []
        self.vm_dict['disk'].append(self.primary_disk)
        self.vm_dict['net'] = []
        self.vm_dict['net'].append(self.primary_net)
        self.vm_dict['spice'] = {}
        self.vm_dict['spice']['port'] = self.spice_port
        self.vm_dict['spice']['passwd'] = self.spice_passwd

    def get_graphics_port(self):
        if 'tlsPort' in self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].keys():
            spice_tls  =  self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].get('tlsPort')
        else:
            spice_tls = None

        if 'port' in self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].keys():
            spice  =  self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].get('port')
        else:
            spice = None

        if 'port' in self.tree.xpath('/domain/devices/graphics[@type="vnc"]')[0].keys():
            vnc =    self.tree.xpath('/domain/devices/graphics[@type="vnc"]')[0].get('port')
        else:
            vnc = None

        if 'websocket' in   self.tree.xpath('/domain/devices/graphics[@type="vnc"]')[0].keys():
            vnc_websocket = self.tree.xpath('/domain/devices/graphics[@type="vnc"]')[0].get('websocket')
        else:
            vnc_websocket = None

        return spice, spice_tls, vnc, vnc_websocket

    def remove_selinux_options(self):
        self.remove_recursive_tag('seclabel', self.tree.getroot())

    def remove_recursive_tag(self, tag, parent):
        for child in parent.getchildren():
            if tag == child.tag:
                parent.remove(child)
            else:
                self.remove_recursive_tag(tag, child)

    def spice_remove_passwd_nossl(self):
        if 'password' in self.tree.xpath('/domain/devices/graphics')[0].keys():
            self.tree.xpath('/domain/devices/graphics')[0].attrib.pop('password')
        if 'passwd' in self.tree.xpath('/domain/devices/graphics')[0].keys():
            self.tree.xpath('/domain/devices/graphics')[0].attrib.pop('passwd')
        if 'defaultMode' in self.tree.xpath('/domain/devices/graphics')[0].keys():
            # self.tree.xpath('/domain/devices/graphics')[0].attrib.pop('defaultMode')
            self.tree.xpath('/domain/devices/graphics')[0].set('defaultMode', 'insecure')

    def clean_xml_for_test(self, new_name, new_disk):
        self.new_domain_uuid()
        self.set_name(new_name)
        self.set_vdisk(new_disk)
        self.new_random_mac()
        self.spice_remove_passwd_nossl()

    def remove_branch(self, xpath, index=0):
        self.tree.xpath(xpath)[index].getparent().remove(self.tree.xpath(xpath)[index])

    def remove_uuid(self):
        self.remove_branch('/domain/uuid')

    def remove_mac(self):
        self.remove_branch('/domain/devices/interface/mac')

        # <on_poweroff>destroy</on_poweroff>
        # <on_reboot>restart</on_reboot>
        # <on_crash>restart</on_crash>

    def remove_boot_order_from_disks(self):
        for disk_xpath in self.tree.xpath('/domain/devices/disk'):
            for boot_xpath in disk_xpath.xpath('boot'):
                disk_xpath.remove(boot_xpath)

    def update_boot_order(self,list_ordered_devs,boot_menu_enable=False):

        # number of boot devices
        boot_elements = self.tree.xpath('/domain/os/boot')
        diff_elements = len(boot_elements) - len(list_ordered_devs)
        if diff_elements < 0:
            #add boot elements
            for i in range(abs(diff_elements)):
                element_boot = etree.Element('boot', dev='disk')
                self.tree.xpath('/domain/os')[0].insert(-1, element_boot)
            pass
        elif diff_elements > 0:
            #remove boot elements:
            for i in range(diff_elements):
                self.tree.xpath('/domain/os/boot')[-1].getparent().remove(self.tree.xpath('/domain/os/boot')[-1])

        # set devs in boot order:
        for i,device in zip(range(len(list_ordered_devs)),list_ordered_devs):
            if device in ['iso','cd']:
                device = 'cdrom'
            elif device in ['pxe','net']:
                device = 'network'
            elif device in ['floppy']:
                device = 'fd'
            elif device in ['disk']:
                device = 'hd'

            self.tree.xpath('/domain/os/boot')[i].set('dev',device)

        # boot menu
        if len(self.tree.xpath('/domain/os/bootmenu')) > 0:
            if boot_menu_enable is True:
                self.tree.xpath('/domain/os/bootmenu')[0].set('enable', 'yes')
            else:
                self.tree.xpath('/domain/os/bootmenu')[0].set('enable', 'no')
        elif boot_menu_enable is True:
            element_bootmenu = etree.Element('bootmenu', enable='yes')
            self.tree.xpath('/domain/os')[0].insert(-1, element_bootmenu)


    def set_name(self, new_name):
        self.tree.xpath('/domain/name')[0].text = new_name

        # TODO INFO TO DEVELOPER: modificamos las variables internas del objeto??
        # creo que mejor no, es más curro y no se utilizará.
        # vale más la pena ddedicar tiempo a poner excepciones
        # self.name = new_name
        # self.vm_dict['name'] = new_name

    def set_vdisk(self, new_path_vdisk, index=0, type_disk='qcow2', force_bus=False):
        if self.tree.xpath('/domain/devices/disk[@device="disk"]'):
            self.tree.xpath('/domain/devices/disk[@device="disk"]')[index].xpath('source')[0].set('file',
                                                                                                  new_path_vdisk)
            self.tree.xpath('/domain/devices/disk[@device="disk"]')[index].xpath('driver')[0].set('type', type_disk)
            path = self.tree.xpath('/domain/devices/disk[@device="disk"]')[index].xpath('source')[0].get('file')
            if force_bus is False:
                bus = self.tree.xpath('/domain/devices/disk[@device="disk"]')[index].xpath('target')[0].get('bus')
                if bus is None:
                    bus = 'ide'
            else:
                bus = force_bus
                self.tree.xpath('/domain/devices/disk[@device="disk"]')[index].xpath('target')[0].set('bus', bus)

            dev = '{}d{}'.format(BUS_LETTER[bus],index_to_char_suffix_disks[self.index_disks[bus]])
            self.tree.xpath('/domain/devices/disk[@device="disk"]')[index].xpath('target')[0].set('dev', dev)
            self.index_disks[bus] += 1
            return path

    def set_cdrom(self, new_path_cdrom, index=0):
        if self.tree.xpath('/domain/devices/disk[@device="cdrom"]'):
            self.tree.xpath('/domain/devices/disk[@device="cdrom"]')[index].xpath('source')[0].set('file',
                                                                                                  new_path_cdrom)
            path = self.tree.xpath('/domain/devices/disk[@device="cdrom"]')[index].xpath('source')[0].get('file')

            bus = 'ide'
            dev = '{}d{}'.format(BUS_LETTER[bus],index_to_char_suffix_disks[self.index_disks[bus]])

            self.tree.xpath('/domain/devices/disk[@device="cdrom"]')[index].xpath('target')[0].set('bus', bus)
            self.tree.xpath('/domain/devices/disk[@device="cdrom"]')[index].xpath('target')[0].set('dev', dev)

            self.index_disks[bus] += 1
            return path

    def set_floppy(self, new_path_floppy, index=0):
        if self.tree.xpath('/domain/devices/disk[@device="floppy"]'):
            self.tree.xpath('/domain/devices/disk[@device="floppy"]')[index].xpath('source')[0].set('file',
                                                                                                  new_path_floppy)
            path = self.tree.xpath('/domain/devices/disk[@device="floppy"]')[index].xpath('source')[0].get('file')


            return path

    def randomize_vm(self):
        self.new_random_mac()
        self.new_domain_uuid()

        self.dict_from_xml()

    def print_vm_dict(self):
        pprint(self.vm_dict)

    def return_xml(self):
        return etree.tostring(self.tree, encoding='unicode', pretty_print=True)

    def print_xml(self):
        log.debug(self.return_xml())

    def print_tag(self,tag,to_log=False):
        x = self.return_xml()
        str_out = x[x.find('<{}'.format(tag)):x.rfind('</{}>'.format(tag)) + len(tag) + 4]
        if to_log is False:
            print(str_out)
        elif to_log is None:
            pass
        else:
            log.debug(str_out)
        return str_out

    # def __repr__(self):
    #    return self.return_xml()

    def __str__(self):
        return self.return_xml()


def remove_recursive_tag(tag, parent):
    for child in parent.getchildren():
        if tag == child.tag:
            parent.remove(child)
        else:
            remove_recursive_tag(tag, child)

    return parent


def create_template_from_dict(dict_template_new):
    pass


def update_xml_from_dict_domain(id_domain, xml=None):
    d = get_domain(id_domain)
    hw = d['hardware']
    if xml is None:
        v = DomainXML(d['xml'])
    else:
        v = DomainXML(xml)
    if v.parser is False:
        return False
    # v.set_memory(memory=hw['currentMemory'],unit=hw['currentMemory_unit'])
    v.set_memory(memory=hw['memory'], unit=hw['memory_unit'],current=int(hw.get('currentMemory',hw['memory'])*DEFAULT_BALLOON))
    total_disks_in_xml = len(v.tree.xpath('/domain/devices/disk[@device="disk"]'))
    total_cdroms_in_xml = len(v.tree.xpath('/domain/devices/disk[@device="cdrom"]'))
    total_floppies_in_xml = len(v.tree.xpath('/domain/devices/disk[@device="floppy"]'))

    if 'boot_order' in hw.keys():
        if 'boot_menu_enable' in hw.keys():
            v.update_boot_order(hw['boot_order'], hw['boot_menu_enable'])
        else:
            v.update_boot_order(hw['boot_order'])

    if 'disks' in hw.keys():
        num_remove_disks = total_disks_in_xml - len(hw['disks'])
        if num_remove_disks > 0:
            for i in range(num_remove_disks):
                v.remove_disk()
        for i in range(len(hw['disks'])):
            s=hw['disks'][i]['file']
            if s[s.rfind('.'):].lower().find('qcow') == 1:
                type_disk = 'qcow2'
            else:
                type_disk = 'raw'



            if i >= total_disks_in_xml:
                force_bus = hw['disks'][i].get('bus', False)
                if force_bus is False:
                    force_bus = 'virtio'
                v.add_disk(index=i,path_disk=hw['disks'][i]['file'],type_disk=type_disk,bus=force_bus)
            else:
                force_bus = hw['disks'][i].get('bus', False)
                if force_bus is False:
                    v.set_vdisk(hw['disks'][i]['file'], index=i,type_disk=type_disk)
                else:
                    v.set_vdisk(hw['disks'][i]['file'], index=i, type_disk=type_disk, force_bus=force_bus)
    elif total_disks_in_xml > 0:
        for i in range(total_disks_in_xml):
            v.remove_disk()

    if 'isos' in hw.keys():
        num_remove_cdroms = total_cdroms_in_xml - len(hw['isos'])
        if num_remove_cdroms > 0:
            for i in range(num_remove_cdroms):
                v.remove_cdrom()
        for i in range(len(hw['isos'])):
            if i >= total_cdroms_in_xml:
                v.add_cdrom(index=i, path_cdrom=hw['isos'][i]['path'])
            else:
                v.set_cdrom(hw['isos'][i]['path'], index=i)
    elif total_cdroms_in_xml > 0:
        for i in range(total_cdroms_in_xml):
            v.remove_cdrom()

    if 'floppies' in hw.keys():
        num_remove_floppies = total_floppies_in_xml - len(hw['floppies'])
        if num_remove_floppies > 0:
            for i in range(num_remove_floppies):
                v.remove_floppy()
        for i in range(len(hw['floppies'])):
            if i >= total_floppies_in_xml:
                v.add_floppy(index=i, path_floppy=hw['floppies'][i]['path'])
            else:
                v.set_floppy(hw['floppies'][i]['path'], index=i)
    elif total_floppies_in_xml > 0:
        for i in range(total_floppies_in_xml):
            v.remove_floppy()



    v.set_name(id_domain)
    # INFO TO DEVELOPER, deberíamos poder usar la funcion v.set_description(para poner algo)
    # INFO TO DEVELOPER, estaría bien guardar la plantilla de la que deriva en algún campo de rethink,
    # la puedo sacar a partir de hw['name'], hay que decidir como le llamamos al campo
    # es importante para poder filtrar y saber cuantas máquinas han derivado,
    # aunque la información que vale de verdad es la backing-chain del disco
    template_name = hw['name']

    # TODO FALTA AÑADIR RED, Y PUEDE HABER MÁS DE UNA,
    # SE PUEDE HACER UN REMOVE DE TODAS LAS REDES Y LUEGO AÑADIR
    # CON    v.add_interface()
    for interface_index in range(len(v.vm_dict['interfaces'])):
        v.remove_interface(order=interface_index)

    if 'interfaces' in hw.keys():
        for d_interface in hw['interfaces']:
            v.add_interface(type=d_interface['type'],
                            id=d_interface['id'],
                            model_type=d_interface['model'])

    v.set_vcpu(hw['vcpus'])
    v.set_video_type(hw['video']['type'])
    # INFO TO DEVELOPER, falta hacer un v.set_network_id (para ver contra que red hace bridge o se conecta
    # INFO TO DEVELOPER, falta hacer un v.set_netowk_type (para seleccionar si quiere virtio o realtek por ejemplo)

    v.randomize_vm()
    v.remove_selinux_options()
    v.remove_boot_order_from_disks()
    # v.print_xml()
    xml_raw = v.return_xml()
    hw_updated = v.dict_from_xml()

    update_domain_dict_hardware(id_domain, hw_updated, xml=xml_raw)
    return xml_raw


def populate_dict_hardware_from_create_dict(id_domain):
    domain = get_domain(id_domain)
    create_dict = domain['create_dict']
    new_hardware_dict = {}
    if 'origin' in create_dict.keys():
        template_origin = create_dict['origin']
        template = get_domain(template_origin)
        new_hardware_dict = template['hardware'].copy()

    else:
        # TODO domain from iso or new
        pass

    if 'hardware' in create_dict.keys():
        if 'disks' in create_dict['hardware'].keys():
            new_hardware_dict['disks'] = create_dict['hardware']['disks'].copy()

        for media_type in ['isos','floppies']:
            if media_type in create_dict['hardware'].keys():
                new_hardware_dict[media_type] = []
                for d in create_dict['hardware'][media_type]:
                    new_media_dict = {}
                    media = get_media(d['id'])
                    new_media_dict['path'] = media['path_downloaded']
                    new_hardware_dict[media_type].append(new_media_dict)


    new_hardware_dict['name'] = id_domain
    new_hardware_dict['uuid'] = None

    # MEMORY and CPUS
    new_hardware_dict['vcpus'] = create_dict['hardware']['vcpus']
    new_hardware_dict['currentMemory'] = create_dict['hardware'].get('currentMemory',int(create_dict['hardware']['memory'] * DEFAULT_BALLOON))
    new_hardware_dict['memory'] = create_dict['hardware']['memory']
    new_hardware_dict['currentMemory_unit'] = 'KiB'
    new_hardware_dict['memory_unit'] = 'KiB'

    # VIDEO
    id_video = create_dict['hardware']['videos'][0]
    new_hardware_dict['video'] = create_dict_video_from_id(id_video)

    # GRAPHICS
    id_graphics = create_dict['hardware']['graphics'][0]

    pool_var = domain['hypervisors_pools']
    id_pool = pool_var if type(pool_var) is str else pool_var[0]
    new_hardware_dict['graphics'] = create_dict_graphics_from_id(id_graphics, id_pool)

    # INTERFACES
    list_ids_interfaces = create_dict['hardware']['interfaces']
    new_hardware_dict['interfaces'] = create_list_interfaces_from_list_ids(list_ids_interfaces)

    # BOOT MENU
    if 'hardware' in create_dict.keys():
        if 'boot_order' in create_dict['hardware'].keys():
            new_hardware_dict['boot_order'] = create_dict['hardware']['boot_order']
        if 'boot_menu_enable' in create_dict['hardware'].keys():
            new_hardware_dict['boot_menu_enable'] = create_dict['hardware']['boot_menu_enable']
    #import pprint
    #pprint.pprint(new_hardware_dict)
    #print('############### domain {}'.format(id_domain))
    update_table_field('domains',
                       id_domain,
                       'hardware',
                       new_hardware_dict,
                       merge_dict=False)


def create_dict_video_from_id(id_video):
    dict_video = get_dict_from_item_in_table('videos', id_video)
    d = {'heads': dict_video['heads'],
         'ram': dict_video['ram'],
         'type': dict_video['model'],
         'vram': dict_video['vram']
         }
    return d


def create_list_interfaces_from_list_ids(list_ids_networks):
    l = []
    for id_net in list_ids_networks:
        l.append(create_dict_interface_hardware_from_id(id_net))
    return l


def create_dict_interface_hardware_from_id(id_net):
    dict_net = get_dict_from_item_in_table('interfaces', id_net)

    return {'type': dict_net['kind'],
            'id': dict_net['ifname'],
            'name': dict_net['name'],
            'model': dict_net['model'],
            'net': dict_net['net']}


def create_dict_graphics_from_id(id, pool_id):
    dict_graph = get_dict_from_item_in_table('graphics', id)
    if dict_graph is None:
        log.error('{} not defined as id in graphics table, value default is used'.format(id))
        dict_graph = get_dict_from_item_in_table('graphics', 'default')

    # deprectaed
    #type = dict_graph['type']
    d = {}
    #d['type'] = type
    pool = get_dict_from_item_in_table('hypervisors_pools', pool_id)

    if pool['viewer']['defaultMode'] == 'Insecure':
        d['defaultMode'] = 'Insecure'
        d['certificate'] = ''
        d['domain'] = ''

    if pool['viewer']['defaultMode'] == 'Secure':
        d['defaultMode'] = 'Secure'
        d['certificate'] = pool['viewer']['certificate']
        d['domain'] = pool['viewer']['defaultMode']

    return d

def recreate_xml_to_start(id, ssl=True, cpu_host_model=False):
    dict_domain = get_domain(id)

    xml = dict_domain['xml']
    x = DomainXML(xml)
    if x.parser is False:
        #error when parsing xml
        return False

    ##### actions to customize xml

    if dict_domain.get('not_change_cpu_section',False) is False:
        x.set_cpu_host_model(cpu_host_model)

    # spice video compression
    #x.add_spice_graphics_if_not_exist()
    x.set_spice_video_options()

    # spice password
    if ssl is True:
        #recreate random password in x.viewer_passwd
        x.reset_viewer_passwd()
    else:
        # only for test purposes, not use in production
        x.spice_remove_passwd_nossl()

    #add vlc access
    x.add_vlc_with_websockets()

    # redo network
    try:
        list_interfaces = dict_domain['create_dict']['hardware']['interfaces']
    except KeyError:
        list_interfaces = []
        log.info('domain {} withouth key interfaces in create_dict'.format(id))

    mac_address = []
    for interface_index in range(len(x.vm_dict['interfaces'])):
        mac_address.append(x.vm_dict['interfaces'][interface_index]['mac'])
        x.remove_interface(order=interface_index)

    interface_index = 0

    for id_interface in list_interfaces:
        d_interface = get_interface(id_interface)

        x.add_interface(type=d_interface['kind'],
                        id=d_interface['ifname'],
                        model_type=d_interface['model'],
                        mac=mac_address[interface_index])

        interface_index += 1

    x.remove_selinux_options()

    #remove boot order in disk definition that conflict with /os/boot order in xml
    x.remove_boot_order_from_disks()

    x.dict_from_xml()
    # INFO TO DEVELOPER, OJO, PORQUE AQUI SE PIERDE EL BACKING CHAIN??
    update_domain_dict_hardware(id, x.vm_dict, xml=xml)
    if 'viewer_passwd' in x.__dict__.keys():
        #update password in database
        update_domain_viewer_started_values(id, passwd=x.viewer_passwd)
        log.debug("updated viewer password {} in domain {}".format(x.viewer_passwd, id))

    xml = x.return_xml()
    # log.debug('#####################################################')
    # log.debug(xml)
    # log.debug('#####################################################')

    return xml
