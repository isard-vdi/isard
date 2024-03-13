# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import datetime
import os
import random
import string
import time

import bcrypt
import pem
from OpenSSL import crypto
from rethinkdb import r


class loadConfig:
    def __init__(self):
        None

    def cfg(self):
        return {
            "RETHINKDB_HOST": os.environ.get("RETHINKDB_HOST", "isard-db"),
            "RETHINKDB_PORT": os.environ.get("RETHINKDB_PORT", "28015"),
            "RETHINKDB_DB": os.environ.get("RETHINKDB_DB", "isard"),
            "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO"),
            "WEBAPP_ADMIN_PWD": os.environ.get("WEBAPP_ADMIN_PWD", False),
        }


class Certificates(object):
    def __init__(self, pool="default"):
        self.pool = pool
        self.ca_file = "/certs/ca-cert.pem"
        self.server_file = "/certs/server-cert.pem"
        cfg = loadConfig()
        self.cfg = cfg.cfg()
        self.check_db()

    def check_db(self):
        ready = False
        while not ready:
            try:
                self.conn = r.connect(
                    host=self.cfg["RETHINKDB_HOST"],
                    port=self.cfg["RETHINKDB_PORT"],
                    db=self.cfg["RETHINKDB_DB"],
                ).repl()
                print("Database server OK")
                list(r.db("isard").table_list().run(self.conn))
                ready = True
            except Exception as e:
                print(
                    "Certificates error: Database server "
                    + self.cfg["RETHINKDB_HOST"]
                    + ":"
                    + self.cfg["RETHINKDB_PORT"]
                    + " not present. Waiting to be ready"
                )
                time.sleep(0.5)
        ready = False

    def get_viewer(self, update_db=False):
        if update_db is False:
            return self.__process_viewer()
        else:
            viewer = self.__process_viewer()
            return self.__update_hypervisor_pool(viewer)

    def update_hyper_pool(self):
        viewer = self.__process_viewer()
        return self.__update_hypervisor_pool(viewer)

    def __process_viewer(self):
        ca_cert = server_cert = []
        try:
            ca_cert = pem.parse_file(self.ca_file)
        except:
            ca_cert = []
        ca_cert = False if len(ca_cert) == 0 else ca_cert[0].as_text()

        try:
            server_cert = pem.parse_file(self.server_file)
        except:
            server_cert = []
        server_cert = False if len(server_cert) == 0 else server_cert[0].as_text()

        if server_cert is False:
            print("No valid certificate found in /opt/isard/certs/viewers")
            return {
                "defaultMode": "Insecure",
                "certificate": False,
                "server-cert": False,
                "host-subject": False,
                "notAfter": "",
                "domain": False,
            }

        db_viewer = self.__get_hypervisor_pool_viewer()
        if server_cert == db_viewer["server-cert"]:
            if not db_viewer.get("notAfter", False):
                db_viewer["notAfter"] = datetime.datetime.strptime(
                    crypto.load_certificate(
                        crypto.FILETYPE_PEM, open(self.server_file).read()
                    )
                    .get_notAfter()
                    .decode("utf-8"),
                    "%Y%m%d%H%M%S%fZ",
                ).strftime("%Y-%m-%d")
            return db_viewer

        """From here we have a valid server_cert that has to be updated"""
        server_cert_obj = crypto.load_certificate(
            crypto.FILETYPE_PEM, open(self.server_file).read()
        )

        if ca_cert is False:
            """NEW VERIFIED CERT"""
            print("Seems a trusted certificate...")
            if self.__extract_ca() is False:
                print(
                    "Something failed while extracting ca root cert from server-cert.pem!!"
                )
                return {
                    "defaultMode": "Insecure",
                    "certificate": False,
                    "server-cert": False,
                    "host-subject": False,
                    "notAfter": "",
                    "domain": "ERROR IMPORTING CERTS",
                }
            print("Domain: " + server_cert_obj.get_subject().CN)
            return {
                "defaultMode": "Secure",
                "certificate": False,
                "server-cert": server_cert,
                "host-subject": False,
                "notAfter": datetime.datetime.strptime(
                    server_cert_obj.get_notAfter().decode("utf-8"), "%Y%m%d%H%M%S%fZ"
                ).strftime("%Y-%m-%d"),
                "domain": server_cert_obj.get_subject().CN,
            }
        else:
            """NEW SELF SIGNED CERT"""
            print("Seems a self signed certificate")
            ca_cert_obj = crypto.load_certificate(
                crypto.FILETYPE_PEM, open(self.ca_file).read()
            )
            hs = ""
            for t in server_cert_obj.get_subject().get_components():
                hs = hs + t[0].decode("utf-8") + "=" + t[1].decode("utf-8") + ","
            print("Domain: " + ca_cert_obj.get_subject().CN)
            return {
                "defaultMode": "Secure",
                "certificate": ca_cert,
                "server-cert": server_cert,
                "host-subject": hs[:-1],
                "notAfter": datetime.datetime.strptime(
                    server_cert_obj.get_notAfter().decode("utf-8"), "%Y%m%d%H%M%S%fZ"
                ).strftime("%Y-%m-%d"),
                "domain": ca_cert_obj.get_subject().CN,
            }

    def __extract_ca(self):
        try:
            certs = pem.parse_file(self.server_file)
        except:
            print("Could not find server-cert.pem file in folder!!")
            return False
        if len(certs) < 2:
            print(
                "The server-cert.pem certificate is not the full chain!! Please add ca root certificate to server-cert.pem chain."
            )
            return False
        ca = certs[-1].as_text()
        if os.path.isfile(self.ca_file):
            print(
                "The ca-cert.file already exists. This ca extraction can not be done."
            )
            return False
        try:
            with open(self.ca_file, "w") as caFile:
                res = caFile.write(ca)
        except:
            print("Unable to write to server-cert.pem file!!")
            return False
        return ca

    def __get_hypervisor_pool_viewer(self):
        try:
            viewer = (
                r.table("hypervisors_pools")
                .get(self.pool)
                .pluck("viewer")
                .run()["viewer"]
            )
            if "server-cert" not in viewer.keys():
                viewer["server-cert"] = False
            return viewer
        except:
            return {
                "defaultMode": "Insecure",
                "certificate": False,
                "server-cert": False,
                "host-subject": False,
                "notAfter": "",
                "domain": False,
            }

    def __update_hypervisor_pool(self, viewer):
        self.check_db()
        r.table("hypervisors_pools").get(self.pool).update({"viewer": viewer}).run()
        if viewer["defaultMode"] == "Secure" and viewer["certificate"] is False:
            try:
                if (
                    r.table("hypervisors")
                    .get("isard-hypervisor")
                    .run()["viewer_hostname"]
                    == "isard-hypervisor"
                ):
                    r.table("hypervisors").get("isard-hypervisor").update(
                        {"viewer_hostname": viewer["domain"]}
                    ).run()
            except Exception as e:
                print(
                    "Could not update hypervisor isard-hypervisor with certificate name. You should do it through UI"
                )
        print("Certificates updated in database")
        return True


class Password(object):
    def __init__(self):
        None

    def valid(self, plain_password, enc_password):
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), enc_password.encode("utf-8")
        )

    def encrypt(self, plain_password):
        return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode(
            "utf-8"
        )

    def generate_human(self, length=6):
        chars = string.ascii_letters + string.digits + "!@#$*"
        rnd = random.SystemRandom()
        return "".join(rnd.choice(chars) for i in range(length))


def gen_random_mac():
    mac = [
        0x52,
        0x54,
        0x00,
        random.randint(0x00, 0x7F),
        random.randint(0x00, 0xFF),
        random.randint(0x00, 0xFF),
    ]
    return ":".join(map(lambda x: "%02x" % x, mac))


# Being used in an old upgrade, so keeping with old interfaces_mac key
def gen_new_mac():
    domains_hardware = list(
        r.table("domains")
        .get_all("desktop", index="kind")
        .pluck("id", {"create_dict": {"hardware": {"interfaces_mac": True}}})
        .run()
    )

    hardware_macs = [
        dom["create_dict"]["hardware"]["interfaces_mac"]
        for dom in domains_hardware
        if dom.get("create_dict", {}).get("hardware", {}).get("interfaces_mac")
    ]
    all_macs = [item for sublist in hardware_macs for item in sublist]
    new_mac = gen_random_mac()
    # 24 bit combinations = 16777216 ~= 16.7 million. Is this enough macs for your system?
    # Take into account that each desktop could have múltime interfaces... still milions of unique macs
    while all_macs.count(new_mac) > 0:
        new_mac = gen_random_mac()
    return new_mac
