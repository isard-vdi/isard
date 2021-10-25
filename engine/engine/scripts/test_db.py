from rethinkdb import r
from rethinkdb.errors import ReqlTimeoutError

r.connect("isard-db", 28015).repl()
from pprint import pprint

pprint(list(r.db("isard").table("hypervisors").run())[0])
pprint(list(r.db("isard").table("hypervisors_pools").run())[0])
exit(1)
print(r.db("isard").table("domains").get("_admin_linkatv1").pluck("id", "status").run())
status = (
    r.db("isard")
    .table("domains")
    .get("_admin_Template_TetrOS")
    .changes()
    .filter(r.row["status"] == "Started")
    .run()
)
