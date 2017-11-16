# Copyright 2017 the Isard-vdi project authors:
#      Alberto Larraz Dalmases
#      Josep Maria Viñolas Auquer
# License: AGPLv3

#Manage domain's xml

# coding=utf-8

# TODO: INFO TO DEVELOPER revisar si hacen falta todas estas librerías para este módulo

import uuid
import random
import string
from lxml import etree
from io import StringIO
from pprint import pprint
import traceback

from .log import *
from .functions import randomMAC
from .db import get_domain, update_domain_dict_hardware, update_domain_viewer_started_values
from .db import get_dict_from_item_in_table, update_table_field




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
      <source file="/path/to/cdrom.iso"/>
      <target dev="hda" bus="ide"/>
      <readonly/>
    </disk>
'''

XML_SNIPPET_DISK = '''
    <disk type="file" device="disk">
      <driver name="qemu" type="qcow2"/>
      <source file="/path/to/disk.qcow"/>
      <target dev="vda" bus="virtio"/>
    </disk>
'''




class DomainXML(object):
    def __init__(self,xml):
        # self.tree = etree.parse(StringIO(xml))

        parser = etree.XMLParser(remove_blank_text=True)
        try:
            self.tree = etree.parse(StringIO(xml), parser)
        except Exception as e:                                                              
            log.error('Exception when parse xml: {}'.format(e))                        
            log.error('xml that fail: \n{}'.format(xml))
            log.error('Traceback: {}'.format(traceback.format_exc()))
            return False

        self.vm_dict = self.dict_from_xml(self.tree)

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

    def reset_mac_address(self,dev_index=0,mac=None):
        '''delete the mac address from xml. In the next boot libvirt create a random mac
         If you want to fix mac address mac parameter is optional.
         If there are more than one network device, the dev_index indicates the network device position
         in the xml definition. dev_index = 0 is the first network interface defined in xml.'''

        if mac is None:
            mac = randomMAC()

        self.tree.xpath('/domain/devices/interface')[dev_index].xpath('mac')[dev_index].set('address',mac)

    def dict_from_xml(self,xml_tree=False):
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
                vm_dict['machine']= xml_tree.xpath('/domain/os/type')[0].get('machine')

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
            vm_dict['video']={}
            for key in ('type','ram','vram','vgamem','heads'):
                if key in self.tree.xpath('/domain/devices/video/model')[0].keys():
                    vm_dict['video'][key]= xml_tree.xpath('/domain/devices/video/model')[0].get(key)


        if xml_tree.xpath('/domain/devices/disk[@device="disk"]'):
            vm_dict['disks'] = list()
            for tree in xml_tree.xpath('/domain/devices/disk[@device="disk"]'):
                list_dict = {}
                list_dict['type'] = tree.xpath('driver')[0].get('type')
                list_dict['file'] = tree.xpath('source')[0].get('file')
                list_dict['dev'] = tree.xpath('target')[0].get('dev')
                list_dict['bus'] = tree.xpath('target')[0].get('bus')
                vm_dict['disks'].append(list_dict)

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

        ## OJO!!!!!!!!!!!!!!

        # EN SPICE SIEMPRE TIENE QUE ESTAR autoport='yes' listen='0.0.0.0'

        # CUANDO ESTÁ CORRIENDO APARECE EL PUERTO, PASSWORD
        # GENERAR EL PASSWORD ALEATORIAMENTE Y PASÁRSELO
        # Y OJO PORQUE HAY QUE CAMBIARLO A TLS Y GENERAR TICKETS
        # ESTÁ EN IMAGINARI
        self.vm_dict = vm_dict

        return vm_dict

    def set_description(self,description):
        if self.tree.xpath('/domain/description'):
            self.tree.xpath('/domain/description')[0].text = description

        else:
            element = etree.parse(StringIO('<description>{}</description>'.format(description))).getroot()

            if self.tree.xpath('/domain/title'):
                self.tree.xpath('/domain/title')[0].addnext(element)
            else:
                if self.tree.xpath('/domain/name'):
                    self.tree.xpath('/domain/name')[0].addnext(element)


    def set_title(self,title):
        if self.tree.xpath('/domain/title'):
            self.tree.xpath('/domain/title')[0].text = title

        else:
            element = etree.parse(StringIO('<title>{}</title>'.format(title))).getroot()

            if self.tree.xpath('/domain/name'):
                self.tree.xpath('/domain/name')[0].addnext(element)

    def set_memory(self,memory,unit='KiB',current=-1,max=-1):

        if self.tree.xpath('/domain/memory'):
            self.tree.xpath('/domain/memory')[0].set('unit',unit)
            self.tree.xpath('/domain/memory')[0].text = str(memory)
        else:
            element = etree.parse(StringIO('<memory unit=\'{}\'>{}</memory>'.format(unit,memory)))
            self.tree.xpath('/domain/name')[0].addnext(element)

        if current > 0:
            if self.tree.xpath('/domain/currentMemory'):
                self.tree.xpath('/domain/currentMemory')[0].set('unit',unit)
                self.tree.xpath('/domain/currentMemory')[0].text = str(current)
            else:
                element = etree.parse(StringIO('<currentMemory unit=\'{}\'>{}</currentMemory>'.format(unit,current)))
                self.tree.xpath('/domain/memory')[0].addnext(element)

        else:
            if self.tree.xpath('/domain/currentMemory'):
                self.remove_branch('/domain/currentMemory')

        if max > 0:
            if self.tree.xpath('/domain/maxMemory'):
                self.tree.xpath('/domain/maxMemory')[0].set('unit',unit)
                self.tree.xpath('/domain/maxMemory')[0].text = str(max)
            else:
                element = etree.parse(StringIO('<maxMemory unit=\'{}\'>{}</maxMemory>'.format(unit,max)))
                self.tree.xpath('/domain/maxMemory')[0].addnext(element)

        else:
            if self.tree.xpath('/domain/maxMemory'):
                self.remove_branch('/domain/maxMemory')

    def set_vcpu(self, vcpus, placement='static'):

        #example from libvirt.org  <vcpu placement='static' cpuset="1-4,^3,6" current="1">2</vcpu>
        if self.tree.xpath('/domain/vcpu'):
            #self.tree.xpath('/domain/vcpu')[0].attrib.pop('placement')
            self.tree.xpath('/domain/vcpu')[0].set('placement',placement)
            self.tree.xpath('/domain/vcpu')[0].text = str(vcpus)
        else:
            element = etree.parse(StringIO('<vcpu placement=\'{}\'>{}</vcpu>'.format(placement,vcpus))).getroot()
            self.tree.xpath('/domain/name')[0].addnext(element)


    def add_device(self,xpath_same,element_tree,xpath_next='',xpath_previous=''):
        # mejor añadir a la vez cds y discos para verificar que no hay lio con los hda, hdb...

        if self.tree.xpath('/domain/devices'):

            if self.tree.xpath(xpath_same):
                self.tree.xpath(xpath_same)[-1].addnext(element_tree)
            elif xpath_next and self.tree.xpath(xpath_next):
                    self.tree.xpath(xpath_next)[0].addprevious(element_tree)
            elif xpath_previous and  self.tree.xpath(xpath_previous):
                    self.tree.xpath(xpath_previous)[-1].addnext(element_tree)
            else:
                self.tree.xpath('/domain/devices')[0].insert(1,element_tree)

        else:
            log.debug('element /domain/devices not found in xml_etree when adding disk')
            return False

    def add_disk(self):
        disk_etree = etree.parse(StringIO(XML_SNIPPET_DISK))
        new_disk = disk_etree.xpath('/disk')[0]
        xpath_same = '/domain/devices/disk[@device="disk"]'
        xpath_next = '/domain/devices/disk[@device="cdrom"]'
        xpath_previous = '/domain/devices/emulator'
        self.add_device(xpath_same,new_disk,xpath_next=xpath_next,xpath_previous=xpath_previous)

    def add_cdrom(self):
        disk_etree = etree.parse(StringIO(XML_SNIPPET_CDROM))
        new_disk = disk_etree.xpath('/disk')[0]
        xpath_same = '/domain/devices/disk[@device="cdrom"]'
        xpath_previous = '/domain/devices/disk[@device="disk"]'
        xpath_next = '/domain/devices/controller'
        self.add_device(xpath_same,new_disk,xpath_next=xpath_next,xpath_previous=xpath_previous)

    def add_interface(self,type,id,mac=None,model_type='virtio'):
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
            interface_etree.xpath('/interface')[0].xpath('source')[0].set('bridge',id)

        elif type == 'network':
            interface_etree = etree.parse(StringIO(XML_SNIPPET_NETWORK))
            interface_etree.xpath('/interface')[0].xpath('source')[0].set('network',id)

        else:
            log.error('type of interface incorrect when adding interface in xml')
            return -1

        interface_etree.xpath('/interface')[0].xpath('mac')[0].set('address',mac)
        interface_etree.xpath('/interface')[0].xpath('model')[0].set('type',model_type)

        new_interface = interface_etree.xpath('/interface')[0]

        xpath_same = '/domain/devices/interface'
        xpath_next = '/domain/devices/input'
        xpath_previous = '/domain/devices/controller'

        self.add_device(xpath_same,new_interface,xpath_next=xpath_next,xpath_previous=xpath_previous)

    def reset_interface(self,type,id,mac=None,model_type='virtio'):
        '''
        :param type:' bridge' OR 'network' .
                     If bridge inserts xml code for bridge,
                     If network insert xml code for virtual network
        :return:
        '''
        xpath = '/domain/devices/interface'

        while len(self.tree.xpath(xpath)):
            self.remove_branch(xpath)

        self.add_interface(type,id,mac,model_type)

    def reset_viewer_passwd(self, ssl=True):
        passwd = ''.join([random.choice(string.ascii_letters + string.digits) for n in range(16)])
        self.set_viewer_passwd(passwd, ssl)

    def set_graphics_type(self, type_graphics):
        self.tree.xpath('/domain/devices/graphics')[0].set('type',type_graphics)

    def set_video_type(self, type_video):
        self.tree.xpath('/domain/devices/video/model')[0].set('type',type_video)


    def set_viewer_passwd(self, passwd, ssl=True):
        # if self.tree.xpath('/domain/devices/graphics')[0].get('type') == 'spice':
            if 'password' in self.tree.xpath('/domain/devices/graphics')[0].keys():
                self.tree.xpath('/domain/devices/graphics')[0].attrib.pop('password')
            self.tree.xpath('/domain/devices/graphics')[0].set('passwd',passwd)
            self.viewer_passwd = passwd
            if ssl is True:
                #mode secure if you not use websockets
                #self.tree.xpath('/domain/devices/graphics')[0].set('defaultMode','secure')
                #defaultMode=any is the default value, if you pop defaultMode attrib is the same
                self.tree.xpath('/domain/devices/graphics')[0].set('defaultMode', 'any')
            else:
                if 'defaultMode' in self.tree.xpath('/domain/devices/graphics')[0].keys():
                    self.tree.xpath('/domain/devices/graphics')[0].attrib.pop('defaultMode')
        # else:
        #     log.error('domain {} has not spice graphics and can not change password of spice connection'.format(self.vm_dict['name']))

    def remove_disk(self,order=-1):
        xpath = '/domain/devices/disk[@device="disk"]'
        self.remove_device(xpath,order_num=order)

    def remove_cdrom(self,order=-1):
        xpath = '/domain/devices/disk[@device="cdrom"]'
        self.remove_device(xpath,order_num=order)

    def remove_interface(self,order=-1):
        xpath = '/domain/devices/interface'
        self.remove_device(xpath,order_num=order)

    def remove_device(self,xpath,order_num=-1):
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
        self.vm_dict['name']=self.name
        self.vm_dict['uuid']=self.uuid
        self.vm_dict['machine']=self.machine
        self.vm_dict['disk']=[]
        self.vm_dict['disk'].append(self.primary_disk)
        self.vm_dict['net']=[]
        self.vm_dict['net'].append(self.primary_net)
        self.vm_dict['spice']={}
        self.vm_dict['spice']['port']=self.spice_port
        self.vm_dict['spice']['passwd']=self.spice_passwd

    def get_graphics_port(self):
        if 'tlsPort' in self.tree.xpath('/domain/devices/graphics')[0].keys():
            tlsPort = self.tree.xpath('/domain/devices/graphics')[0].get('tlsPort')
        else:
            tlsPort = None

        if 'port' in self.tree.xpath('/domain/devices/graphics')[0].keys():
            port = self.tree.xpath('/domain/devices/graphics')[0].get('port')
        else:
            port = None

        return port, tlsPort

    def remove_selinux_options(self):
        self.remove_recursive_tag('seclabel',self.tree.getroot())

    def remove_recursive_tag(self,tag,parent):
        for child in parent.getchildren():
            if tag == child.tag:
                parent.remove(child)
            else:
                self.remove_recursive_tag(tag,child)



    def spice_remove_passwd_nossl(self):
        if 'password' in self.tree.xpath('/domain/devices/graphics')[0].keys():
            self.tree.xpath('/domain/devices/graphics')[0].attrib.pop('password')
        if 'passwd' in self.tree.xpath('/domain/devices/graphics')[0].keys():
            self.tree.xpath('/domain/devices/graphics')[0].attrib.pop('passwd')
        if 'defaultMode' in self.tree.xpath('/domain/devices/graphics')[0].keys():
            #self.tree.xpath('/domain/devices/graphics')[0].attrib.pop('defaultMode')
            self.tree.xpath('/domain/devices/graphics')[0].set('defaultMode','insecure')

    def clean_xml_for_test(self,new_name,new_disk):
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

    def set_name(self,new_name):
        self.tree.xpath('/domain/name')[0].text = new_name

        # TODO INFO TO DEVELOPER: modificamos las variables internas del objeto??
        # creo que mejor no, es más curro y no se utilizará.
        # vale más la pena ddedicar tiempo a poner excepciones
        # self.name = new_name
        # self.vm_dict['name'] = new_name

    def set_vdisk(self, new_path_vdisk,index=0):
        if self.tree.xpath('/domain/devices/disk[@device="disk"]'):
            self.tree.xpath('/domain/devices/disk[@device="disk"]')[index].xpath('source')[0].set('file',new_path_vdisk)
            path = self.tree.xpath('/domain/devices/disk[@device="disk"]')[index].xpath('source')[0].get('file')
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

    #def __repr__(self):
    #    return self.return_xml()

    def __str__(self):
        return self.return_xml()


def remove_recursive_tag(tag,parent):
    for child in parent.getchildren():
        if tag == child.tag:
            parent.remove(child)
        else:
            remove_recursive(tag,child)

    return parent


def domain_xml_to_test(domain_id,ssl=True):
    id=domain_id
    # INFO TO DEVELOPER, QUE DE UN ERROR SI EL ID NO EXISTE
    dict_domain = get_domain(domain_id)
    xml = dict_domain['xml']
    x = DomainXML(xml)
    if ssl is True:
        x.reset_viewer_passwd()
    else:
        x.spice_remove_passwd_nossl()

    x.remove_selinux_options()
    xml = x.return_xml()
    log.debug('#####################################################3')
    log.debug('#####################################################3')
    log.debug('#####################################################3')
    log.debug('#####################################################3')
    log.debug(xml)
    log.debug('#####################################################3')
    log.debug('#####################################################3')
    log.debug('#####################################################3')
    log.debug('#####################################################3')

    x.dict_from_xml()
    update_domain_dict_hardware(id,x.vm_dict,xml=xml)
    #update_domain_viewer_started_values(id,passwd=x.viewer_passwd)

    return xml

def create_template_from_dict(dict_template_new):
    pass

def update_xml_from_dict_domain(id_domain,xml=None):
    d = get_domain(id_domain)
    hw = d['hardware']
    if xml is None:
        v = DomainXML(d['xml'])
    else:
        v = DomainXML(xml)
    # v.set_memory(memory=hw['currentMemory'],unit=hw['currentMemory_unit'])
    v.set_memory(memory=hw['memory'],unit=hw['memory_unit'])
    for i in range(len(hw['disks'])):
        v.set_vdisk(hw['disks'][i]['file'],index=i)

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
    v.set_graphics_type(hw['graphics']['type'])
    v.set_video_type(hw['video']['type'])
    # INFO TO DEVELOPER, falta hacer un v.set_network_id (para ver contra que red hace bridge o se conecta
    # INFO TO DEVELOPER, falta hacer un v.set_netowk_type (para seleccionar si quiere virtio o realtek por ejemplo)

    v.randomize_vm()
    v.remove_selinux_options()
    #v.print_xml()
    xml_raw = v.return_xml()
    hw_updated = v.dict_from_xml()

    update_domain_dict_hardware(id_domain,hw_updated,xml=xml_raw)
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
        #TODO domain from iso or new
        pass

    if 'hardware' in domain.keys():
        if 'disks' in domain['hardware']:
            new_hardware_dict['disks'] = domain['hardware']['disks'].copy()

    new_hardware_dict['name'] = id_domain
    new_hardware_dict['uuid'] = None

    #MEMORY and CPUS
    new_hardware_dict['vcpus'] = create_dict['hardware']['vcpus']
    new_hardware_dict['currentMemory'] = create_dict['hardware']['memory']
    new_hardware_dict['memory'] = create_dict['hardware']['memory']
    new_hardware_dict['currentMemory_unit'] = 'KiB'
    new_hardware_dict['memory_unit'] = 'KiB' \
                                       ''

    #VIDEO
    id_video = create_dict['hardware']['videos'][0]
    new_hardware_dict['video'] = create_dict_video_from_id(id_video)

    #GRAPHICS
    id_graphics = create_dict['hardware']['graphics'][0]

    pool_var = domain['hypervisors_pools']
    id_pool = pool_var if type(pool_var) is str else pool_var[0]
    new_hardware_dict['graphics'] = create_dict_graphics_from_id(id_graphics,id_pool)

    #INTERFACES
    list_ids_interfaces = create_dict['hardware']['interfaces']
    new_hardware_dict['interfaces'] = create_list_interfaces_from_list_ids(list_ids_interfaces)
    import pprint
    pprint.pprint(new_hardware_dict)
    print('############### domain {}'.format(id_domain))
    update_table_field('domains',
                       id_domain,
                       'hardware',
                       new_hardware_dict,
                       merge_dict=False)


def create_dict_video_from_id(id_video):
    dict_video = get_dict_from_item_in_table('videos', id_video)
    d={ 'heads': dict_video['heads'],
        'ram'  : dict_video['ram'],
        'type' : dict_video['model'],
        'vram' : dict_video['vram']
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
            'id':   dict_net['ifname'],
            'name': dict_net['name'],
            'model': dict_net['model'],
            'net':  dict_net['net']}


def create_dict_graphics_from_id(id,pool_id):
    dict_graph = get_dict_from_item_in_table('graphics', id)
    type = dict_graph['type']
    d = {}
    d['type'] = type
    pool = get_dict_from_item_in_table('hypervisors_pools', pool_id)

    if pool['viewer']['defaultMode'] == 'Insecure':
        d['defaultMode'] = 'Insecure'
        d['certificate'] = ''
        d['domain']      = ''

    if pool['viewer']['defaultMode'] == 'Secure':
        d['defaultMode'] = 'Secure'
        d['certificate'] = pool['viewer']['certificate']
        d['domain']      = pool['viewer']['defaultMode']

    return d

