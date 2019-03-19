# IsardVDI Changelog

All notable changes to this project will be documented in this file.

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
