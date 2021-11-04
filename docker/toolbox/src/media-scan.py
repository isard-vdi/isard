import json
import os
import sys
import tarfile
import traceback
from pathlib import Path

from api_client import ApiClient
from isard_virt_lib import IsardVirtLib

ivl = IsardVirtLib()

# Instantiate connection
try:
    apic = ApiClient()
except:
    raise

BASE_PATH = "/isard"

media_ext = [".iso", ".fd"]
disk_ext = [".qcow", ".qcow2"]
compress_ext = [".tar.gz", ".gz"]


def getopts(argv):
    opts = {}
    while argv:
        if argv[0][0] == "-":
            if len(argv) == 1:
                opts[argv[0]] = ""
            else:
                opts[argv[0]] = argv[1]
        argv = argv[1:]
    return opts


size_suffixes = ["B", "KB", "MB", "GB", "TB", "PB"]


def humansize(nbytes):
    i = 0
    while nbytes >= 1024 and i < len(size_suffixes) - 1:
        nbytes /= 1024.0
        i += 1
    f = ("%.2f" % nbytes).rstrip("0").rstrip(".")
    return "%s%s" % (f, size_suffixes[i])


def process_items(dir_name, suffixes, endpoint):
    print("#### Scanning " + dir_name + " ####")
    list_of_files = {
        str(p.resolve()) for p in Path(dir_name).glob("**/*") if p.suffix in suffixes
    }
    files_with_size = [
        (file_path, humansize(os.stat(file_path).st_size))
        for file_path in list_of_files
    ]
    for f in list_of_files:
        print("- " + f)
    print(
        "A total of "
        + str(len(list_of_files))
        + " files were found in "
        + dir_name
        + ". Api will process new ones.\n"
    )
    try:
        data = apic.post(endpoint, data=json.dumps(files_with_size))
        if not data:
            print("Scanning Media: Api does not answer OK...")
    except:
        print("Scanning Media: Could not contact api...")


def process_item(file_path):
    if os.environ.get("DESTINATION") == BASE_PATH:
        file_path = os.environ.get("FILE", file_path)
    else:
        file_path = os.environ.get("DESTINATION")
    print("#### Processing new file ####")
    print("- " + file_path)

    if file_path.startswith(BASE_PATH + "/media"):
        if "." + file_path.split(".")[-1] not in media_ext:  # +compress_ext:
            print(
                "MEDIA ERROR: The file "
                + file_path
                + " does not match extensions: "
                + str(media_ext)
            )
            exit(1)
    elif file_path.startswith(BASE_PATH + "/groups"):
        if "." + file_path.split(".")[-1] not in disk_ext:  # +compress_ext:
            print(
                "DISKS ERROR: The file "
                + file_path
                + " does not match extensions: "
                + str(disk_ext)
            )
            exit(1)
    else:
        print(
            "Can only process media and groups folders. You tried to add: " + file_path
        )
        exit(1)

    # uncompress(file_path)
    endpoint = (
        "hypervisor/media_found"
        if file_path.startswith(BASE_PATH + "/media")
        else "hypervisor/disks_found"
    )
    file_with_size = [(file_path, humansize(os.stat(file_path).st_size))]
    try:
        data = apic.post(endpoint, data=json.dumps(file_with_size))
        if not data:
            print("Process item: Api does not answer OK...")
        print("Api processed the file.")
    except:
        print("Process item: Could not contact api...")


def delete_item(file_path):
    file_path = os.environ.get("FILE", file_path)
    print("#### Deleting file ####")
    print("- " + file_path)

    if file_path.startswith(BASE_PATH + "/media"):
        if "." + file_path.split(".")[-1] not in media_ext:  # +compress_ext:
            print(
                "MEDIA ERROR: The file "
                + file_path
                + " does not match extensions: "
                + str(media_ext)
            )
            exit(1)
    elif file_path.startswith(BASE_PATH + "/groups"):
        if "." + file_path.split(".")[-1] not in disk_ext:  # +compress_ext:
            print(
                "DISKS ERROR: The file "
                + file_path
                + " does not match extensions: "
                + str(disk_ext)
            )
            exit(1)
    else:
        print(
            "Can only delete media and groups folders. You tried to add: " + file_path
        )
        exit(1)

    # uncompress(file_path)
    endpoint = "hypervisor/media_delete"
    try:
        data = apic.post(endpoint, data=json.dumps([file_path]))
        if not data:
            print("Delete item: Api does not answer OK...")
        print("Api deleted the file.")
    except:
        print("Delete item: Could not contact api...")


def uncompress(file_path):
    # tar cvf toolbox/thetemp.tar.gz groups/default/default/local/admin-admin/group_disk.qcow2 templates/default/default/local/admin-admin/nova_template2.qcow2
    if "." + file_path.split(".")[-1] in compress_ext:
        if file_path.endswith(".tar.gz"):
            with tarfile.open(file_path) as tar:
                for tf in tar.getnames():
                    if tf.startswith("media/") and tf.split(".")[-1] in media_ext:
                        continue
                    if tf.startswith("groups/") and tf.split(".")[-1] in disk_ext:
                        continue
                    if tf.startswith("templates/") and tf.split(".")[-1] in disk_ext:
                        continue
                    print("Incorrect path/ext match in file inside tar: " + tf)
                    return False

            tar = tarfile.open(file_path, "r:gz")
            tar.extractall(BASE_PATH + "/")
            tar.close()
            os.remove(file_path)


def compress(file_path):
    # tar cvf toolbox/thetemp.tar.gz groups/default/default/local/admin-admin/group_disk.qcow2 templates/default/default/local/admin-admin/nova_template2.qcow2

    if "." + file_path.split(".")[-1] in disk_ext:
        chain = ivl.qcow_get_full_chain(file_path)
        with tarfile.open(os.path.splitext(file_path)[0] + ".tar.gz", "w:gz") as tar:
            for c in chain:
                tar.add(c, arcname=os.path.basename(c))
    else:
        print("Incorrect path/ext match in file inside tar: " + tf)
        return False


if __name__ == "__main__":
    from sys import argv

    myargs = getopts(argv)
    if not len(myargs) or "-h" in myargs or "--help" in myargs:
        print("Usage: media-scan.py [args]")
        print(" Args:")
        print("   -f/--file <filename>      Will add filename to media.")
        print("   -d/--delete <filename>    Will delete filename to media.")
        print(
            "   -m/--media                Will scan all media path an add missing to media."
        )
        print(
            "   -g/--groups               Will scan all groups path an add missing to media."
        )
        print(
            "   -a/--all                  Will scan media and groups paths an add missing to media."
        )

    if ("-a" in myargs or "--all" in myargs) and len(myargs) > 1:
        print("-a/--all can not be mixed with other arguments")
        exit(1)

    if "-f" in myargs or "--file" in myargs:
        process_item(myargs.get("-f", myargs.get("--file")))
    if "-d" in myargs or "--delete" in myargs:
        delete_item(myargs.get("-d", myargs.get("--delete")))
    if "-m" in myargs or "--media" in myargs:
        process_items(BASE_PATH + "/media", [".iso", ".fd"], "hypervisor/media_found")
    if "-g" in myargs or "--groups" in myargs:
        process_items(
            BASE_PATH + "/groups", [".qcow", ".qcow2"], "hypervisor/disks_found"
        )
    if "-a" in myargs or "--all" in myargs:
        process_items(BASE_PATH + "/media", [".iso", ".fd"], "hypervisor/media_found")
        process_items(
            BASE_PATH + "/groups", [".qcow", ".qcow2"], "hypervisor/disks_found"
        )
