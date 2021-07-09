# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

class QuotaCategoryNewUserExceeded(Exception):
    pass

class QuotaGroupNewUserExceeded(Exception):
    pass

## User

class QuotaUserNewDesktopExceeded(Exception):
    pass

class QuotaUserConcurrentExceeded(Exception):
    pass

class QuotaUserVcpuExceeded(Exception):
    pass

class QuotaUserMemoryExceeded(Exception):
    pass

## Category
class QuotaCategoryNewDesktopExceeded(Exception):
    pass   
    
class QuotaCategoryConcurrentExceeded(Exception):
    pass

class QuotaCategoryVcpuExceeded(Exception):
    pass

class QuotaCategoryMemoryExceeded(Exception):
    pass

         

## Group
class QuotaGroupNewDesktopExceeded(Exception):
    pass  

class QuotaGroupConcurrentExceeded(Exception):
    pass

class QuotaGroupVcpuExceeded(Exception):
    pass

class QuotaGroupMemoryExceeded(Exception):
    pass

  