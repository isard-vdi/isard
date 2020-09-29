# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

class UserNotFound(Exception):
    pass

class UserExists(Exception):
    pass
    
class UserTemplatesError(Exception):
    pass

class UserDesktopsError(Exception):
    pass

class UserLoginFailed(Exception):
    pass

class UpdateFailed(Exception):
    pass

class DesktopNotCreated(Exception):
    pass

class DesktopWaitFailed(Exception):
    pass

class DesktopStartTimeout(Exception):
    pass    

class DesktopStopTimeout(Exception):
    pass

class DesktopStartFailed(Exception):
    pass

class DesktopStopFailed(Exception):
    pass

class DesktopNotFound(Exception):
    pass

class DesktopNotStarted(Exception):
    pass

class DesktopPreconditionFailed(Exception):
    pass

class DesktopExists(Exception):
    pass

class NotAllowed(Exception):
    pass

class ViewerProtocolNotImplemented(Exception):
    pass

class ViewerProtocolNotFound(Exception):
    pass

class RoleNotFound(Exception):
    pass

class CategoryNotFound(Exception):
    pass
    
class GroupNotFound(Exception):
    pass

class UserDeleteFailed(Exception):
    pass



class UserTemplateNotFound(Exception):
    pass
    
class TemplateNotFound(Exception):
    pass

class TemplateExists(Exception):
    pass
    
class NewUserNotInserted(Exception):
    pass

class NewDesktopNotInserted(Exception):
    pass
    
class NewTemplateNotInserted(Exception):
    pass


class DesktopFailed(Exception):
    pass
    


class HypervisorPoolNotFound(Exception):
    pass

class DomainHypervisorSSLPortNotFound(Exception):
    pass

class DomainHypervisorPortNotFound(Exception):
    pass
    

class CodeNotFound(Exception):
    pass



class NewDesktopNotBootable(Exception):
    pass

class MediaNotFound(Exception):
    pass

class XmlNotFound(Exception):
    pass
