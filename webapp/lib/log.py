# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

import logging as log
import configparser
import os
from webapp import app



#~ import logging as log
#~ log.basicConfig(level=log.INFO)
#~ logger = log.getLogger(__name__) 

#~ try:
    #~ rcfg = configparser.ConfigParser()
    #~ rcfg.read(os.path.join(os.path.dirname(__file__),'../../isard.conf'))
#~ except Exception as e:
    #~ log.info('Aborting. Please configure your log level in: isard.conf \n exception: {}'.format(e))
    #~ sys.exit(0)
    
#~ LOG_LEVEL = rcfg.get('LOG', 'LEVEL')
#~ LOG_FILE  = rcfg.get('LOG', 'FILE')
try:
    LOG_LEVEL = app.config['LOG_LEVEL']
except Exception as e:
    LOG_LEVEL = 'INFO'
# LOG FORMATS
LOG_FORMAT='%(asctime)s %(msecs)d - %(levelname)s - %(threadName)s: %(message)s'
LOG_DATE_FORMAT='%Y/%m/%d %H:%M:%S'
LOG_LEVEL_NUM = log.getLevelName(LOG_LEVEL)
log.basicConfig(format=LOG_FORMAT,datefmt=LOG_DATE_FORMAT,level=LOG_LEVEL_NUM)
