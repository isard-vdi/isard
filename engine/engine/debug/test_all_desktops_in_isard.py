from engine.services import db

all_domains = db.get_all_domains_with_id_and_status()
all_domains_stopped = [d for d in all_domains if d["status"] == "Stopped"]
