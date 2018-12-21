import engine.services.db.domains
from engine.services import db

[db.update_domain_status('Deleting', a['id']) for a in engine.services.db.domains.get_domains_from_user('test1')]


