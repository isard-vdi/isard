# Isard**VDI**

<img align="right" src="webapp/webapp/webapp/static/img/isard.png" alt="IsardVDI Logo" width="150px;">

[![](https://img.shields.io/github/release/isard-vdi/isard.svg)](https://github.com/isard-vdi/isard/releases) [![](https://img.shields.io/badge/docker--compose-ready-blue.svg)](https://github.com/isard-vdi/isard/blob/master/docker-compose.yml) [![](https://img.shields.io/badge/docs-latest-brightgreen.svg)](https://isardvdi.readthedocs.io/en/latest/) [![](https://img.shields.io/badge/license-AGPL%20v3.0-brightgreen.svg)](https://github.com/isard-vdi/isard/blob/master/LICENSE)

Open Source KVM Virtual Desktops based on KVM Linux and dockers. 

- Engine that monitors hypervisors and domains (desktops)

- Websocket user interface with real time events.

- HTML5 and native SPICE client viewers

  **IMPORTANT NOTE**: You cannot migrate from the version 1 to version 2, since there are many structural changes. You should backup your XML definition files and QCOW disks and import them in the new version.

# Documentation

Follow the extensive documentation to get the most of your installation:

- [https://isardvdi.readthedocs.io/en/develop/](https://isardvdi.readthedocs.io/en/develop/)

## Quick Start with docker & docker-compose

### 1) *INSTALL docker & docker-compose*
- https://docs.docker.com/install/
- https://docs.docker.com/compose/install/

### 2) **Pull images and bring it up**:

```
wget https://isardvdi.com/docker-compose.yml
docker-compose pull
docker-compose up -d
```

Connect to **https://<ip|domain>**/isard-admin with default user *admin* and password *IsardVDI*

NOTE: 

- All data will be created in your host /opt/isard folder
- Logs will be at /opt/isard-local

## Custom build

There is an **isardvdi.cfg.example** file that you can copy to **isardvdi.cfg** and edit to fit your requirements. After that you can create your own *docker-compose.yml* file from that config by issuing *build.sh* script.

Then bring it up with **docker-compose up -d**

Please read the [documentation](https://isardvdi.readthedocs.io/en/develop/install/install/#main-parameters) to configure your IsardVDI installation

### Desktops

You can directly go to *Updates* menu and download and test precreated desktops.

If you want to create your own desktop:

1. Go to Media menu and download an ISO
2. After the download is finished it will show a desktop icon where you can create the desktop.

You will find the created desktop in Desktops menu. Implemented encrypted viewers:

- HTML5 Viewer
- Native virt-viewer SPICE protocol.

### Templates

Create a template from a desktop:

1. Open desktop details and click on Template it button.
2. Fill in the form and click on create.

It will create a template from that desktop as it was now. You can create as many desktops identical to that template.

### Updates

In Updates menu you will have access to different resources you can download from our IsardVDI updates server.

![Main admin screen](https://isardvdi.readthedocs.io/en/latest/images/main.png)

## Documentation

- https://isardvdi.readthedocs.io/en/latest/

## More info: 

Go to [IsardVDI Project website](http://www.isardvdi.com/)

### Authors
+ Josep Maria Viñolas Auquer
+ Alberto Larraz Dalmases
+ Néfix Estrada

### Contributors
+ Daniel Criado Casas

### Support/Contact
Please email us at info@isardvdi.com if you have any questions or fill in an issue.

### Social Networks
Mastodon: [@isard@fosstodon.org](https://fosstodon.org/@isard)  
Twitter: [@isard_vdi](https://twitter.com/isard_vdi)

