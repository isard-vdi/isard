import pyqcow
import time,os,json
import contextlib
import guestfs

class QcowFileLockedError(Exception):
    def __init__(self, file_path, message=False):
        if not message: message = "The "+file_path+" is locked."
        super().__init__(message)

@contextlib.contextmanager
def Qcow(file_path):
    qcow_file = pyqcow.file()
    qcow_file.open(file_path)
    if qcow_file.is_locked(): raise QcowFileLockedError(file_path)
    yield qcow_file
    qcow_file.close()

@contextlib.contextmanager
def Guestfs(file_path,readonly=1):
    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(file_path, readonly=readonly)
    g.launch()
    yield g
    g.umount_all()

class IsardVirtLib():
    def __init__(self):
        None

    def qcow_get_size(self,file_path):
        with Qcow(file_path) as q: return q.get_media_size()

    def qcow_get_full_chain(self,file_path):
        backing = [file_path]
        bc = file_path
        while bc != None:
            with Qcow(bc) as q: bc = q.get_backing_filename()
            if bc != None: backing.append(bc)
        return backing

    def qcow_get_disks(self,file_path):
        with Guestfs(file_path) as g:
            print('Devices found:')
            print(g.list_devices())
            print('Partitions found:')
            print(g.list_partitions())
            print('Filesystems found:')
            print(g.list_filesystems())

if __name__ == '__main__':
    file_path = "/isard/groups/default/default/local/admin-admin/downloaded_ubuntu_20_04_lts.qcow2"
    ivl = IsardVirtLib()

    # print(ivl.qcow_get_disks(file_path))

    # print(ivl.qcow_get_size(file_path))
    # print(ivl.qcow_get_full_chain(file_path))

    # print(ivl.qcow_get_applications(file_path))