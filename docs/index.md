# Isard**VDI**

Open Source VDI deployment based on KVM Linux. 

## What is it

A quick and real time web interface to manage your virtual desktops.

Bring it up:

```
git clone https://github.com/isard-vdi/isard
cd isard
docker-compose up -d
```

Connect with browser to the server and follow the wizard. You are ready 
to test virtual desktops:

- Start **demo desktops** and connect to it using your browser and spice or 
vnc protocol. Nothing to be installed, but already secured with certificates.
- Install virt-viewer and connect to it using the spice client. **Sound 
and USB** transparent plug will be available.

Download new precreated desktops, isos and lots of resources from the **Updates** menu.

Create your own desktop using isos downloaded from Updates or **Media** 
menu option. When you finish installing the operating system and 
applications create a **Template** and decide which users or categories 
you want to be able to create a desktop identical to that template. Thanks to the **incremental disk creation** all this can be done within 
minutes.

Don't get tied to an 'stand-alone' installation in one server. You can 
add more hypervisors to your **pool** and let IsardVDI decide where to 
start each desktop. Each hypervisor needs only the KVM/qemu and libvirt 
packages and SSH access. You should keep the storage shared between 
those hypervisors.

We currenly manage a **large IsardVDI infrastructure** at Escola del 
Treball in Barcelona. 3K students and teachers have IsardVDI available 
from our self-made pacemaker dual nas cluster and six hypervisors, 
ranging from top level intel server dual core mainboards to gigabyte 
gaming ones. 

We have experience in different **thin clients** that we use to lower renovation and 
consumption costs at classrooms.

[IsardVDI Project website](http://www.isardvdi.com/)

### Authors
+ Josep Maria Viñolas Auquer
+ Alberto Larraz Dalmases

### Contributors
+ Daniel Criado Casas
+ Néfix Estrada

### Support/Contact
Please send us an email to info@isardvdi.com if you have any questions or fill in an issue.
