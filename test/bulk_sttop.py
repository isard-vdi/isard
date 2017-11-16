from time import sleep

from engine.services import db

[db.update_domain_status('Starting', a['id']) for a in db.get_domains_from_user('test1')]
sleep(30)
[db.update_domain_status('Stopping', a['id']) for a in db.get_domains_from_user('test1')]
sleep(10)
[db.update_domain_status('Deleting', a['id']) for a in db.get_domains_from_user('test1')]


