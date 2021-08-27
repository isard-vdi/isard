import os, sys, json
from time import sleep
from pprint import pprint
import traceback

from setup import SetupHypervisor, EnableHypervisor, DeleteHypervisor
# from wireguard import SetupWireguard

if not len(sys.argv):
    print('You should pass action: setup, enable, delete')
    exit(1)

### Setup hypervisor + certificates
if sys.argv[1] == "setup":
    try:
        hyp_number=SetupHypervisor()
    except:
        print(traceback.format_exc())
        exit(1)
    
    # try:
    #     SetupWireguard(hyp_number)
    # except:
    #     print(traceback.format_exc())
    #     exit(1)

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
