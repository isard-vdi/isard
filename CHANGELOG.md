# IsardVDI Changelog

All notable changes to this project will be documented in this file.

## [4.4.1] - 2021-10-12

### Fixed

- Fix libwebsockets package for guacamole by upgrading alpine to 3.14

## [4.4.0] - 2021-10-11

### Added

- Delete desktops from frontend

### Fixed

- fixed statusbar components visibility

## [4.3.0] - 2021-10-11

### Added

- Reduced isard-toolbox image size
- Filebrowser has hooks that automates some events to isard-api More info [here](https://gitlab.com/isard/isardvdi/-/issues/186)

## [4.2.6] - 2021-10-11

### Fixed

- Fixes bug when accessing jumperurl in deployments and generation of same url for all 

## [4.2.5] - 2021-10-11

### Fixed

- Exception when the user is already logged out in webapp

## [4.2.4] - 2021-10-10

### Fixed

- Bug in deployments that didn't allow to get viewers from webapp and
  blocked access through advanced user frontend to deployments

## [4.2.3] - 2021-10-08

### Fixed

- How infrastructure hyper get registered in database

## [4.2.2] - 2021-10-08

### Fixed

- Missing translations of French, German, Basque and Russian

## [4.2.1] - 2021-10-07

- Fix docker-compose file build

    Fix multiple configuration files support by using new environment for
    each configuration file.

    Fix regression of v4.2.0 in docer-compose.yml generated via gitlab-ci

## [4.2.0] - 2021-10-07

### Added

- Support multiple configuration files

    `build.sh` generates `docker-compose.yml` using `isardvdi.cfg`
    and `docker-compose.my_config.yml` using `isardvdi.my_config.cfg`.
    See new variables in `isardvdi.cfg.example` to select flavour and usage
    type. Also, stats inclusion can be configured.

## [4.1.3] - 2021-10-07

### Fixed

- Missing translations of French

## [4.1.2] - 2021-10-06

### Fixed

- Fixed wg MTU to 1600 at isard-vpn and hypers. This will allow at least in
  infrastructure to get personal networks working with web.
  To fix it on cloud refer to the links in isardvdi.cfg.example.

## [4.1.1] - 2021-10-06

### Fixed

- Forced hypervisor setting undefined after edit.

## [4.1.0] - 2021-10-06

### Added

- Create desktop from frontend

## [4.0.2] - 2021-10-05

### Fixed

- Fix bug when stopping domains

## [4.0.1] - 2021-10-04

### Fixed

- Fix gitlab-ci by adding missing stats docker container

## [4.0.0] - 2021-09-28

### Changed

- There is OpenVswitch inside isard-vpn and inside isard-hypervisor (all). Isard-vpnc who went with remotehyper has disappeared. A wireguard 3-layer tunnel is created between isard-hypervisor and isard-vpn and another geneve-type layer 2 tunnel is set in. This allows encapsulating vlans inside the geneve tunnels.
- All bridge type interfaces (with vlan id) that existed in the DB are passed to ovs type (openvswitch)
- The wireguard interface is changed to an ovs interface with vlan id 4095 which is now wireguard.
- All domains when adding an ovs-like network with an associated vlan tag are tagged by the engine to the xml with this tag and automatically pass through the geneve tunnels to (and from) isard-vpn and see each other.
- There is now a dnsmasq in vlan 4095 inside isard-vpn which serves all directions dynamically towards all guests who have wireguard networking. It is also this dnsmasq who is responsible for updating the mac-ip-domain in the DB (in isard-engine he puts the mac and then isard-api when he receives dnsmasq info he seeks this mac in the domains and updates the guest wireguard IP).
- If you put a trunk-type physical interface into the isard-hypervisor (with the pipework), when you want a machine to put a network with an existing vlan id into the trunk, you see the physical machines of that vlan.
- Warning! Do not add more than one physical trunk interface to hypervisors as it will flood (storm). Only one hypervisor should be tight to the physical network now. Planning to add RSTP at ovs level.
- Hypervisors are no longer created in the DB (may but will no longer work like this). When the hypervisor starts access to isard-api and adds itself to the bbdd. In this process, the engine connects and puts it online, and the hypervisor establishes the geneve tunnel for networks. When the hypervisor is destroyed (docker-compose down or shut down the machine) it also accesses the api to be removed. In this process the api first stops all the desktops it has (in the near future it will migrate to another hyper) and once finished it is removed from the bbdd.
- There is an option in isard-engine to put the hypervisor into 'only forced' (not yet on the web). This option is very interesting because it will allow us to test a hyper with forced hyper domains before we can switch to production.
- Now all goes with JWT (see isardvdi.cfg.example there is jwt for different services).
- isardvdi.cfg has changed completely, and some wireguard and networks still need to be removed. It is self-documented.
- The isard-engine is now much faster to detect states and change domains.
- The isard-engine is more stable when working with hypervisors that enter and exit.
- The option to put a domain as server appears as admin in domains. This makes him always try to get him off.
- In terms of stats it has been changed and now sends the data that monitors thehyper to isard-influxdb and the new queries are in grafana (we are still making graphs). Influx also has a token to connect between stats and vpn.

### New

- A 'personal' network is created. This network defines a range of vlan ids (2000-3000). When a user adds the personal network to their desktops, they will all have the same interface to one of these vlans. More personal networks can be created with different ranks as well.
- Scan storage files from isard-hypervisor and add the non used by domains nor already in media to the media of that user. This script can be run on an isard-hypervisor: docker exec isard-hypervisor python3 /src/lib/media-scan.py [all|media|groups]. This will allow to upload isos/qcows directly on the host storage path (/opt/isard/...), scan it with the script and create desktops from isos and desktops from the media menu.
- Added filebrowser to access /opt/isard/{backups,templates,groups,media} folders from portal/video where an hypervisor is attached. The only writable (upload) folders are groups and media, others are read only (download). It can be accessed from hypervisor details in webapp.

## [3.3.0] - 2021-10-02

### Changed

- Use gitlab-ci parallel matrix feature to speed up builds

## [3.2.8] - 2021-09-30

### Fixed

- Fix frontend login by always allowing login via category path

## [3.2.7] - 2021-09-30

### Fixed

- Fix webapp logout, regression of v3.0.0 and v3.1.14

## [3.2.6] - 2021-09-30

### Fixed

- Missing translations of French and German

## [3.2.5] - 2021-09-28

### Fixed

- Back to qemu 5 as qemu 6 misbehaves with mouse in html5

### Update tricks

#### After upgrade

```sh
docker-compose exec isard-hypervisor chown -R qemu /etc/pki/libvirt-spice
```

More info [here](https://gitlab.com/isard/isardvdi/-/issues/176)

## [3.2.4] - 2021-09-28

### Fixed

- Fix direct viewer url in isard-portal endpoint

## [3.2.3] - 2021-09-27

### Fixed

- Fix gitlab-ci mergerequest pipelines, regression of v3.1.0

## [3.2.2] - 2021-09-27

### Fixed

- Missing translations of Catalan, French, German and Russian

## [3.2.1] - 2021-09-23

### Fixed

- Fix gitlab-ci docker push, regression of v3.1.10

## [3.2.0] - 2021-09-22

### Changed

- Use packaged QEMU in the hypervisor Docker instead of building it manually

## [3.1.17] - 2021-09-22

### Fixed

- Bulk create desktops initializes iCheck incorrectly and leads to a mass creation to all the users

## [3.1.16] - 2021-09-22

### Fixed

- Missing user role in template listing

## [3.1.15] - 2021-09-20

### Fixed

- Filter media by term

## [3.1.14] - 2021-09-20

### Fixed

- Access to media when on desktop modal

## [3.1.13] - 2021-09-20

### Fixed

- Removed nginx cache to improve client performance

## [3.1.12] - 2021-09-20

### Fixed

- Fixed bug when showing multiple times the guest IP in viewers modal

## [3.1.11] - 2021-09-17

### Fixed

- Access to resources that are owned by a user already deleted. 
  Will allow access to those resources only to admin/manager roles.

## [3.1.10] - 2021-09-17

### Added

- Docker builds now use cache, reducing build times

## [3.1.9] - 2021-09-17

### Fixed

- Fixed releaser script

## [3.1.8] - 2021-09-16

### Fixed

- fix bug when username has '_' character and uses deployments

## [3.1.7] - 2021-09-13

### Fixed

- fix accessing details when user is not admin or manager in decorator @ownsidortag

## [3.1.6] - 2021-09-10

### Fixed

- fix websockets connection after expired session

## [3.1.5] - 2021-09-09

### Fixed

- Show downloading status in frontend

## [3.1.4] - 2021-09-09

### Added

- Vue Composition Api support

## [3.1.3] - 2021-09-09

### Added

- Enable restart of failed desktops

## [3.1.2] - 2021-09-07

### Fixed

- Login errors messages

## [3.1.1] - 2021-09-07

### Fixed

- Authentication user name in token and role in oauth

## [3.1.0] - 2021-09-01

### Added

- Added the releaser script. Now tags and GitLab releases are done automatically

## [3.0.2] - 2021-08-27

### Fixed

- Deployments with started desktops failed

## [3.0.1] - 2021-08-27

### Fixed

- Temporary desktops didn't start
- Some temporary desktops logout user as the allowed filter had a bug

### Removed

- Removed unused BACKEND variables from isardvdi.cfg

## [3.0.0] - 2021-08-25 | Gran Paradiso

*Note*: it is possible to upgrade from version `2.0.0-rc1` to `3.0.0`, but we don't assure you everything will work (though it probably will). For a stable installation, start from scratch. 

### Update tricks

#### Before upgrade
```sh
mkdir -p /opt/isard/hypervisor
docker cp isard-hypervisor:/etc/ssh /opt/isard/hypervisor/sshd_keys
rm /opt/isard/hypervisor/sshd_keys/moduli /opt/isard/hypervisor/sshd_keys/ssh_config /opt/isard/hypervisor/sshd_keys/sshd_config
```
More info [here](https://github.com/isard-vdi/isard/pull/290)

```sh
docker network rm isard-network
```
More info [here](https://gitlab.com/isard/isardvdi/-/merge_requests/276#note_626216072)

#### After upgrade
```sh
docker-compose run isard-hypervisor chown -R qemu /etc/pki/libvirt-spice
```
More info [here](https://github.com/isard-vdi/isard/issues/278#issuecomment-716102809)


### Added

- New frontend
- Set a custom logo
- Single Sign On
- Full Nvidia GPU support
- RDP viewer
- RDP browser viewer (using Guacamole)
- Deployments (desktop groups)
- Desktop soft shutdown
- Desktop sharing through an unique URL
- VPN connection for each user

### Fixed

- *Lots* of bugs fixed in all the services

### Changed

- Advanced interface styles cleanup
- Updated Libvirt & QEMU to newer releases
- Updated lots of frontend & webapp Javascript dependencies
- Development moved to Gitlab
- Renamed the 'Updates' section to 'Downloads', in the advanced interface

### Removed

- Old frontend


## [2.0.0-rc1] - 2020-08-03

### Added

- OAuth2 Gitlab & Google authentications
- Auto enrollment codes
- Non persistent desktops
- Simplified web front end for non persistent desktops
- Multitenancy configuration
- New tenancy limits for users, desktops, concurrent, vcpus, memory, templates...
- Single 80 & 443 ports for everything (including viewers)
- New isardvdi.cfg and build.sh custom installation
- New QoS resource definitions for networking and storage
- New api with basic endpoints to control your users, desktops and viewers

### Fixed

- Deleting templates with fine grained detail of domains chain
- Lots of non critical web user interface bugs

### Changed

- New grafana dashboards with more details
- Stats moved from engine to an independent isard-stats container

### Removed

- Spice Web viewer (in favour of noVNC)

## [1.2.2] - 2020-03-24

### Added

- Hypervisor autodetects VLANS or can be set by script.
- Adding remote hypervisor through CLI has all the UI options now.
  docker exec -e ENABLED=True -e ID=isard-hypervisor -e HYPERVISOR=192.168.0.10 -e PASSWORD=isard -e PORT=2022 -e POOL=default -e DISKOP=True -e VIRTUALOP=True -e VIEWERHOST=localhost -e VIEWERNATHOST=isardvdi.com -e VIEWERNATOFFSET=30000 isard-app sh -c '/add-hypervisor.sh'
- Added squid image that allows proxying spice viewers.
- Now .env file allows to configure main system parameters.
- Grafana container updated to latest version and uses .env file
- Rsync added to Hypervisor image so now can handle different mount points.
- Maintenance mode (on/off) in nginx. docker exec -ti isard-nginx /bin/sh -c "maintenance.sh on"

### Fixed

- Fixed supervisord parameters in app to be more stable at restart.
- Hypervisor default network is forced to be active as failed in some systems.
- Mosquitto extras image rebuild and now automatically monitors Espurna IoT power devices.
- Removed rsync bwlimit when creating templates

### Changed
- Grafana is now part of main docker-compose file.
- Database upgrade modified python3 rethinkdb connection

## [1.2.1] - 2019-07-06

### Fixed

- Removed last access from the user profile page [#67](https://github.com/isard-vdi/isard/issues/67)
- Hide the delete user button until it works [#171](https://github.com/isard-vdi/isard/issues/171)
- Don't depend only on environment variables for the Docker Compose Isard version [#175](https://github.com/isard-vdi/isard/pull/175)

## [1.2.0] - 2019-06-21 | La Pedriza

### Added
- Create desktops automatically when a user from a specific category / group logs in [#134](https://github.com/isard-vdi/isard/issues/134)
- Ephimeral desktops for a specific category / group [#133](https://github.com/isard-vdi/isard/issues/133)
- New Docker and Docker Compose developing system [#160](https://github.com/isard-vdi/isard/issues/160)
- Set predefined desktops when adding users in bulk [#138](https://github.com/isard-vdi/isard/issues/138)

### Changed

- Improved the XML definitions to boost the video performance [#157](https://github.com/isard-vdi/isard/issues/157)

### Fixed
- Add minimum template name length [#136](https://github.com/isard-vdi/isard/issues/136)
- Fix hypervisor port variable type when updating an hypervisor [#137](https://github.com/isard-vdi/isard/issues/137)
- Fix VNC port variable type when updating it [#139](https://github.com/isard-vdi/isard/issues/139)
- Remote hyper port 22 restriction [#149](https://github.com/isard-vdi/isard/issues/149)
- In some cases, the SSH keys weren't copied to the hypervisor [#155](https://github.com/isard-vdi/isard/issues/155)

## [1.1.1] - 2019-03-19

### Fixed
- Bug with user password update from admin that updated all the user passwords at the same time.
- Bug when acessing IsardVDI from an https port different from 443.

## [1.1.0] - 2019-02-26 | Canigó

### Added
- Support under VMWare [#98](https://github.com/isard-vdi/isard/issues/98)
- Support on AMD cpu [#98](https://github.com/isard-vdi/isard/issues/98)
- Permissions on templates and bases in admin mode [#118](https://github.com/isard-vdi/isard/issues/118)
- Delete templates and bases with all the derived desktops and templates (admin mode) [#114](https://github.com/isard-vdi/isard/issues/114)
- Complete domain chain in domain dictionary [#78](https://github.com/isard-vdi/isard/issues/78)
- Delete media will delete the media in all domains [#111](https://github.com/isard-vdi/isard/issues/111)

### Changed
- Force host-passthrough cpu mode in domains for better compatibility [#101](https://github.com/isard-vdi/isard/issues/101)
- Swapped wizard steps hypervisor and engine as makes more sense to check first the engine. [#81](https://github.com/isard-vdi/isard/issues/81)
- Domain status engine detection now done using stats thread. Not relaying only in libvirt events. [#120](https://github.com/isard-vdi/isard/issues/120)

### Fixed
- On physical host reboot the hypervisor docker gets online again. [#119](https://github.com/isard-vdi/isard/issues/119)
- Media status correctly shown in web interface. [#110](https://github.com/isard-vdi/isard/issues/110)
- Post installation updates register now works. [#109](https://github.com/isard-vdi/isard/issues/109)
- Admin base and template modals not shown. [#112](https://github.com/isard-vdi/isard/issues/112)
- Restart download when failed [#91](https://github.com/isard-vdi/isard/issues/91)
- Delete process is now more atomic and will delete domain from database even if there are problems during disk delete. [#117](https://github.com/isard-vdi/isard/issues/117)

### Removed
- Windows install checkbox on creating domain. Not needed anymore. [#115](https://github.com/isard-vdi/isard/issues/115)
- Global actions removed from templates and bases as are not needed there. [#116](https://github.com/isard-vdi/isard/issues/116)

## [1.0.1] - 2018-12-27

### Fixed
- Wait for the hypervisor before starting engine. Fixes some restart cases that may fail [#20](https://github.com/isard-vdi/isard/issues/20)

## [1.0.0] - 2018-12-22 | Anayet
This is the stable release of IsardVDI.

### Added
- Unique docker-compose version with alpine base images
- Updated websocket viewers with spice and vnc
- Secure spice and vnc connections with certificates.
- Self-signed and commercial certificates can be used.
- Wizard will generate self-signed certificates for websocket viewers if none found.
- New graphics definition that will allow better tuning of graphics parameters.
- Redefined modal for opening viewers that allow setting preferred one.

### Changed
- User admin can change private template to base template
- All templates are private and can define permissions
- Wizard: More information about updates
- Improved the design of the Nginx 502 static page.
- Advanced users can upload and manage media
- The login form has a "required" indicator in the password field

### Fixed
- Cpu and graphics rewritten in domain XML previous to start. 
- Improved bugs in configuration forms
- When edit xml, create more exceptions and logs if failed trying to start

### Removed
- Create from virt-install y and virt-builder deactivated in this release. 

## [0.9.1] - 2018-02-19

### Fixed

- Launching too much hypervisor event threads
- Page errors and hardware populate modals
- Boot order error when modifying hardware and create xml
- Added logging folder in repository


### Added

- Bulk actions updated


## [0.9.0] - 2018-02-02

### Added

- Wizard installation
- Media download from url to have isos in your domains
- Repository with qcow disks, isos and configuration that the admin can download from isardvdi.com repo
- New policy balanced algorithm based on weights

### Changed

- New internal stats with pandas 
- New tests to try policy balanced algorithm and domains behaviours


## [0.8.1] - 2017-11-04

- Fixing bugs


## [0.8.0] - 2017-06-20

- First public release
