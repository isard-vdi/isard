import os, json, sys
import traceback
from api_client import ApiClient

from pathlib import Path

# Instantiate connection
try:
    apic=ApiClient()
except:
    raise

suffixes = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
def humansize(nbytes):
    i = 0
    while nbytes >= 1024 and i < len(suffixes)-1:
        nbytes /= 1024.
        i += 1
    f = ('%.2f' % nbytes).rstrip('0').rstrip('.')
    return '%s%s' % (f, suffixes[i])

def process_items(dir_name,suffixes,endpoint):
    print('#### Scanning '+dir_name+' ####')
    list_of_files = {str(p.resolve()) for p in Path(dir_name).glob("**/*") if p.suffix in suffixes}
    # print(list_of_files)
    files_with_size = [ (file_path, humansize(os.stat(file_path).st_size)) 
                        for file_path in list_of_files ]
    for f in list_of_files:
        print('- '+f)
    print('A total of '+str(len(list_of_files))+' files were found in '+dir_name+'. Api will process new ones.\n')
    try:
        data=apic.post(endpoint,data=json.dumps(files_with_size))
        if not data:
            print('Scanning Media: Api does not answer OK...')
    except:
        print('Scanning Media: Could not contact api...')
        
subpath=sys.argv[1:]
if not len(subpath):
    print('You should pass as an argument: all, media or groups')
    exit(1)
if subpath[0] not in ['all','media','groups']:
    print('Incorrect argument. Valid arguments are: all, media or groups')
    exit(1)

if subpath[0] == 'media': process_items('/isard/media',[".iso", ".fd"],'hypervisor/media_found')
## It will fail to create a desktop from a templates disk, obviously, if engine does not move it to groups folder.
# if subpath[0] == 'templates': process_items('/isard/templates',[".qcow", ".qcow2"],'hypervisor/disks_found')
if subpath[0] == 'groups': process_items('/isard/groups',[".qcow", ".qcow2"],'hypervisor/disks_found')
if subpath[0] == 'all': 
    process_items('/isard/media',[".iso", ".fd"],'hypervisor/media_found')
    # process_items('/isard/templates',[".qcow", ".qcow2"],'hypervisor/disks_found')
    process_items('/isard/groups',[".qcow", ".qcow2"],'hypervisor/disks_found')
