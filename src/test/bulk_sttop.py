from time import sleep

import engine.services.db.domains
from engine.services import db

[db.update_domain_status('Starting', a['id']) for a in engine.services.db.domains.get_domains_from_user('test1')]
sleep(30)
[db.update_domain_status('Stopping', a['id']) for a in engine.services.db.domains.get_domains_from_user('test1')]
sleep(10)
[db.update_domain_status('Deleting', a['id']) for a in engine.services.db.domains.get_domains_from_user('test1')]


