#
#   Copyright © 2022 Josep Maria Viñolas Auquer
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import json
import os

if not os.environ.get("USAGE", "") == "devel":
    print("We don't allow doing this in production...")
    exit(1)
try:
    with open("/isard/logs/disks.json", "r") as read_file:
        disks = json.loads(read_file.read())
except:
    print(
        "You should put disks.json in /opt/isard-local/logs outside container (or /isard/logs inside storage container) and be sure you are in development mode"
    )
    exit(1)
disks_ok = len(disks["ok"])
i = 1
for disk in disks["ok"]:
    print("-------- DISKS OK " + str(i) + "/" + str(disks_ok) + " ----------------")
    i += 1
    for chain in reversed(disks["ok"][disk]):
        if os.path.isfile(chain["filename"]):
            print("Skipping existing: " + chain["filename"])
            continue
        if chain.get("full-backing-filename"):
            print(
                "creating disk with backing "
                + chain.get("full-backing-filename")
                + " for "
                + chain["filename"]
            )
            os.makedirs(os.path.dirname(chain["filename"]), exist_ok=True)
            os.system(
                "qemu-img create -F qcow2 -b "
                + chain["full-backing-filename"]
                + " -f qcow2 "
                + chain["filename"]
            )
        else:
            print("creating ROOT disk for " + chain["filename"])
            os.makedirs(os.path.dirname(chain["filename"]), exist_ok=True)
            os.system("qemu-img create -f qcow2 " + chain["filename"] + " 200K")

disks_err = len(disks["error"])
i = 1
for disk_err in disks["error"]:
    print(
        "-------- DISKS ERROR CHAIN "
        + str(i)
        + "/"
        + str(disks_err)
        + " ----------------"
    )
    disk = disks["error"][disk_err]
    if os.path.isfile(disk["filename"]):
        print("Skipping existing: " + disk["filename"])
        i += 1
        continue
    print(
        "Force creating ERROR disk for "
        + disk["filename"]
        + " with missing backing "
        + disk.get("full-backing-filename")
    )
    os.makedirs(os.path.dirname(disk["filename"]), exist_ok=True)
    os.system(
        "qemu-img create -F qcow2 -b "
        + disk["full-backing-filename"]
        + " -f qcow2 -u "
        + disk["filename"]
        + " 200K"
    )
    i += 1
