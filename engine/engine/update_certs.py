# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

# ~ ''' Check for new certificates and update db if needed '''
from initdb.lib import Certificates
c=Certificates()
c.update_hyper_pool()
