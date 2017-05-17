import csv
import rethinkdb as r
from engine.db import insert_host_viewer, new_rethink_connection, insert_place
from engine.log import log

class dbo (object):
    def __init__(self):
        self.conn = new_rethink_connection()

db = dbo()


if not r.table_list().contains('places').run(db.conn):
    log.info("Table places not found, creating...")
    r.table_create('places', primary_key="id").run(db.conn)
    r.table('hypervisors_events').index_create("network_address").run(db.conn)
    r.table('hypervisors_events').index_wait("network_address").run(db.conn)
    r.table('hypervisors_events').index_create("status").run(db.conn)
    r.table('hypervisors_events').index_wait("status").run(db.conn)

if not r.table_list().contains('hosts_viewers').run(db.conn):
    log.info("Table hosts_viewers not found, creating...")
    r.table_create('hosts_viewers', primary_key="id").run(db.conn)
    r.table('places').index_create("hostname").run(db.conn)
    r.table('places').index_wait("hostname").run(db.conn)
    r.table('places').index_create("mac").run(db.conn)
    r.table('places').index_wait("mac").run(db.conn)
    r.table('places').index_create("place_id").run(db.conn)
    r.table('places').index_wait("place_id").run(db.conn)

l_csv = list(csv.reader(open('/opt/macs_y_hostnames.csv')))
l_ok  = [[a[0],int(a[-1])-200,'10.200.{}.{}'.format(a[1],a[-1]),a[2],a[3]] for a in l_csv if  a[1] != '\\N' and a[-1] != '\\N']
l_places = list(set([s[-1] for s in l_ok]))


for place in l_places:
    rows_by_default = 6
    cols_by_default = 6
    insert_place(place,place,rows_by_default,cols_by_default)

for l_host in l_ok:
    order = l_host[1]
    if order < 1 or order > 35:
        print('order <1 or > 35')
        row = 0
        col = 0
    else:
        row = int(((order-36)*-1)/6)
        col = ((order-36)*-1) % 6

    insert_host_viewer(hostname=l_host[0],
                       description=l_host[0],
                       place_id=l_host[-1],
                       ip=l_host[2],
                       row=row,
                       col=col,
                       mac=l_host[3])