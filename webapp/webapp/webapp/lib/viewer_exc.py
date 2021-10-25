# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8


class CategoryNotFound(Exception):
    pass


class GroupNotFound(Exception):
    pass


class UserTemplateNotFound(Exception):
    pass


class TemplateNotFound(Exception):
    pass


class NewUserNotInserted(Exception):
    pass


class NewDesktopNotInserted(Exception):
    pass


class DesktopNotStarted(Exception):
    pass


class DesktopFailed(Exception):
    pass


class DomainNotFound(Exception):
    pass


class DomainNotStarted(Exception):
    pass


class HypervisorPoolNotFound(Exception):
    pass


class DomainHypervisorSSLPortNotFound(Exception):
    pass


class DomainHypervisorPortNotFound(Exception):
    pass
