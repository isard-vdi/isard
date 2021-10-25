import requests
from rethinkdb import ReqlTimeoutError, r

r.connect("isard-db", 28015).repl()


def activate_shares():
    try:
        r.db("isard").table("config").get(1).update(
            {"shares": {"templates": False, "isos": False}}
        ).run()
        print("Shares between categories deactivated")
    except Exception as e:
        print("Error activating shares.\n" + str(e))


activate_shares()
