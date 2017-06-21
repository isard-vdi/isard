# Isard**VDI**
VDI deployment based on KVM Linux. Users create and share desktops with any OS and software through templating in seconds. The Isard engine orchestrates hypervisors and focuses on optimizing desktop virtualization performance.

Isard**VDI** was born with the aim of creating a free software alternative to privative virtual desktop solutions such as Citrix XenDesktops or VMware Horizon.

Isard**VDI** directly manages KVM Linux hypervisors using libvirt.

A web application that allows agile desktop deployments and centralized hypervisors management.

Use only for testing purposes. Work in progress. 

## Features
##### Benefits to users
+ Linux and Windows virtual desktops
+ Template creation from desktop snapshot
+ Template shareable with other users and groups
+ Web interface with real time events for improved user experience
+ Spice, HTML5, VNC and rDesktop viewers available
+ USB devices redirection in spice viewer
+ Kiosk mode. Create disposable desktops
+ Multiple resoure permission levels
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

### Support/Contact
Please send us an email to info@isardvdi.com if you have any questions 
