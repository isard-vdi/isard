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

import sys

import guestfs


def inspect_disk(path):
    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(path, readonly=1)
    g.launch()
    roots = g.inspect_os()
    disks = {"devices": roots}
    for root in roots:
        disks[root] = {
            "product_name": "%s" % (g.inspect_get_product_name(root)),
            "version": "%d.%d"
            % (g.inspect_get_major_version(root), g.inspect_get_minor_version(root)),
            "type": "%s" % (g.inspect_get_type(root)),
            "distro": "%s" % (g.inspect_get_distro(root)),
        }
    g.umount_all()
    return disks
