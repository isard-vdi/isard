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
from time import sleep

from engine.services.log import logs
from libvirt import libvirtError
from libvirt_qemu import qemuAgentCommand


def notify_desktop(domain, message):
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
    shellscript = f"""
        exit_code=0;
        echo '{message.decode()}' | base64 -d | wall || exit_code=$?;
        for uid in $(ls /run/user/);
        do
            sudo -u \\#$uid DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus \
                /usr/bin/notify-send -u critical \
                    \"$(echo '{message.decode()}' | base64 -d)\" \
            || exit_code=$?;
        done;
        exit $exit_code
    """.encode()

    command_exec = {
        "execute": "guest-exec",
        "arguments": {
            "path": "/usr/bin/sh",
            "input-data": base64.b64encode(shellscript).decode(),
            "capture-output": True,
        },
    }
    try:
        command_exec_response = qemuAgentCommand(
            domain, json.dumps(command_exec), 30, 0
        )
    except libvirtError as error:
        logs.workers.error(
            f"libvirt error trying to notify desktop {desktop_id} "
            f'with "{message_decoded}": {error}'
        )
        return False
    command_status = {
        "execute": "guest-exec-status",
        "arguments": {
            "pid": json.loads(command_exec_response).get("return", {}).get("pid"),
        },
    }
    exited = False
    tries = 5
    while not exited:
        try:
            command_status_result = qemuAgentCommand(
                domain, json.dumps(command_status), 30, 0
            )
        except libvirtError as error:
            logs.workers.error(
                "libvirt error collecting notification status for "
                f'desktop {desktop_id} with "{message_decoded}": {error}'
            )
            return False

        command_result = json.loads(command_status_result).get("return", {})
        exited = command_result.get("exited")
        if not exited:
            logs.workers.debug(
                f"Collecting notification status for desktop {desktop_id} "
                f'with "{message_decoded}", remaining {tries} tries: {command_result}'
            )
            sleep(1)
            tries -= 1
            if not tries:
                logs.workers.error(
                    f"Failed collecting notification status for desktop {desktop_id} "
                    f'with "{message_decoded}": {command_result}'
                )
                return False

    if not command_result.get("exitcode"):
        logs.workers.info(
            f"Domain {desktop_id} was successfully notified "
            f'with message "{message_decoded}"'
        )
        return True
    else:
        logs.workers.error(
            f"Failed to notify desktop {desktop_id} "
            f'with message "{message_decoded}" with '
            f'error "{base64.b64decode(command_result.get("err-data", "")).decode()}"'
        )
        return False
