# Isard**VDI**

Open Source Virtual Desktops Infrastructure based on KVM Linux and dockers. 

- Engine that monitors hypervisors and domains (desktops)
- Websocket user interface with real time events.

## Quick Start

### Bring it up

Start containers with **docker-compose up -d**

Connect to **https://<ip|domain>** and follow wizard.

### Desktops

There will be two minimal oldstyle desktops that you can start and connect to.

If you want to create your own desktop:

1. Go to Media menu and download an ISO
2. After the download is finished it will show a desktop icon where you can create the desktop.

You will find the created desktop in Desktops menu.

### Templates

Create a template from a desktop:

1. Open desktop details and click on Template it button.
2. Fill in the form and click on create.

It will create a template from that desktop as it was now. You can create as many desktops identical to that template.

### Updates

In Updates menu you will have access to different resources you can download from our IsardVDI updates server.

![Main admin screen](docs/images/main.png?raw=true "Main admin")

## Documentation

- https://isardvdi.readthedocs.io/en/latest/


## Features
##### Benefits to users
+ Linux and Windows virtual desktops
+ Template creation from desktop snapshot
+ Template shareable with other users and groups
+ Web interface with real time events for improved user experience
+ Spice, HTML5, VNC and rDesktop viewers available
+ USB devices redirection in spice viewer
+ Kiosk mode. Create disposable desktops
+ Multiple resource permission levels
+ Quotas for desktops, running desktops, templates and iso files

##### Benefits to administrators
+ Not tied to any propietary hardware.
+ Not tied to any hypervisor/nas distro
+ Desktops small disk footprint (we handle over 1400 desktops in 5TB)
+ Hypervisors can be grouped in pools
+ Manage thousands of desktops from a single dashboard
+ User access management with database, ldap, oauth2, ...
+ Quotas at roles, categories, groups and user levels
+ Granular permissions for all resources
+ Customizable distributed storage for optimal performance
+ Two level cache system
+ Kiosk mode, with customized templates and menus based on networks
+ Vlan mapping per virtual desktop
+ High end nginx performance proxy ready
+ Available cluster database backend
+ Grafana module included
+ Continuous development and test in real production environtment

## Screenshots and videos: 

Go to [Webpage project](http://www.isardvdi.com/)

#### Future lines and roadmap

We are currently developing new features and continuosly testing it in a real production environtment.
Remote organization access and intensive 3D rendering (among other features) are being tested.

#### Success story

Our organization bet two years ago for our proposal to implement a system of virtual desks. We evaluated the existing systems in the market and verified that they were not perfectly adapted to the educational environment.

It was then when we created a proof of concept with KVM in linux that turned out to be successful.

In September of 2015 we managed to put into operation a first version of the software with an infrastructure fully assembled and optimized by us, since the costs had to be extremely reduced compared to the existing commercial systems.

Teachers and students soon adopted this solution as it provided them with a greater degree of autonomy and agility. Only with the mouth-ear we manage to reach the spectacular numbers of use that we have in our organization.

+ Our current production environtment has more than 800 users and 1400 virtual desktops. 
+ We have teachers and students using it in a day basis seamlesly in classrooms around buildings.
+ We managed to maintain a very low costs

In 2016 we focused all our efforts on a solid and versatile software that materialized in IsardVDI, a software thought from the requirements of the educational system. 

### Authors
+ Josep Maria Viñolas Auquer
+ Alberto Larraz Dalmases

### Contributors
+ Daniel Criado Casas
+ Néfix Estrada

### Support/Contact
Please send us an email to info@isardvdi.com if you have any questions 
