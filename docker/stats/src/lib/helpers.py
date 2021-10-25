# ~ import pprint
import subprocess

# ~ import re
# ~ from pprint import pprint


def execute(cmd):
    popen = subprocess.Popen(cmd, stdout=subprocess.PIPE, universal_newlines=True)
    for stdout_line in iter(popen.stdout.readline, ""):
        yield stdout_line
    popen.stdout.close()
    return_code = popen.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, cmd)


def cu(value):
    if "M" in value:
        return str(1048576 * float(value.split("M")[0]))
    if "k" in value:
        return str(1024 * float(value.split("k")[0]))
    if "G" in value:
        return str(1073741824 * float(value.split("G")[0]))
    if "B" in value:
        return value.split("B")[0]
    return value
