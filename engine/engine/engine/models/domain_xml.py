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
from collections import OrderedDict
from io import StringIO
from pprint import pprint

import xmltodict
from engine.services.db import (
    get_and_update_personal_vlan_id_from_domain_id,
    get_dict_from_item_in_table,
    get_domain,
    get_graphics_types,
    get_interface,
    remove_fieds_when_stopped,
    update_domain_dict_create_dict,
    update_domain_dict_hardware,
    update_domain_viewer_started_values,
    update_table_field,
)
from engine.services.db.downloads import get_media
from engine.services.lib.functions import pop_key_if_zero, randomMAC
from engine.services.lib.storage import insert_storage
from engine.services.log import *
from flatten_dict import flatten
from lxml import etree
from schema import And, Optional, Schema, SchemaError, Use
from yattag import indent

DEFAULT_SPICE_VIDEO_COMPRESSION = "auto_glz"

CPU_MODEL_FALLBACK = "qemu64"

DEFAULT_BALLOON = 1

BUS_TYPES = ["sata", "ide", "virtio"]

BUS_LETTER = {"ide": "h", "sata": "s", "virtio": "v"}

XML_SNIPPET_NETWORK = """
    <interface type="network">
      <source network="default"/>
      <mac address="xx:xx:xx:xx:xx:xx"/>
      <model type="virtio"/>
    </interface>
"""

XML_SNIPPET_BRIDGE = """
    <interface type='bridge'>
      <source bridge='n2m-bridge'/>
      <mac address='52:54:00:eb:b1:aa'/>
      <model type='virtio'/>
    </interface>
"""

XML_SNIPPET_OVS = """
    <interface type='bridge'>
      <source bridge='{ovs_br_name}'/>
      <mac address='52:54:00:eb:b1:aa'/>
      <virtualport type='openvswitch'></virtualport>
      <vlan>
        <tag id='{vlan_id}'/>
      </vlan>
      <model type="virtio"/>
    </interface>
"""

XML_SNIPPET_CDROM = """
    <disk type="file" device="cdrom">
      <driver name="qemu" type="raw"/>
      <source file="{path_cdrom}"/>
      <target dev="sd{suffix_descriptor}" bus="sata"/>
      <readonly/>
    </disk>
"""

XML_SNIPPET_FLOPPY = """
    <disk type="file" device="floppy">
      <source file="{path_floppy}"/>
      <target dev="fda" bus="fdc"/>
    </disk>
"""

XML_SNIPPET_DISK_VIRTIO = """
    <disk type="file" device="disk">
      <driver name="qemu" type="qcow2"/>
      <source file="/path/to/disk.qcow"/>
      <target dev="vd{}" bus="virtio"/>
    </disk>
"""

XML_SNIPPET_DISK_CUSTOM = """
    <disk type="file" device="disk">
      <driver name="qemu" type="{type_disk}"/>
      <source file="{path_disk}"/>
      <target dev="{preffix_descriptor}d{suffix_descriptor}" bus="{bus}"/>
    </disk>
"""

XML_SNIPPET_METADATA = """
  <metadata>
    <isard:isard xmlns:isard="http://isardvdi.com">
      <isard:who user_id="{user_id}" group_id="{group_id}" category_id="{category_id}"/>
      <isard:parent parent_id="{parent_id}"/>
    </isard:isard>
  </metadata>

"""


CPU_MODEL_NAMES = [
    "486",
    "pentium",
    "pentium2",
    "pentium3",
    "pentiumpro",
    "coreduo",
    "n270",
    "core2duo",
    "qemu32",
    "kvm32",
    "cpu64-rhel5",
    "cpu64-rhel6",
    "kvm64",
    "qemu64",
    "Conroe",
    "Penryn",
    "Nehalem",
    "Nehalem-IBRS",
    "Westmere",
    "Westmere-IBRS",
    "SandyBridge",
    "SandyBridge-IBRS",
    "IvyBridge",
    "IvyBridge-IBRS",
    "Haswell-noTSX",
    "Haswell-noTSX-IBRS",
    "Haswell",
    "Haswell-IBRS",
    "Broadwell-noTSX",
    "Broadwell-noTSX-IBRS",
    "Broadwell",
    "Broadwell-IBRS",
    "Skylake-Client",
    "Skylake-Client-IBRS",
    "Skylake-Server",
    "Skylake-Server-IBRS",
    "athlon",
    "phenom",
    "Opteron_G1",
    "Opteron_G2",
    "Opteron_G3",
    "Opteron_G4",
    "Opteron_G5",
    "EPYC",
    "EPYC-IBPB",
]

BANDWIDTH_SCHEMA = Schema(
    {
        Optional("inbound"): {
            Optional("@average"): And(Use(int)),
            Optional("@peak"): And(Use(int)),
            Optional("@floor"): And(Use(int)),
            Optional("@burst"): And(Use(int)),
        },
        Optional("outbound"): {
            Optional("@average"): And(Use(int)),
            Optional("@peak"): And(Use(int)),
            Optional("@burst"): And(Use(int)),
        },
    }
)

IOTUNE_SCHEMA = Schema(
    {
        # Optional("total_bytes_sec"): And(Use(int)),
        Optional("read_bytes_sec"): And(Use(int)),
        Optional("write_bytes_sec"): And(Use(int)),
        # Optional("total_iops_sec"): And(Use(int)),
        Optional("read_iops_sec"): And(Use(int)),
        Optional("write_iops_sec"): And(Use(int)),
        # Optional("total_bytes_sec_max"): And(Use(int)),
        Optional("read_bytes_sec_max"): And(Use(int)),
        Optional("write_bytes_sec_max"): And(Use(int)),
        # Optional("total_iops_sec_max"): And(Use(int)),
        Optional("read_iops_sec_max"): And(Use(int)),
        Optional("write_iops_sec_max"): And(Use(int)),
        Optional("size_iops_sec"): And(Use(int)),
        # Optional("total_bytes_sec_max_length"): And(Use(int)),
        Optional("read_bytes_sec_max_length"): And(Use(int)),
        Optional("write_bytes_sec_max"): And(Use(int)),
        # Optional("total_iops_sec_max_length"): And(Use(int)),
        Optional("read_iops_sec_max_length"): And(Use(int)),
        Optional("write_iops_sec_max"): And(Use(int)),
    }
)

index_to_char_suffix_disks = "a,b,c,d,e,f,g,h,i,j,k,l,m,n".split(",")


class DomainXML(object):
    def __init__(self, xml):
        # self.tree = etree.parse(StringIO(xml))

        parser = etree.XMLParser(remove_blank_text=True)
        try:
            self.tree = etree.parse(StringIO(xml), parser)
            self.parser = True
        except Exception as e:
            logs.exception_id.debug("0022")
            log.error("Exception when parse xml: {}".format(e))
            log.error("xml that fail: \n{}".format(xml))
            log.error("Traceback: {}".format(traceback.format_exc()))
            self.parser = False
            return None

        self.vm_dict = self.dict_from_xml(self.tree)

        self.index_disks = {}
        self.index_disks["virtio"] = 0
        self.index_disks["ide"] = 0
        self.index_disks["sata"] = 0
        self.d_graphics_types = None

    # def update_xml(self,**kwargs):
    #     if kwargs.__contains__('vcpus'):
    #         log.debug(1.)

    def new_domain_uuid(self):
        "Create new uuid from random function uuid.uuid4()"
        new_uuid = str(uuid.uuid4())
        self.tree.xpath("/domain/uuid")[0].text = new_uuid
        return new_uuid

    def new_random_mac(self):
        new_mac = randomMAC()
        self.reset_mac_address(mac=new_mac)
        return new_mac

    def reset_mac_address(self, dev_index=0, mac=None):
        """delete the mac address from xml. In the next boot libvirt create a random mac
        If you want to fix mac address mac parameter is optional.
        If there are more than one network device, the dev_index indicates the network device position
        in the xml definition. dev_index = 0 is the first network interface defined in xml."""

        if mac is None:
            mac = randomMAC()

        self.tree.xpath("/domain/devices/interface")[dev_index].xpath("mac")[
            dev_index
        ].set("address", mac)

    def dict_from_xml(self, xml_tree=False):
        ## TODO INFO TO DEVELOPER: hay que montar excepciones porque si no el xml peta
        ## cuando no existe un atributo
        vm_dict = {}
        if xml_tree is False:
            xml_tree = self.tree

        if xml_tree.xpath("/domain/devices/graphics"):
            element_graphics = xml_tree.xpath("/domain/devices/graphics")[0]

            if "type" in self.tree.xpath("/domain/devices/graphics")[0].keys():
                type = self.tree.xpath("/domain/devices/graphics")[0].get("type")
            else:
                type = None

            if "defaultMode" in self.tree.xpath("/domain/devices/graphics")[0].keys():
                defaultMode = self.tree.xpath("/domain/devices/graphics")[0].get(
                    "defaultMode"
                )
            else:
                defaultMode = None

            vm_dict["graphics"] = {}
            vm_dict["graphics"]["type"] = type
            vm_dict["graphics"]["defaultMode"] = defaultMode

        # if 'passwd' in self.tree.xpath('/domain/devices/graphics')[0].keys():
        #     if 'viewer' not in vm_dict.keys():
        #         vm_dict['viewer'] = {}
        #     vm_dict['viewer']['passwd'] = self.tree.xpath('/domain/devices/graphics')[0].get('passwd')

        if xml_tree.xpath("/domain/name"):
            vm_dict["name"] = xml_tree.xpath("/domain/name")[0].text

        if xml_tree.xpath("/domain/uuid"):
            vm_dict["uuid"] = xml_tree.xpath("/domain/uuid")[0].text

        if xml_tree.xpath("/domain/os/type"):
            if xml_tree.xpath("/domain/os/type")[0].get("machine"):
                vm_dict["machine"] = xml_tree.xpath("/domain/os/type")[0].get("machine")

        if xml_tree.xpath("/domain/memory"):
            vm_dict["memory"] = int(xml_tree.xpath("/domain/memory")[0].text)
            vm_dict["memory_unit"] = (
                xml_tree.xpath("/domain/memory")[0].get("unit")
                if xml_tree.xpath("/domain/memory")[0].get("unit") is None
                else "KiB"
            )

        if xml_tree.xpath("/domain/currentMemory"):
            vm_dict["currentMemory"] = int(
                xml_tree.xpath("/domain/currentMemory")[0].text
            )
            vm_dict["currentMemory_unit"] = (
                xml_tree.xpath("/domain/currentMemory")[0].get("unit")
                if xml_tree.xpath("/domain/currentMemory")[0].get("unit") is None
                else "KiB"
            )

        if xml_tree.xpath("/domain/maxMemory"):
            vm_dict["maxMemory"] = xml_tree.xpath("/domain/maxMemory")[0].text
            vm_dict["maxMemory_unit"] = (
                xml_tree.xpath("/domain/maxMemory")[0].get("unit")
                if xml_tree.xpath("/domain/maxMemory")[0].get("unit") is None
                else "KiB"
            )

        if xml_tree.xpath("/domain/vcpu"):
            vm_dict["vcpus"] = int(xml_tree.xpath("/domain/vcpu")[0].text)

        if xml_tree.xpath("/domain/devices/video/model"):
            vm_dict["video"] = {}
            for key in ("type", "ram", "vram", "vgamem", "heads"):
                if key in self.tree.xpath("/domain/devices/video/model")[0].keys():
                    vm_dict["video"][key] = xml_tree.xpath(
                        "/domain/devices/video/model"
                    )[0].get(key)

        if xml_tree.xpath('/domain/devices/disk[@device="disk"]'):
            vm_dict["disks"] = list()
            for tree in xml_tree.xpath('/domain/devices/disk[@device="disk"]'):
                list_dict = {}
                list_dict["type"] = tree.xpath("driver")[0].get("type")
                list_dict["file"] = tree.xpath("source")[0].get("file")
                list_dict["dev"] = tree.xpath("target")[0].get("dev")
                list_dict["bus"] = tree.xpath("target")[0].get("bus")
                vm_dict["disks"].append(list_dict)

        if xml_tree.xpath('/domain/devices/disk[@device="floppy"]'):
            vm_dict["floppies"] = list()
            for tree in xml_tree.xpath('/domain/devices/disk[@device="floppy"]'):
                list_dict = {}
                # list_dict['type'] = tree.xpath('driver')[0].get('type')
                if len(tree.xpath("source")) != 0:
                    list_dict["file"] = tree.xpath("source")[0].get("file")
                list_dict["dev"] = tree.xpath("target")[0].get("dev")
                # list_dict['bus'] = tree.xpath('target')[0].get('bus')
                vm_dict["floppies"].append(list_dict)

        if xml_tree.xpath('/domain/devices/disk[@device="cdrom"]'):
            vm_dict["cdroms"] = list()
            for tree in xml_tree.xpath('/domain/devices/disk[@device="cdrom"]'):
                list_dict = {}
                # list_dict['type'] = tree.xpath('driver')[0].get('type')
                if len(tree.xpath("source")) != 0:
                    list_dict["file"] = tree.xpath("source")[0].get("file")
                list_dict["dev"] = tree.xpath("target")[0].get("dev")
                # list_dict['bus'] = tree.xpath('target')[0].get('bus')
                vm_dict["cdroms"].append(list_dict)

        if xml_tree.xpath("/domain/devices/interface"):
            vm_dict["interfaces"] = list()
            for tree in xml_tree.xpath("/domain/devices/interface"):
                list_dict = {}

                list_dict["type"] = tree.get("type")

                if tree.xpath("mac"):
                    list_dict["mac"] = tree.xpath("mac")[0].get("address")

                if list_dict["type"] == "network" and tree.xpath("source"):
                    # list_dict['id'] = tree.xpath('source')[0].get('network')
                    list_dict["net"] = tree.xpath("source")[0].get("network")

                if list_dict["type"] == "bridge" and tree.xpath("source"):
                    # list_dict['id'] = tree.xpath('source')[0].get('bridge')
                    list_dict["net"] = tree.xpath("source")[0].get("bridge")

                if tree.xpath("model"):
                    list_dict["model"] = tree.xpath("model")[0].get("type")

                if tree.xpath("bandwidth"):
                    bandwith_tree = tree.xpath("bandwidth")[0]
                    bandwidth_xml = etree.tostring(bandwith_tree, encoding="unicode")
                    list_dict["qos"] = xmltodict.parse(bandwidth_xml)["bandwidth"]
                else:
                    list_dict["qos"] = False

                vm_dict["interfaces"].append(list_dict)

        vm_dict["boot_order"] = [
            x.get("dev") for x in tree.xpath("/domain/os/boot[@dev]")
        ]
        vm_dict["boot_menu_enable"] = [
            x.get("dev") for x in tree.xpath("/domain/os/bootmenu[@enable]")
        ]

        ## OJO!!!!!!!!!!!!!!

        # EN SPICE SIEMPRE TIENE QUE ESTAR autoport='yes' listen='0.0.0.0'

        # CUANDO ESTÁ CORRIENDO APARECE EL PUERTO, PASSWORD
        # GENERAR EL PASSWORD ALEATORIAMENTE Y PASÁRSELO
        # Y OJO PORQUE HAY QUE CAMBIARLO A TLS Y GENERAR TICKETS
        # ESTÁ EN IMAGINARI
        self.vm_dict = vm_dict

        return vm_dict

    def set_description(self, description):
        if self.tree.xpath("/domain/description"):
            self.tree.xpath("/domain/description")[0].text = description

        else:
            element = etree.parse(
                StringIO("<description>{}</description>".format(description))
            ).getroot()

            if self.tree.xpath("/domain/title"):
                self.tree.xpath("/domain/title")[0].addnext(element)
            else:
                if self.tree.xpath("/domain/name"):
                    self.tree.xpath("/domain/name")[0].addnext(element)

    def set_title(self, title):
        if self.tree.xpath("/domain/title"):
            self.tree.xpath("/domain/title")[0].text = title

        else:
            element = etree.parse(StringIO("<title>{}</title>".format(title))).getroot()

            if self.tree.xpath("/domain/name"):
                self.tree.xpath("/domain/name")[0].addnext(element)

    def set_memory(self, memory, unit="KiB", current=-1, max=-1):

        if self.tree.xpath("/domain/memory"):
            self.tree.xpath("/domain/memory")[0].set("unit", unit)
            self.tree.xpath("/domain/memory")[0].text = str(memory)
        else:
            element = etree.parse(
                StringIO("<memory unit='{}'>{}</memory>".format(unit, memory))
            )
            self.tree.xpath("/domain/name")[0].addnext(element)

        if current <= 0:
            current_size = memory
        else:
            current_size = current

        if self.tree.xpath("/domain/currentMemory"):
            self.tree.xpath("/domain/currentMemory")[0].set("unit", unit)
            self.tree.xpath("/domain/currentMemory")[0].text = str(current_size)
        else:
            element = etree.parse(
                StringIO(
                    "<currentMemory unit='{}'>{}</currentMemory>".format(
                        unit, current_size
                    )
                )
            )
            self.tree.xpath("/domain/memory")[0].addnext(element)

        if max > 0:
            if self.tree.xpath("/domain/maxMemory"):
                self.tree.xpath("/domain/maxMemory")[0].set("unit", unit)
                self.tree.xpath("/domain/maxMemory")[0].text = str(max)
            else:
                element = etree.parse(
                    StringIO("<maxMemory unit='{}'>{}</maxMemory>".format(unit, max))
                )
                self.tree.xpath("/domain/maxMemory")[0].addnext(element)

        else:
            if self.tree.xpath("/domain/maxMemory"):
                self.remove_branch("/domain/maxMemory")

    def set_vcpu(self, vcpus, placement="static"):

        # example from libvirt.org  <vcpu placement='static' cpuset="1-4,^3,6" current="1">2</vcpu>
        if self.tree.xpath("/domain/vcpu"):
            # self.tree.xpath('/domain/vcpu')[0].attrib.pop('placement')
            self.tree.xpath("/domain/vcpu")[0].set("placement", placement)
            self.tree.xpath("/domain/vcpu")[0].text = str(vcpus)
        else:
            element = etree.parse(
                StringIO("<vcpu placement='{}'>{}</vcpu>".format(placement, vcpus))
            ).getroot()
            self.tree.xpath("/domain/name")[0].addnext(element)

        # with machine=pc-q35 we need to parse vcpus in cpu entry
        if self.tree.xpath("/domain/cpu"):
            element = etree.parse(
                StringIO(
                    f"<topology sockets='1' dies='1' cores='{vcpus}' threads='1'/>"
                )
            ).getroot()
            cpu_xpath = self.tree.xpath("/domain/cpu")[0]
            for tag_topology in cpu_xpath.xpath("topology"):
                cpu_xpath.remove(tag_topology)
            cpu_xpath.append(element)

    def add_to_domain(
        self,
        xpath_same,
        element_tree,
        xpath_next="",
        xpath_previous="",
        xpath_parent="/domain",
    ):
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
            log.debug(
                "element {} not found in xml_tree when adding to the domain".format(
                    xpath_parent
                )
            )

    def add_device(self, xpath_same, element_tree, xpath_next="", xpath_previous=""):
        # mejor añadir a la vez cds y discos para verificar que no hay lio con los hda, hdb...

        if not self.add_to_domain(
            xpath_same, element_tree, xpath_next, xpath_previous, "/domain/devices"
        ):
            return False

    def add_disk(
        self, index=0, path_disk="/path/to/disk.qcow", type_disk="qcow2", bus="virtio"
    ):
        global index_to_char_suffix_disks

        prefix = BUS_LETTER[bus]
        index_bus = self.index_disks[bus]
        xml_snippet = XML_SNIPPET_DISK_CUSTOM.format(
            type_disk=type_disk,
            path_disk=path_disk,
            preffix_descriptor=prefix,
            suffix_descriptor=index_to_char_suffix_disks[index_bus],
            bus=bus,
        )
        disk_etree = etree.parse(StringIO(xml_snippet))
        new_disk = disk_etree.xpath("/disk")[0]
        xpath_same = '/domain/devices/disk[@device="disk"]'
        xpath_next = '/domain/devices/disk[@device="cdrom"]'
        xpath_previous = "/domain/devices/emulator"
        self.add_device(
            xpath_same, new_disk, xpath_next=xpath_next, xpath_previous=xpath_previous
        )
        self.index_disks[bus] += 1

    def add_floppy(self, path_floppy="/path/to/floppy"):
        xml_snippet = XML_SNIPPET_FLOPPY.format(path_floppy=path_floppy)
        disk_etree = etree.parse(StringIO(xml_snippet))
        new_disk = disk_etree.xpath("/disk")[0]
        xpath_same = '/domain/devices/disk[@device="floppy"]'
        xpath_previous = '/domain/devices/disk[@device="disk"]'
        xpath_next = "/domain/devices/controller"
        self.add_device(
            xpath_same, new_disk, xpath_next=xpath_next, xpath_previous=xpath_previous
        )
        self.index_disks["ide"] += 1

    def add_cdrom(self, path_cdrom="/path/to/cdrom"):
        global index_to_char_suffix_disks
        # default bus sata

        index_bus = self.index_disks["sata"]
        xml_snippet = XML_SNIPPET_CDROM.format(
            suffix_descriptor=index_to_char_suffix_disks[index_bus],
            path_cdrom=path_cdrom,
        )
        disk_etree = etree.parse(StringIO(xml_snippet))
        new_disk = disk_etree.xpath("/disk")[0]
        xpath_same = '/domain/devices/disk[@device="cdrom"]'
        xpath_previous = '/domain/devices/disk[@device="disk"]'
        xpath_next = "/domain/devices/controller"
        self.add_device(
            xpath_same, new_disk, xpath_next=xpath_next, xpath_previous=xpath_previous
        )
        self.index_disks["sata"] += 1

    def add_interface(
        self,
        type_interface,
        mac,
        id_domain,
        id_interface,
        model_type="virtio",
        net="default",
        qos=False,
    ):
        """
        :param type_interface:' bridge' OR 'network' .
                     If bridge inserts xml code for bridge,
                     If network insert xml code for virtual network
        :return:
        """

        if type_interface == "bridge":
            interface_etree = etree.parse(StringIO(XML_SNIPPET_BRIDGE))
            interface_etree.xpath("/interface")[0].xpath("source")[0].set("bridge", net)

        elif type_interface == "ovs":
            xml_snippet = XML_SNIPPET_OVS.format(vlan_id=net, ovs_br_name="ovsbr0")
            interface_etree = etree.parse(StringIO(xml_snippet))

        elif type_interface == "personal":
            vlan_id = False
            if type(net) == str:
                if net.find("-") > 0 and len(net[net.find("-") :]) > 1:
                    range = net.split("-")
                    if range[0].isnumeric() is True and range[1].isnumeric() is True:
                        if (
                            int(range[0]) < pow(2, 12)
                            and int(range[1]) < pow(2, 12)
                            and int(range[1]) > int(range[0])
                        ):
                            vlan_id = get_and_update_personal_vlan_id_from_domain_id(
                                id_domain,
                                id_interface,
                                range_start=int(range[0]),
                                range_end=int(range[1]),
                            )
                            if vlan_id is not False:
                                xml_snippet = XML_SNIPPET_OVS.format(
                                    vlan_id=vlan_id, ovs_br_name="ovsbr0"
                                )
                                interface_etree = etree.parse(StringIO(xml_snippet))
                            else:
                                log.error(f"vlan_id not available for personal network")
                        else:
                            log.error(
                                f"interface personal net with vlans_id numbers not valid (<4096?): {net}"
                            )
                    else:
                        log.error(
                            f"interface personal net is not defined as a range of numeric vlans_id as xxxx-yyyy. net: {net}"
                        )
                else:
                    log.error(
                        f"interface personal net is not defined as string with a range of vlans_id as xxxx-yyyy. net: {net}"
                    )
            else:
                log.error("interface personal net is not a string")
            if vlan_id is False:
                return -1

        elif type_interface.find("ovs") == 0 and len(type_interface) > 3:
            suffix_br = type_interface[3:]
            ovs_br_name = "ovsbr" + suffix_br
            xml_snippet = XML_SNIPPET_OVS.format(vlan_id=net, ovs_br_name=ovs_br_name)
            interface_etree = etree.parse(StringIO(xml_snippet))

        elif type_interface == "network":
            interface_etree = etree.parse(StringIO(XML_SNIPPET_NETWORK))
            interface_etree.xpath("/interface")[0].xpath("source")[0].set(
                "network", net
            )

        else:
            log.error(
                "type_interface of interface incorrect when adding interface in xml"
            )
            return -1

        interface_etree.xpath("/interface")[0].xpath("mac")[0].set("address", mac)
        interface_etree.xpath("/interface")[0].xpath("model")[0].set("type", model_type)

        new_interface = interface_etree.xpath("/interface")[0]

        if type(qos) is dict:
            bandwidth_dict = {"bandwidth": qos}
            bandwidth_xml = indent(
                xmltodict.unparse(bandwidth_dict, full_document=False)
            )
            bandwidth_etree = etree.parse(StringIO(bandwidth_xml))
            bandwidth_element = bandwidth_etree.xpath("/bandwidth")[0]
            interface_element = interface_etree.xpath("/interface")[0]
            insert_index = len(interface_element.getchildren())
            interface_element.insert(insert_index, bandwidth_element)

        xpath_same = "/domain/devices/interface"
        xpath_next = "/domain/devices/input"
        xpath_previous = "/domain/devices/controller"

        self.add_device(
            xpath_same,
            new_interface,
            xpath_next=xpath_next,
            xpath_previous=xpath_previous,
        )

    def reset_viewer_passwd(self, ssl=True):
        passwd = "".join(
            [random.choice(string.ascii_letters + string.digits) for n in range(32)]
        )
        self.set_viewer_passwd(passwd, ssl)

    def set_cpu_host_model(self, cpu_host_model="host-model"):
        """update cpu host_model from xml original in domain,
        by default cpu_host_model is host-model (see libvirt xml help)
        cpu_host_mode: not-change, custom, host-model, host-passthrough"""

        if cpu_host_model == "not-change":
            return False

        fallback = etree.parse(
            StringIO("<model fallback='allow'>{}</model>".format(CPU_MODEL_FALLBACK))
        ).getroot()

        if cpu_host_model == "host-model" or cpu_host_model is False:
            # cpu = etree.Element('cpu', mode='host-model', check='partial')
            # cpu.append(etree.Element('model', fallback='allow'))

            # cpu = etree.parse(StringIO("<cpu mode='host-model' check='partial'>").getroot()
            cpu = etree.parse(StringIO("<cpu mode='host-model' > </cpu>")).getroot()
            cpu.append(fallback)

        elif cpu_host_model == "host-passthrough":
            cpu = etree.parse(
                StringIO("<cpu mode='{}' > </cpu>".format(cpu_host_model))
            ).getroot()
            cpu.append(fallback)

        elif cpu_host_model in CPU_MODEL_NAMES:
            exact_cpu = etree.parse(
                StringIO("<model>{}</model>".format(cpu_host_model))
            ).getroot()
            cpu = etree.parse(StringIO("<cpu mode='custom' > </cpu>")).getroot()
            cpu.append(exact_cpu)

        else:
            log.error(
                "cpu_host_model not supported, cpu section not modified: "
                + cpu_host_model
            )
            return False

        # delete old cpu section
        domain = self.tree.xpath("/domain")[0]

        cpu_old = domain.xpath("cpu")
        if len(cpu_old) == 1:
            domain.remove(cpu_old[0])

        num_vcpus = int(self.tree.xpath("/domain/vcpu")[0].text)
        element = etree.parse(
            StringIO(
                f"<topology sockets='1' dies='1' cores='{num_vcpus}' threads='1'/>"
            )
        ).getroot()
        cpu.append(element)

        # insert new cpu section
        xpath_same = "/domain/cpu"
        xpath_previous = "/domain/features"
        xpath_next = "/domain/clock"
        self.add_to_domain(xpath_same, cpu, xpath_next, xpath_previous)

    def set_video_type(self, type_video):
        if type_video == "none":
            # remove all attributes like vram that have no sense if type_video is none
            # libvirt xml parser launch an exception if these keys exists
            for key in self.tree.xpath("/domain/devices/video/model")[0].keys():
                if key != "type":
                    try:
                        del self.tree.xpath("/domain/devices/video/model")[0].attrib[
                            key
                        ]
                    except Exception as e:
                        logs.exception_id.debug("0023")
                        print(
                            f"Exception when remove attribute from video model none in xml: {e}"
                        )
            # remove alivas
            if self.tree.xpath("/domain/devices/video/alias"):
                self.tree.xpath("/domain/devices/video/alias")[-1].getparent().remove(
                    self.tree.xpath("//domain/devices/video/alias")[-1]
                )

        self.tree.xpath("/domain/devices/video/model")[0].set("type", type_video)

    def add_metadata_isard(self, user_id, group_id, category_id, parent_id):
        xpath_same = "/domain/metadata"
        xpath_previous = "/domain/name"
        xpath_next = "/domain/memory"
        xml_snippet = XML_SNIPPET_METADATA.format(
            user_id=user_id,
            group_id=group_id,
            category_id=category_id,
            parent_id=parent_id,
        )

        metadata_etree = etree.parse(StringIO(xml_snippet)).getroot()
        self.add_to_domain(xpath_same, metadata_etree, xpath_next, xpath_previous)

    def add_vnc_with_websockets(self):
        xpath_same = "/domain/devices/graphics"
        xpath_previous = "/domain/devices/interface"
        xpath_next = "/domain/devices/video"
        # VNC protocol limits passwords to 8 characters
        # https://qemu.readthedocs.io/en/latest/system/vnc-security.html#with-passwords
        passwd = self.viewer_passwd[:8]

        xpath_vnc = '/domain/devices/graphics[@type="vnc"]'

        # remove if exist vnc
        if self.tree.xpath("/domain/devices"):
            if self.tree.xpath(xpath_vnc):
                self.tree.xpath(xpath_vnc)[0].getparent().remove(
                    self.tree.xpath(xpath_vnc)[0]
                )
        else:
            log.debug("element /domain/devices not found in xml_etree when adding disk")
            return False

        # vnc_string_xml = "<graphics type='vnc' port=auto autoport='no' websocket='-1' listen='0.0.0.0'>. <listen type='address' address='0.0.0.0'/>"

        vnc_string_xml = (
            f"    <graphics type='vnc' passwd='{passwd}' autoport='yes' websocket='-1' listen='0.0.0.0' > \n"
            + "        <listen type='address' address='0.0.0.0'/> \n"
            + "    </graphics>"
        )
        vnc = etree.parse(StringIO(vnc_string_xml)).getroot()
        self.add_to_domain(xpath_same, vnc, xpath_next, xpath_previous)

    def set_spice_video_options(self, id_graphics="default"):
        xpath_spice = '/domain/devices/graphics[@type="spice"]'

        self.d_graphics_types = get_graphics_types(id_graphics)

        if self.d_graphics_types is None:
            d_spice_options = {
                "image": {"compression": "auto_glz"},
                "jpeg": {"compression": "always"},
                "playback": {"compression": "off"},
                "streaming": {"mode": "all"},
                "zlib": {"compression": "always"},
            }
        else:
            d_spice_options = self.d_graphics_types["spice"]["options"]

        # add spice graphics if not exists
        if not self.tree.xpath(xpath_spice):
            self.add_spice_graphics_if_not_exist()

        # remove all options in spice
        tree_spice = self.tree.xpath(xpath_spice)[0]
        for i in tree_spice.getchildren():
            tree_spice.remove(i)

        # add all options in spice
        for p, v in d_spice_options.items():
            element = etree.Element(p, **v)
            tree_spice.insert(-1, element)

        # libvirt adds the following audio by default if only spice graphic is enabled
        # but we also add vnc
        # https://libvirt.org/formatdomain.html#spice-audio-backend
        if not self.tree.xpath('/domain/devices/audio[@id="1"][@type="spice"]'):
            self.add_to_domain(
                "/domain/devices/audio",
                etree.parse(StringIO('<audio id="1" type="spice"/>')).getroot(),
                "",
                "/domain/devices/sound",
            )

    def add_spice_graphics_if_not_exist(self, video_compression=None):
        xpath_spice = '/domain/devices/graphics[@type="spice"]'

        if not self.tree.xpath(xpath_spice):
            xpath_same = "/domain/devices/graphics"
            xpath_previous = "/domain/devices/interface"
            xpath_next = "/domain/devices/video"

            if video_compression is None:
                video_compression = DEFAULT_SPICE_VIDEO_COMPRESSION

            string_xml = (
                '    <graphics type="spice" port="-1" tlsPort="-1" autoport="yes">\n'
                + f'        <image compression="{video_compression}"/>\n'
                + "    </graphics>"
            )

            spice_graphics = etree.parse(StringIO(string_xml)).getroot()
            self.add_to_domain(xpath_same, spice_graphics, xpath_next, xpath_previous)

    def set_viewer_passwd(self, passwd, ssl=True):
        # if self.tree.xpath('/domain/devices/graphics')[0].get('type') == 'spice':
        if (
            "password"
            in self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].keys()
        ):
            self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].attrib.pop(
                "password"
            )
        self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].set(
            "passwd", passwd
        )
        self.viewer_passwd = passwd
        if ssl is True:
            # mode secure if you not use websockets
            # self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].set('defaultMode','secure')
            # defaultMode=any is the default value, if you pop defaultMode attrib is the same
            self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].set(
                "defaultMode", "any"
            )
        else:
            if (
                "defaultMode"
                in self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].keys()
            ):
                self.tree.xpath('/domain/devices/graphics[@type="spice"]')[
                    0
                ].attrib.pop("defaultMode")
                # else:
                #     log.error('domain {} has not spice graphics and can not change password of spice connection'.format(self.vm_dict['name']))

    def set_domain_type_and_emulator(self, type="kvm", emulator="/usr/bin/qemu-kvm"):
        try:
            # change type qemu that is the default in some xmls from virt-install
            self.tree.xpath("/domain")[0].attrib.pop("type")
            self.tree.xpath("/domain")[0].set("type", type)

            # change <emulator>/usr/bin/qemu-system-x86_64</emulator>
            # to     <emulator>/usr/bin/qemu-kvm</emulator>
            # that set audio in spice previus to call qemu-system-x86_64
            self.tree.xpath("/domain/devices/emulator")[0].text = emulator

        except Exception as e:
            log.error("Exception when setting domain type and emulator: {}".format(e))

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
        xpath = "/domain/devices/interface"
        self.remove_device(xpath, order_num=order)

    def remove_device(self, xpath, order_num=-1):
        if self.tree.xpath("/domain/devices"):
            if self.tree.xpath(xpath):
                if order_num == -1:
                    print("ORDER NUM:" + str(order_num))
                    remaining = len(self.tree.xpath(xpath))
                    while remaining:
                        print(
                            "ORDER NUM:"
                            + str(order_num)
                            + " REMAINING:"
                            + str(remaining)
                        )
                        self.tree.xpath(xpath)[remaining - 1].getparent().remove(
                            self.tree.xpath(xpath)[remaining - 1]
                        )
                        remaining = len(self.tree.xpath(xpath))
                    return True
                l = len(self.tree.xpath(xpath))
                if order_num >= -1 and order_num < l:
                    self.tree.xpath(xpath)[order_num].getparent().remove(
                        self.tree.xpath(xpath)[order_num]
                    )
                    return True
                else:
                    log.debug("index error in remove_device function")
            else:
                log.debug("remove disk fail, there are not more disks to remove")
        else:
            log.debug("element /domain/devices not found in xml_etree when adding disk")
            return False

    def create_dict(self):
        self.vm_dict["name"] = self.name
        self.vm_dict["uuid"] = self.uuid
        self.vm_dict["machine"] = self.machine
        self.vm_dict["disk"] = []
        self.vm_dict["disk"].append(self.primary_disk)
        self.vm_dict["net"] = []
        self.vm_dict["net"].append(self.primary_net)
        self.vm_dict["spice"] = {}
        self.vm_dict["spice"]["port"] = self.spice_port
        self.vm_dict["spice"]["passwd"] = self.spice_passwd

    def get_graphics_port(self):
        if (
            "tlsPort"
            in self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].keys()
        ):
            spice_tls = self.tree.xpath('/domain/devices/graphics[@type="spice"]')[
                0
            ].get("tlsPort")
        else:
            spice_tls = None

        if (
            "port"
            in self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].keys()
        ):
            spice = self.tree.xpath('/domain/devices/graphics[@type="spice"]')[0].get(
                "port"
            )
        else:
            spice = None

        if "port" in self.tree.xpath('/domain/devices/graphics[@type="vnc"]')[0].keys():
            vnc = self.tree.xpath('/domain/devices/graphics[@type="vnc"]')[0].get(
                "port"
            )
        else:
            vnc = None

        if (
            "websocket"
            in self.tree.xpath('/domain/devices/graphics[@type="vnc"]')[0].keys()
        ):
            vnc_websocket = self.tree.xpath('/domain/devices/graphics[@type="vnc"]')[
                0
            ].get("websocket")
        else:
            vnc_websocket = None

        return spice, spice_tls, vnc, vnc_websocket

    def remove_selinux_options(self):
        self.remove_recursive_tag("seclabel", self.tree.getroot())

    def remove_recursive_tag(self, tag, parent):
        for child in parent.getchildren():
            if tag == child.tag:
                parent.remove(child)
            else:
                self.remove_recursive_tag(tag, child)

    def spice_remove_passwd_nossl(self):
        if "password" in self.tree.xpath("/domain/devices/graphics")[0].keys():
            self.tree.xpath("/domain/devices/graphics")[0].attrib.pop("password")
        if "passwd" in self.tree.xpath("/domain/devices/graphics")[0].keys():
            self.tree.xpath("/domain/devices/graphics")[0].attrib.pop("passwd")
        if "defaultMode" in self.tree.xpath("/domain/devices/graphics")[0].keys():
            # self.tree.xpath('/domain/devices/graphics')[0].attrib.pop('defaultMode')
            self.tree.xpath("/domain/devices/graphics")[0].set(
                "defaultMode", "insecure"
            )

    def clean_xml_for_test(self, new_name, new_disk):
        self.new_domain_uuid()
        self.set_name(new_name)
        self.set_vdisk(new_disk)
        self.new_random_mac()
        self.spice_remove_passwd_nossl()

    def remove_branch(self, xpath, index=0):
        self.tree.xpath(xpath)[index].getparent().remove(self.tree.xpath(xpath)[index])

    def remove_uuid(self):
        self.remove_branch("/domain/uuid")

    def remove_mac(self):
        self.remove_branch("/domain/devices/interface/mac")

        # <on_poweroff>destroy</on_poweroff>
        # <on_reboot>restart</on_reboot>
        # <on_crash>restart</on_crash>

    def remove_boot_order_and_danger_options_from_disks(self):
        for disk_xpath in self.tree.xpath("/domain/devices/disk"):
            for tag_to_remove in ["boot", "backingStore", "alias", "address"]:
                for tag_xpath in disk_xpath.xpath(tag_to_remove):
                    disk_xpath.remove(tag_xpath)

    def update_boot_order(self, list_ordered_devs, boot_menu_enable=False):

        # number of boot devices
        boot_elements = self.tree.xpath("/domain/os/boot")
        diff_elements = len(boot_elements) - len(list_ordered_devs)
        if diff_elements < 0:
            # add boot elements
            for i in range(abs(diff_elements)):
                element_boot = etree.Element("boot", dev="disk")
                self.tree.xpath("/domain/os")[0].insert(-1, element_boot)
            pass
        elif diff_elements > 0:
            # remove boot elements:
            for i in range(diff_elements):
                self.tree.xpath("/domain/os/boot")[-1].getparent().remove(
                    self.tree.xpath("/domain/os/boot")[-1]
                )

        # set devs in boot order:
        for i, device in zip(range(len(list_ordered_devs)), list_ordered_devs):
            if device in ["iso", "cd"]:
                device = "cdrom"
            elif device in ["pxe", "net"]:
                device = "network"
            elif device in ["floppy"]:
                device = "fd"
            elif device in ["disk"]:
                device = "hd"

            self.tree.xpath("/domain/os/boot")[i].set("dev", device)

        # boot menu
        if len(self.tree.xpath("/domain/os/bootmenu")) > 0:
            if boot_menu_enable is True:
                self.tree.xpath("/domain/os/bootmenu")[0].set("enable", "yes")
            else:
                self.tree.xpath("/domain/os/bootmenu")[0].set("enable", "no")
        elif boot_menu_enable is True:
            element_bootmenu = etree.Element("bootmenu", enable="yes")
            self.tree.xpath("/domain/os")[0].insert(-1, element_bootmenu)

    def set_name(self, new_name):
        self.tree.xpath("/domain/name")[0].text = new_name

        # TODO INFO TO DEVELOPER: modificamos las variables internas del objeto??
        # creo que mejor no, es más curro y no se utilizará.
        # vale más la pena ddedicar tiempo a poner excepciones
        # self.name = new_name
        # self.vm_dict['name'] = new_name

    def set_vdisk(self, new_path_vdisk, index=0, type_disk="qcow2", force_bus=False):
        if self.tree.xpath('/domain/devices/disk[@device="disk"]'):
            self.tree.xpath('/domain/devices/disk[@device="disk"]')[index].xpath(
                "source"
            )[0].set("file", new_path_vdisk)
            self.tree.xpath('/domain/devices/disk[@device="disk"]')[index].xpath(
                "driver"
            )[0].set("type", type_disk)
            path = (
                self.tree.xpath('/domain/devices/disk[@device="disk"]')[index]
                .xpath("source")[0]
                .get("file")
            )
            if force_bus is False:
                bus = (
                    self.tree.xpath('/domain/devices/disk[@device="disk"]')[index]
                    .xpath("target")[0]
                    .get("bus")
                )
                if bus is None:
                    bus = "sata"
            else:
                bus = force_bus
                self.tree.xpath('/domain/devices/disk[@device="disk"]')[index].xpath(
                    "target"
                )[0].set("bus", bus)

            dev = "{}d{}".format(
                BUS_LETTER[bus], index_to_char_suffix_disks[self.index_disks[bus]]
            )
            self.tree.xpath('/domain/devices/disk[@device="disk"]')[index].xpath(
                "target"
            )[0].set("dev", dev)
            self.index_disks[bus] += 1
            return path

    def set_cdrom(self, new_path_cdrom, index=0):
        if self.tree.xpath('/domain/devices/disk[@device="cdrom"]'):
            self.tree.xpath('/domain/devices/disk[@device="cdrom"]')[index].xpath(
                "source"
            )[0].set("file", new_path_cdrom)
            path = (
                self.tree.xpath('/domain/devices/disk[@device="cdrom"]')[index]
                .xpath("source")[0]
                .get("file")
            )

            bus = "sata"
            dev = "{}d{}".format(
                BUS_LETTER[bus], index_to_char_suffix_disks[self.index_disks[bus]]
            )

            self.tree.xpath('/domain/devices/disk[@device="cdrom"]')[index].xpath(
                "target"
            )[0].set("bus", bus)
            self.tree.xpath('/domain/devices/disk[@device="cdrom"]')[index].xpath(
                "target"
            )[0].set("dev", dev)

            self.index_disks[bus] += 1
            return path

    def set_floppy(self, new_path_floppy, index=0):
        if self.tree.xpath('/domain/devices/disk[@device="floppy"]'):
            self.tree.xpath('/domain/devices/disk[@device="floppy"]')[index].xpath(
                "source"
            )[0].set("file", new_path_floppy)
            path = (
                self.tree.xpath('/domain/devices/disk[@device="floppy"]')[index]
                .xpath("source")[0]
                .get("file")
            )

            return path

    def randomize_vm(self, mac=False, uuid=True):
        if mac:
            self.new_random_mac()
        if uuid:
            self.new_domain_uuid()
        self.dict_from_xml()

    def print_vm_dict(self):
        pprint(self.vm_dict)

    def return_xml(self):
        return indent(etree.tostring(self.tree, encoding="unicode"))

    def print_xml(self):
        log.debug(self.return_xml())

    def print_tag(self, tag, to_log=False):
        x = self.return_xml()
        str_out = x[
            x.find("<{}".format(tag)) : x.rfind("</{}>".format(tag)) + len(tag) + 4
        ]
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
    remove_fieds_when_stopped(id_domain)
    d = get_domain(id_domain)
    hw = d["hardware"]
    if xml is None:
        v = DomainXML(d["xml"])
    else:
        v = DomainXML(xml)
    if v.parser is False:
        return False
    # v.set_memory(memory=hw['currentMemory'],unit=hw['currentMemory_unit'])
    v.set_memory(
        memory=hw["memory"],
        unit=hw["memory_unit"],
        current=int(hw.get("currentMemory", hw["memory"]) * DEFAULT_BALLOON),
    )
    total_disks_in_xml = len(v.tree.xpath('/domain/devices/disk[@device="disk"]'))
    total_cdroms_in_xml = len(v.tree.xpath('/domain/devices/disk[@device="cdrom"]'))
    total_floppies_in_xml = len(v.tree.xpath('/domain/devices/disk[@device="floppy"]'))

    if "boot_order" in hw.keys():
        if "boot_menu_enable" in hw.keys():
            v.update_boot_order(hw["boot_order"], hw["boot_menu_enable"])
        else:
            v.update_boot_order(hw["boot_order"])

    if "disks" in hw.keys():
        num_remove_disks = total_disks_in_xml - len(hw["disks"])
        if num_remove_disks > 0:
            for i in range(num_remove_disks):
                v.remove_disk()
        for i in range(len(hw["disks"])):
            insert_storage(hw["disks"][i])
            s = hw["disks"][i]["file"]
            if s[s.rfind(".") :].lower().find("qcow") == 1:
                type_disk = "qcow2"
            else:
                type_disk = "raw"

            if i >= total_disks_in_xml:
                force_bus = hw["disks"][i].get("bus", False)
                if force_bus is False:
                    force_bus = "virtio"
                v.add_disk(
                    index=i,
                    path_disk=hw["disks"][i]["file"],
                    type_disk=type_disk,
                    bus=force_bus,
                )
            else:
                force_bus = hw["disks"][i].get("bus", False)
                if force_bus is False:
                    v.set_vdisk(hw["disks"][i]["file"], index=i, type_disk=type_disk)
                else:
                    v.set_vdisk(
                        hw["disks"][i]["file"],
                        index=i,
                        type_disk=type_disk,
                        force_bus=force_bus,
                    )
    elif total_disks_in_xml > 0:
        for i in range(total_disks_in_xml):
            v.remove_disk()

    if "isos" in hw.keys():
        num_remove_cdroms = total_cdroms_in_xml - len(hw["isos"])
        if num_remove_cdroms > 0:
            for i in range(num_remove_cdroms):
                v.remove_cdrom()
        for i in range(len(hw["isos"])):
            if i >= total_cdroms_in_xml:
                v.add_cdrom(path_cdrom=hw["isos"][i]["path"])
            else:
                v.set_cdrom(hw["isos"][i]["path"], index=i)
    elif total_cdroms_in_xml > 0:
        for i in range(total_cdroms_in_xml):
            v.remove_cdrom()

    if "custom" in d.keys():
        if type(d["custom"]) is dict:
            if "path_custom_fd" in d["custom"].keys():
                path_custom_fd = d["custom"]["path_custom_fd"]
                v.add_floppy(path_floppy=path_custom_fd)

    if "floppies" in hw.keys():
        num_remove_floppies = total_floppies_in_xml - len(hw["floppies"])
        if num_remove_floppies > 0:
            for i in range(num_remove_floppies):
                v.remove_floppy()
        for i in range(len(hw["floppies"])):
            if i >= total_floppies_in_xml:
                v.add_floppy(path_floppy=hw["floppies"][i]["path"])
            else:
                v.set_floppy(hw["floppies"][i]["path"], index=i)
    elif total_floppies_in_xml > 0:
        for i in range(total_floppies_in_xml):
            v.remove_floppy()

    v.set_name(id_domain)
    # INFO TO DEVELOPER, deberíamos poder usar la funcion v.set_description(para poner algo)
    # INFO TO DEVELOPER, estaría bien guardar la plantilla de la que deriva en algún campo de rethink,
    # la puedo sacar a partir de hw['name'], hay que decidir como le llamamos al campo
    # es importante para poder filtrar y saber cuantas máquinas han derivado,
    # aunque la información que vale de verdad es la backing-chain del disco
    # template_name = hw['name']

    v.remove_interface()
    """ for interface_index in range(len(v.vm_dict['interfaces'])):
        v.(order=interface_index) """

    recreate_xml_interfaces(d, v)

    v.set_vcpu(hw["vcpus"])
    v.set_video_type(hw["video"]["type"])
    # INFO TO DEVELOPER, falta hacer un v.set_network_id (para ver contra que red hace bridge o se conecta
    # INFO TO DEVELOPER, falta hacer un v.set_netowk_type (para seleccionar si quiere virtio o realtek por ejemplo)

    v.randomize_vm()
    v.remove_selinux_options()
    v.remove_boot_order_and_danger_options_from_disks()
    # v.print_xml()
    xml_raw = v.return_xml()
    # VERIFING HARDWARE FROM XML
    hw_updated = v.dict_from_xml()

    # pprint diffs between hardware and hardware from xml
    try:
        flatten_hw = flatten(hw, enumerate_types=(list,))
        flatten_hw_updated = flatten(hw_updated, enumerate_types=(list,))
        set_flatten_hw = set((k, v) for k, v in flatten_hw.items())
        set_flatten_hw_updated = set((k, v) for k, v in flatten_hw_updated.items())
        diff_hw_TO_hw_updated = list(set_flatten_hw - set_flatten_hw_updated)
        diff_hw_updated_TO_hw = list(set_flatten_hw_updated - set_flatten_hw)
        pprint(sorted(diff_hw_TO_hw_updated))
        pprint(sorted(diff_hw_updated_TO_hw))
    except:
        pass

    update_domain_dict_hardware(id_domain, hw, xml=xml_raw)
    update_table_field(
        "domains", id_domain, "hardware_from_xml", hw_updated, merge_dict=False
    )

    return xml_raw


def populate_dict_hardware_from_create_dict(id_domain):
    domain = get_domain(id_domain)
    create_dict = domain["create_dict"]
    new_hardware_dict = {}
    # if 'origin' in create_dict.keys():
    #     template_origin = create_dict['origin']
    #     template = get_domain(template_origin)
    #     new_hardware_dict = template['hardware'].copy()
    #
    # else:
    #     # TODO domain from iso or new
    #     pass

    if "disks" in create_dict["hardware"].keys():
        new_hardware_dict["disks"] = create_dict["hardware"]["disks"].copy()

    for media_type in ["isos", "floppies"]:
        if media_type in create_dict["hardware"].keys():
            new_hardware_dict[media_type] = []
            for d in create_dict["hardware"][media_type]:
                new_media_dict = {}
                media = get_media(d["id"])
                new_media_dict["path"] = media["path_downloaded"]
                new_hardware_dict[media_type].append(new_media_dict)

    new_hardware_dict["name"] = id_domain
    new_hardware_dict["uuid"] = None

    # MEMORY and CPUS
    new_hardware_dict["vcpus"] = create_dict["hardware"]["vcpus"]
    new_hardware_dict["currentMemory"] = create_dict["hardware"].get(
        "currentMemory", int(create_dict["hardware"]["memory"] * DEFAULT_BALLOON)
    )
    new_hardware_dict["memory"] = create_dict["hardware"]["memory"]
    new_hardware_dict["currentMemory_unit"] = "KiB"
    new_hardware_dict["memory_unit"] = "KiB"

    # VIDEO
    id_video = create_dict["hardware"]["videos"][0]
    new_hardware_dict["video"] = create_dict_video_from_id(id_video)

    # GRAPHICS
    id_graphics = create_dict["hardware"]["graphics"][0]

    pool_var = domain["hypervisors_pools"]
    id_pool = pool_var if type(pool_var) is str else pool_var[0]
    # ~ new_hardware_dict['graphics'] = create_dict_graphics_from_id(id_graphics, id_pool)

    # INTERFACES
    list_interfaces_id = create_dict["hardware"]["interfaces"]
    if "interfaces_mac" not in create_dict["hardware"].keys():
        create_dict["hardware"]["interfaces_mac"] = []
    list_interfaces_mac = create_dict["hardware"]["interfaces_mac"]
    if len(list_interfaces_mac) < len(list_interfaces_id):
        for i in range(len(list_interfaces_mac), len(list_interfaces_id)):
            create_dict["hardware"]["interfaces_mac"].append(randomMAC())
        update_domain_dict_create_dict(id_domain, create_dict)
    elif len(list_interfaces_mac) > len(list_interfaces_id):
        create_dict["hardware"]["interfaces_mac"] = list_interfaces_mac[
            : len(list_interfaces_id)
        ]
        update_domain_dict_create_dict(id_domain, create_dict)

    new_hardware_dict["interfaces"] = create_list_interfaces_from_list_ids(
        list_interfaces_id, list_interfaces_mac
    )
    d_netnames_mac = {
        "macs": {d["id"]: d["mac"] for d in new_hardware_dict["interfaces"]}
    }
    d_netnames_mac_reset = {"macs": False}
    update_table_field("domains", id_domain, "create_dict", d_netnames_mac_reset)
    update_table_field("domains", id_domain, "create_dict", d_netnames_mac)

    # BOOT MENU
    if "hardware" in create_dict.keys():
        if "boot_order" in create_dict["hardware"].keys():
            new_hardware_dict["boot_order"] = create_dict["hardware"]["boot_order"]
        if "boot_menu_enable" in create_dict["hardware"].keys():
            new_hardware_dict["boot_menu_enable"] = create_dict["hardware"][
                "boot_menu_enable"
            ]
    # import pprint
    # pprint.pprint(new_hardware_dict)
    # print('############### domain {}'.format(id_domain))
    update_table_field(
        "domains", id_domain, "hardware", new_hardware_dict, merge_dict=False
    )


def create_dict_video_from_id(id_video):
    dict_video = get_dict_from_item_in_table("videos", id_video)
    d = {
        "heads": dict_video["heads"],
        "ram": dict_video["ram"],
        "type": dict_video["model"],
        "vram": dict_video["vram"],
    }

    return d


def create_list_interfaces_from_list_ids(list_ids_networks, list_mac_networks):
    l = []
    for i, id_net in enumerate(list_ids_networks):
        mac_address = list_mac_networks[i]
        l.append(create_dict_interface_hardware_from_id(id_net, mac_address))
    return l


def create_dict_interface_hardware_from_id(id_net, mac_address):
    dict_net = get_dict_from_item_in_table("interfaces", id_net)
    qos_id = dict_net.get("qos_id", False)
    if qos_id:
        try:
            dict_qos = get_dict_from_item_in_table("qos_net", qos_id)
            try:
                # validate and convert str to int
                dict_bandwidth = BANDWIDTH_SCHEMA.validate(dict_qos["bandwidth"])
                # remove elements with zero
                dict_bandwidth = pop_key_if_zero(dict_bandwidth)
                return {
                    "type": dict_net["kind"],
                    "id": dict_net["id"],
                    "name": dict_net["name"],
                    "model": dict_net["model"],
                    "net": dict_net["net"],
                    "mac": mac_address,
                    "qos": dict_bandwidth,
                }
            except SchemaError as error:
                log.error("error validating schema of qos: {}".format(error))
        except:
            log.error(f"net qos with id {qos_id} not defined in dict_qos table")
    return {
        "type": dict_net["kind"],
        "id": dict_net["id"],
        "name": dict_net["name"],
        "model": dict_net["model"],
        "net": dict_net["net"],
        "mac": mac_address,
        "qos": False,
    }


# ~ def create_dict_graphics_from_id(id, pool_id):
# ~ dict_graph = get_dict_from_item_in_table('graphics', id)
# ~ if dict_graph is None:
# ~ log.error('{} not defined as id in graphics table, value default is used'.format(id))
# ~ dict_graph = get_dict_from_item_in_table('graphics', 'default')

# ~ # deprectaed
# ~ #type = dict_graph['type']
# ~ d = {}
# ~ #d['type'] = type
# ~ pool = get_dict_from_item_in_table('hypervisors_pools', pool_id)

# ~ if pool['viewer']['defaultMode'] == 'Insecure':
# ~ d['defaultMode'] = 'Insecure'
# ~ d['certificate'] = ''
# ~ d['domain'] = ''

# ~ if pool['viewer']['defaultMode'] == 'Secure':
# ~ d['defaultMode'] = 'Secure'
# ~ d['certificate'] = pool['viewer']['certificate']
# ~ d['domain'] = pool['viewer']['defaultMode']

# ~ return d


def recreate_xml_to_start(id_domain, ssl=True, cpu_host_model=False):
    remove_fieds_when_stopped(id_domain)
    dict_domain = get_domain(id_domain)

    xml = dict_domain["xml"]
    x = DomainXML(xml)
    if x.parser is False:
        # error when parsing xml
        return False

    ##### actions to customize xml

    # metadata
    user_id = dict_domain["user"]
    group_id = dict_domain["group"]
    category_id = dict_domain["category"]
    parent_id = dict_domain["create_dict"].get("origin", "")
    x.add_metadata_isard(user_id, group_id, category_id, parent_id)

    if (
        not dict_domain.get("create_dict", {})
        .get("hardware", {})
        .get("not_change_cpu_section")
    ):
        if (
            dict_domain.get("create_dict", {})
            .get("hardware", {})
            .get("virtualization_nested")
        ):
            x.set_cpu_host_model("host-passthrough")
        else:
            x.set_cpu_host_model(cpu_host_model)

    # spice video compression
    # x.add_spice_graphics_if_not_exist()
    x.set_spice_video_options()

    # spice password
    if ssl is True:
        # recreate random password in x.viewer_passwd
        x.reset_viewer_passwd()
    else:
        # only for test purposes, not use in production
        x.spice_remove_passwd_nossl()

    # add vnc access
    x.add_vnc_with_websockets()

    # recreate xml interfaces from create_dict
    recreate_xml_interfaces(dict_domain, x)

    x.remove_selinux_options()

    x.set_domain_type_and_emulator()

    # remove boot order in disk definition that conflict with /os/boot order in xml
    x.remove_boot_order_and_danger_options_from_disks()

    x.dict_from_xml()

    # INFO TO DEVELOPER, OJO, PORQUE AQUI SE PIERDE EL BACKING CHAIN??
    update_domain_dict_hardware(id_domain, x.vm_dict, xml=xml)
    if "viewer_passwd" in x.__dict__.keys():
        # update password in database
        update_domain_viewer_started_values(id_domain, passwd=x.viewer_passwd)
        log.debug(
            "updated viewer password {} in domain {}".format(x.viewer_passwd, id_domain)
        )

    xml = x.return_xml()
    # log.debug('#####################################################')
    # log.debug(xml)
    # log.debug('#####################################################')

    return xml


def recreate_xml_interfaces(dict_domain, x):
    id_domain = dict_domain["id"]
    # redo network
    try:
        list_interfaces = dict_domain["create_dict"]["hardware"]["interfaces"]
        list_interfaces_mac = dict_domain["create_dict"]["hardware"]["interfaces_mac"]
    except KeyError:
        list_interfaces = []
        list_interfaces_mac = []
        log.info("domain {} withouth key interfaces in create_dict".format(id_domain))

    # clean interfaces saving the mac...
    mac_address = []
    x.remove_interface()  # -1 removes it all
    """ for interface_index in range(len(x.vm_dict['interfaces'])):
        x.remove_interface(order=interface_index) """

    custom_mac = False
    if "custom" in dict_domain.keys():
        if type(dict_domain["custom"]) is dict:
            if "mac" in dict_domain["custom"].keys():
                custom_mac = dict_domain["custom"]["mac"]
                log.debug(f"custom mac when starting: {custom_mac}")

    for interface_index, id_interface in enumerate(list_interfaces):
        d_interface = get_interface(id_interface)
        qos_id = d_interface["qos_id"]
        if qos_id:
            try:
                dict_qos = get_dict_from_item_in_table("qos_net", qos_id)
                try:
                    # validate and convert str to int
                    dict_bandwidth = BANDWIDTH_SCHEMA.validate(dict_qos["bandwidth"])
                    # remove elements with zero
                    dict_bandwidth = pop_key_if_zero(dict_bandwidth)
                except:
                    dict_bandwidth = False
            except:
                dict_bandwidth = False
        else:
            dict_bandwidth = False

        ## add custom_mac in first interface:
        if interface_index == 0 and bool(custom_mac) is True:
            mac_selected = custom_mac
        else:
            mac_selected = list_interfaces_mac[interface_index]

        x.add_interface(
            type_interface=d_interface["kind"],
            model_type=d_interface["model"],
            id_interface=d_interface["id"],
            id_domain=id_domain,
            net=d_interface["net"],
            qos=dict_bandwidth,
            mac=mac_selected,
        )

        interface_index += 1


def recreate_xml_if_start_paused(xml, memory_mb=256):
    xml = xml
    unit = "KiB"
    mem_size = memory_mb * 1024

    parser = etree.XMLParser(remove_blank_text=True)
    try:
        tree = etree.parse(StringIO(xml), parser)
    except Exception as e:
        logs.exception_id.debug("0024")
        log.error(
            "Exception when parsing xml in recreate_xml_to_start_paused: {}".format(e)
        )
        log.error("xml that fail: \n{}".format(xml))
        log.error("Traceback: {}".format(traceback.format_exc()))
        return xml

    try:
        type = "kvm"
        emulator = "/usr/bin/qemu-kvm"
        # change type qemu that is the default in some xmls from virt-install
        tree.xpath("/domain")[0].attrib.pop("type")
        tree.xpath("/domain")[0].set("type", type)

        # change <emulator>/usr/bin/qemu-system-x86_64</emulator>
        # to     <emulator>/usr/bin/qemu-kvm</emulator>
        # that set audio in spice previus to call qemu-system-x86_64
        tree.xpath("/domain/devices/emulator")[0].text = emulator

    except Exception as e:
        log.error("Exception when setting domain type and emulator: {}".format(e))

    for tag in ["memory", "currentMemory", "maxMemory"]:
        if tree.xpath(f"/domain/{tag}"):
            tree.xpath(f"/domain/{tag}")[0].set("unit", unit)
            tree.xpath(f"/domain/{tag}")[0].text = str(mem_size)

    xml_output = indent(etree.tostring(tree, encoding="unicode"))
    return xml_output


def recreate_xml_if_gpu(xml, mdev_uid):
    xml = xml

    parser = etree.XMLParser(remove_blank_text=True)
    try:
        tree = etree.parse(StringIO(xml), parser)
    except Exception as e:
        logs.exception_id.debug("0024")
        log.error("Exception when parse xml in recreate_xml_if_gpu: {}".format(e))
        log.error("xml that fail: \n{}".format(xml))
        log.error("Traceback: {}".format(traceback.format_exc()))
        # return False

    uid = mdev_uid

    if os.environ.get("GPU_FAKE") == "true":
        xml_hostdev = f"""    <gpufake:gpufake xmlns:gpufake="http://gpufake.com">
          <gpufake:mdev uuid="{uid}"/>
        </gpufake:gpufake>"""
        xpath_parent = "/domain/metadata"
    else:
        xml_hostdev = f"""  <hostdev mode='subsystem' type='mdev' model='vfio-pci'>
        <source>
          <address uuid='{uid}'/>
        </source>
      </hostdev>"""
        xpath_parent = "/domain/devices"

    element_tree = etree.parse(StringIO(xml_hostdev)).getroot()
    tree.xpath(xpath_parent)[0].insert(-1, element_tree)
    xml_output = indent(etree.tostring(tree, encoding="unicode"))
    return xml_output
