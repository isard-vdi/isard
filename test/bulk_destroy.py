from time import sleep
from engine import db

[db.update_domain_status('Deleting',a['id']) for a in db.get_domains_from_user('test1')]


