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

    cmds = [
        cmd_guest_notifier_linux(message_decoded),
        cmd_guest_notifier_windows(message_decoded),
    ]

    failed = True
    cmd = 0
    command_status = {}
    while failed and cmd <= len(cmds) - 1:
        command_exec = cmds[cmd]

        try:
            logs.workers.error(command_exec)
            command_exec_response = qemuAgentCommand(
                domain, json.dumps(command_exec), 30, 0
            )

            failed = False
            command_status = {
                "execute": "guest-exec-status",
                "arguments": {
                    "pid": json.loads(command_exec_response)
                    .get("return", {})
                    .get("pid"),
                },
            }

        except libvirtError as error:
            logs.workers.error(
                f"libvirt error trying to notify desktop {desktop_id} "
                f'with "{message_decoded}": {error}'
            )

        cmd = cmd + 1

    if command_status != {} and not command_status.get("exitcode"):
        logs.workers.info(
            f"Domain {desktop_id} was successfully notified "
            f'with message "{message_decoded}"'
        )
        return True

    else:
        logs.workers.error(
            f"Failed to notify desktop {desktop_id} "
            f'with message "{message_decoded}" with '
            f'error "{base64.b64decode(command_status.get("err-data", "")).decode()}"'
        )
        return False


def cmd_guest_notifier_windows(message):
    return {
        "execute": "guest-exec",
        "arguments": {
            "path": "C:/Windows/System32/msg.exe",
            "arg": ["*", message],
            "capture-output": True,
        },
    }


def cmd_guest_notifier_linux(message):
    title = "IsardVDI Notification"
    shellscript = f"""
        exit_code=0;

        # Notify the users on the tty
        echo '{message}' | wall || exit_code=$?;

        # Notify the users using a graphical interface
        if which sw-notify-send; then
            CMD="$(which sw-notify-send) -a IsardVDI -u CRITICAL '{title}' '{message}'"

        elif which notify-send; then
            CMD="$(which notify-send) -a IsardVDI -u CRITICAL '{title}' '{message}'"

        elif which gdbus; then
            CMD="gdbus call --session \
                --dest=org.freedesktop.Notifications \
                --object-path=/org/freedesktop/Notifications \
                --method=org.freedesktop.Notifications.Notify \
                'IsardVDI' 0 '' '{title}' '{message}' \
                '[]' '{{}}' 5000"

        else
            echo "No graphical notification program found!"
            exit 1
        fi

        for uid in $(ls /run/user/); do
            runuser -l $(getent passwd "$uid" | cut -d: -f1) -c "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus $CMD || exit_code=$?"
        done

        exit $exit_code
    """.encode()

    command_exec = {
        "execute": "guest-exec",
        "arguments": {
            "path": "/bin/sh",
            "input-data": base64.b64encode(shellscript).decode(),
            "capture-output": True,
        },
    }
    return command_exec
