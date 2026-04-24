#!/usr/bin/env python3
import json
import os

from rethinkdb import r

DB_HOST = os.environ.get("RETHINKDB_HOST", "172.31.255.13")
DB_PORT = int(os.environ.get("RETHINKDB_PORT", "28015"))
DB_NAME = os.environ.get("RETHINKDB_DB", "isard")
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# Tables that have no seed JSON but accumulate per-user state across runs and
# must be reset so dependent tests stay deterministic on re-runs against the
# same database. notifications_data records "user X has been notified of
# notification Y" — once present, the login-trigger fullpage notification
# stops firing, breaking the e2e login-fullpage test on every run after the
# first.
RESET_TABLES = ["notifications_data"]


def main():
    dbconn = r.connect(DB_HOST, port=DB_PORT, db=DB_NAME).repl()
    print(f"Connected to RethinkDB {DB_HOST}:{DB_PORT} db={DB_NAME}")

    for table_name in RESET_TABLES:
        try:
            result = r.table(table_name).delete().run(dbconn)
            print(f"Reset table '{table_name}': {result}")
        except Exception as e:
            print(f"Error resetting '{table_name}': {e}")

    for filename in os.listdir(DATA_DIR):
        if not filename.endswith(".json"):
            continue
        table_name = filename[:-5]
        file_path = os.path.join(DATA_DIR, filename)
        print(f"Inserting data into table '{table_name}' from '{filename}'...")
        try:
            with open(file_path, "r") as f:
                data = json.load(f)
            if not isinstance(data, list):
                data = [data]
            result = r.table(table_name).insert(data, conflict="update").run(dbconn)
            print(f"Result: {result}")
        except Exception as e:
            print(f"Error inserting into '{table_name}': {e}")


if __name__ == "__main__":
    main()
