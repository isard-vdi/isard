import os
import sys


def check_if_debugging():
    if os.environ.get("JETBRAINS_REMOTE_RUN", 0) == "1":
        print("DEBUG REMOTE WITH PYCHARM")
        if load_environ_from_file() is False:
            sys.exit()


def load_environ_from_file(path_loadenv="/root/loadenv"):
    try:
        f = open(path_loadenv)
        l = f.readlines()
        f.close()
    except:
        print(
            "FILE /root/loadenv NOT FOUND, TRY TO EXECUTE: for i in $(env); do echo $i>>/root/loadenv; done"
        )
        return False
    for i in l:
        k = i[: i.find("=")]
        v = i[i.find("=") + 1 :].strip()
        if k not in os.environ.keys():
            os.environ[k] = v
        else:
            print(
                f"ENV not set to variable {k}, is defined with value {os.environ[k]} and value in file loadenv is {v}"
            )
    return True
