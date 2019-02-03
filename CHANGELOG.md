# IsardVDI Changelog

All notable changes to this project will be documented in this file.

## [1.1.0-rc1] - 2019-02-03

This is the first release candidate for the 1.1.0 version. The changelog is going to be updated after the release (approximately in a week [2019-02-10]). Check the [pull request](https://github.com/isard-vdi/isard/pull/94) for more information.

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
