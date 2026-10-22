# SPDX-License-Identifier: AGPL-3.0-or-later
"""Fake getent, ovs-vsctl and ovs-ofctl for geneve_tunnel_test.py; state in $FAKE_STATE."""

import json
import os
import sys

state_path = os.path.join(os.environ["FAKE_STATE"], "state.json")
with open(state_path) as f:
    st = json.load(f)
tool = sys.argv[1]
args = sys.argv[2:]
st["calls"].append([tool] + args)


def save():
    with open(state_path, "w") as f:
        json.dump(st, f)


if tool == "getent":
    ip = st["hosts"].get(args[1])
    save()
    if ip:
        print(f"{ip}  {args[1]}")
        sys.exit(0)
    sys.exit(2)

if tool == "ovs-ofctl":
    if args[0] == "add-flow":
        st["flows"].append(args[2])
    elif args[0] == "dump-flows":
        for fl in st["flows"]:
            print(" " + fl)
    save()
    sys.exit(0)

# ovs-vsctl
port = st["port"]
if args[:2] == ["--if-exists", "get"]:
    if port and args[4] == "type":
        print("geneve")
elif args[0] == "--may-exist" and args[1] == "add-port":
    opts = dict(a.split("=", 1) for a in args[7:] if "=" in a)
    st["port"] = {"options:remote_ip": opts["options:remote_ip"], "ofport": "5"}
elif args[0] == "get":
    if not port:
        save()
        sys.exit(1)
    key = args[3]
    print(port["ofport"] if key == "ofport" else '"%s"' % port.get(key, ""))
elif args[0] == "set":
    if not port:
        save()
        sys.exit(1)
    for a in args[3:]:
        k, v = a.split("=", 1)
        port[k] = v
save()
