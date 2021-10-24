# Isard**VDI**

<img align="right" src="frontend/src/assets/logo.svg" alt="IsardVDI Logo" width="150px;">

[![release](https://img.shields.io/badge/dynamic/json.svg?label=release&url=https://gitlab.com/api/v4/projects/21522757/releases&query=0.name&color=blue)](https://gitlab.com/isard/isardvdi/-/releases)
[![docker-compose](https://img.shields.io/badge/docker--compose-ready-blue.svg)](https://isard.gitlab.io/isardvdi-docs/install/install/#quickstart)
[![docs](https://img.shields.io/badge/docs-latest-brightgreen.svg)](https://isard.gitlab.io/isardvdi-docs/)
[![license](https://img.shields.io/badge/license-AGPL%20v3.0-brightgreen.svg)](LICENSE)

IsardVDI is a Free Software desktop virtualization platform. Some of its features are:

- **GPU support**: it supports the NVIDIA Grid platform 
- **Easy to install**: using Docker and Docker Compose, you can deploy IsardVDI in minutes
- **Scalable**: you can manage multiple hypervisors and add / remove them depending on your needs
- **Fast**: start a desktop and connect to it in a matter of seconds
- **Versatile**: you can run all the OS supported by QEMU/KVM, and there are multiple viewers supported:
  + *SPICE*
  + *noVNC* (web)
  + *RDP*
  + *Guacamole RDP* (web)



## Table of contents

- [Quick Start](#quick-start)
- [Usage](#usage)
- [Documentation](#documentation)
- [Version upgrade notes](#version-upgrade-notes)
- [Contributing](#contributing)
- [Support and Contact](#support-and-contact)
- [Other links](#other-links)
- [License](#license)



## Quick Start

[https://isard.gitlab.io/isardvdi-docs/install/#quick-start](https://isard.gitlab.io/isardvdi-docs/install/#quick-start)



## Usage

### Desktops

To download predefined and tested desktops, you can go to the `Downloads` section, in the `Administration` frontend.

If you want to create your own desktop:

1.  Go to `Media` section (in the `Administration` frontend),  and download an ISO
2. After the download is finished, it will show a desktop icon where you can create the desktop.

### Templates

Create a template from a desktop (in the `Administration` frontend):

1. Open desktop details and click the `Template it` button.
2. Fill in the form and click on `create`.

It will create a template from that desktop as it was now. You can create as many desktops identical to that template.


![Main admin screen](https://isard.gitlab.io/isardvdi-docs/images/main.png)



## Documentation

Follow the extensive documentation to get the most of your installation:

- [https://isard.gitlab.io/isardvdi-docs](https://isard.gitlab.io/isardvdi-docs)



## Version upgrade notes:

- See [Release Notes](https://gitlab.com/isard/isardvdi/-/releases)



## Contributing

The development is done at [GitLab](https://gitlab.com/isard/isardvdi). You can open an issue and create pull requests there. Also, there's the [CONTRIBUTING.md](CONTRIBUTING.md) file, that you should read too. Happy hacking! :D



## Support and Contact

If you have a question related with the software, open an issue! Otherwise, email us at `info@isardvdi.com`. We also offer professional paid support. If you are interested, email us! :)



## Other links

- Website: [https://www.isardvdi.com](https://www.isardvdi.com)
- Mastodon profile: [@isard@fosstodon.org](https://fosstodon.org/@isard)
- Twitter profile: [@isard_vdi](https://twitter.com/isard_vdi)



## License

IsardVDI is licensed under the AGPL v3.0. You can read the full license [here](LICENSE)
