import sys
import traceback

from setup import DeleteHypervisor, DisableHypervisor, EnableHypervisor, SetupHypervisor

if not len(sys.argv):
    print("You should pass action: setup, enable, delete")
    exit(1)

### Setup hypervisor + certificates
if sys.argv[1] == "setup":
    try:
        SetupHypervisor()
    except:
        print(traceback.format_exc())
        exit(1)

if sys.argv[1] == "delete":
    try:
        DeleteHypervisor()
    except:
        print(traceback.format_exc())
        exit(1)

if sys.argv[1] == "enable":
    try:
        print(EnableHypervisor())
    except:
        print(traceback.format_exc())
        exit(1)

if sys.argv[1] == "disable":
    try:
        print(DisableHypervisor())
    except:
        print(traceback.format_exc())
        exit(1)
