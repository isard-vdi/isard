import requests
from rethinkdb import ReqlTimeoutError, r

r.connect("isard-db", 28015).repl()


def add_private_code(code):
    try:
        r.db("isard").table("config").get(1).update(
            {"resources": {"private_code": code}}
        ).run()
        print("Private code updated")
    except Exception as e:
        print("Error updating.\n" + str(e))


code = input("Enter you private access code to IsardVDI Downloads Service: ")
add_private_code(code)
