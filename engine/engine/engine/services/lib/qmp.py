#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2022 Simó Albert i Beltran
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import base64
import json
import os
import pathlib
import subprocess

from engine.services.db.domains import PersonalUnit as DbPersonalUnit
from engine.services.db.domains import get_personal_unit_from_domain
from engine.services.log import logs
from libvirt import libvirtError, virDomain
from libvirt_qemu import qemuAgentCommand

NOTIFIER_CMD_LINUX = None
with open(
    os.path.join(pathlib.Path(__file__).parent.resolve(), "./qmp/notifier_linux.sh")
) as f:
    NOTIFIER_CMD_LINUX = f.read()

NOTIFIER_CMD_WINDOWS = None
with open(
    os.path.join(pathlib.Path(__file__).parent.resolve(), "./qmp/notifier_windows.bat")
) as f:
    NOTIFIER_CMD_WINDOWS = f.read()

PERSONAL_UNIT_CMD_LINUX = None
with open(
    os.path.join(
        pathlib.Path(__file__).parent.resolve(), "./qmp/personal_unit_linux.sh"
    )
) as f:
    PERSONAL_UNIT_CMD_LINUX = f.read()

PERSONAL_UNIT_CMD_WINDOWS = None
with open(
    os.path.join(
        pathlib.Path(__file__).parent.resolve(), "./qmp/personal_unit_windows.bat"
    )
) as f:
    PERSONAL_UNIT_CMD_WINDOWS = f.read()


def exec_commands(domain: virDomain, desktop_id: str, cmds):
    """
    Execute a list of commands in the specified domain
    :param domain: domain where the commands are going to be executed
    :param cmds: commands that are going to be executed
    """
    failed = True
    cmd = 0
    command_status = {}
    while failed and cmd <= len(cmds) - 1:
        command_exec = cmds[cmd]
        cmd = cmd + 1

        try:
            raw_cmd = [
                "virsh",
                f"--connect={domain._conn.getURI()}",
                "qemu-agent-command",
                f"--domain={domain.name()}",
                f"--cmd={json.dumps(command_exec)}",
            ]
            logs.workers.debug(raw_cmd)

            result = subprocess.run(raw_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                continue

            logs.workers.debug(str(result.stdout))

            command_status = {
                "execute": "guest-exec-status",
                "arguments": {
                    "pid": json.loads(str(result.stdout)).get("return", {}).get("pid"),
                },
            }
            raw_cmd = [
                "virsh",
                f"--connect={domain._conn.getURI()}",
                "qemu-agent-command",
                f"--domain={domain.name()}",
                f"--cmd={json.dumps(command_status)}",
            ]
            logs.workers.debug(raw_cmd)

            result = subprocess.run(raw_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                continue

            failed = False

            logs.workers.debug("RESULT => " + str(result.stdout))

        except Exception as error:
            logs.workers.error(
                f"libvirt error trying to execute command in desktop {desktop_id} "
                f"with: {error}"
            )

    if command_status != {} and not command_status.get("exitcode"):
        return None

    return command_status


class Notifier:
    @staticmethod
    def notify_desktop(domain: virDomain, message: bytes):
        """
        Notify desktop with a message

        Guest should have qemu-guest-agent and libnotify-bin installed
        and the following libvirt xml.

        <channel type="unix">
            <source mode="bind"/>
            <target type="virtio" name="org.qemu.guest_agent.0"/>
        </channel>

        :param domain: domain to be notified
        :type domain: libvirt.virDomain
        :param message: message to notify
        "type message: bytes
        """
        desktop_id = domain.name()
        message_decoded = base64.b64decode(message).decode()
        logs.workers.debug(
            f'Notifying desktop {desktop_id} with message "{message_decoded}"'
        )

        cmds = [
            Notifier.cmd_linux(message_decoded),
            Notifier.cmd_windows(message_decoded),
        ]

        command_status = exec_commands(domain, desktop_id, cmds)
        if not command_status:
            logs.workers.info(
                f"Domain {desktop_id} was successfully notified "
                f'with message "{message_decoded}"'
            )

        else:
            logs.workers.error(
                f"Failed to notify desktop {desktop_id} "
                f'with message "{message_decoded}" with '
                f'error "{base64.b64decode(command_status.get("err-data", "")).decode()}"'
            )

    def cmd_windows(message):
        shellscript = NOTIFIER_CMD_WINDOWS.format(
            message=message,
        ).encode()

        return {
            "execute": "guest-exec",
            "arguments": {
                "path": "cmd.exe",
                "arg": ["/U"],
                "input-data": base64.b64encode(shellscript).decode(),
                "capture-output": True,
            },
        }

    def cmd_linux(message):
        shellscript = NOTIFIER_CMD_LINUX.format(
            title="IsardVDI Notification",
            message=message,
        ).encode()

        return {
            "execute": "guest-exec",
            "arguments": {
                "path": "/bin/sh",
                "input-data": base64.b64encode(shellscript).decode(),
                "capture-output": True,
            },
        }


class PersonalUnit:
    @staticmethod
    def connect_personal_unit(domain: virDomain):
        """
        Attempts to connect the personal unit of the user to the desktop
        """
        desktop_id = domain.name()

        logs.workers.debug(f'Attempting to connect {desktop_id} to the personal unit!"')

        unit = get_personal_unit_from_domain(desktop_id)
        if not unit:
            return

        cmds = [
            PersonalUnit.cmd_linux(unit),
            PersonalUnit.cmd_windows(unit),
        ]

        command_status = exec_commands(domain, desktop_id, cmds)
        if not command_status:
            logs.workers.error(
                f"Desktop {desktop_id} was successfully connected to the personal unit"
            )

        else:
            logs.workers.error(
                f"Failed to connect the desktop {desktop_id} "
                f"to the personal unit with"
                f'error "{base64.b64decode(command_status.get("err-data", "")).decode()}"'
            )

    def cmd_windows(unit: DbPersonalUnit):
        shellscript = PERSONAL_UNIT_CMD_WINDOWS.format(
            protocol="s" if unit["tls"] else "",
            verify_cert=unit["verify_cert"],
            user=unit["user_id"],
            password=unit["password"],
            host=unit["dav"],
        ).encode()

        return {
            "execute": "guest-exec",
            "arguments": {
                "path": "cmd.exe",
                "arg": ["/U"],
                "input-data": base64.b64encode(shellscript).decode(),
                "capture-output": True,
            },
        }

    def cmd_linux(unit: DbPersonalUnit):
        shellscript = PERSONAL_UNIT_CMD_LINUX.format(
            protocol="s" if unit["tls"] else "",
            verify_cert=unit["verify_cert"],
            user=unit["user_id"],
            password=unit["password"],
            host=unit["dav"],
        ).encode()

        return {
            "execute": "guest-exec",
            "arguments": {
                "path": "/bin/sh",
                "input-data": base64.b64encode(shellscript).decode(),
                "capture-output": True,
            },
        }
