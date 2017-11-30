import rethinkdb as r

from engine.services.db import new_rethink_connection, close_rethink_connection


def get_last_domain_status(name):
    r_conn = new_rethink_connection()
    rtable = r.table('domains_status')
    try:
        return rtable. \
            get_all(name, index='name'). \
            nth(-1). \
            run(r_conn)
        # ~ filter({'name':name}).\
        # ~ order_by(r.desc('when')).\
        # ~ limit(1).\
        close_rethink_connection(r_conn)
    except:
        close_rethink_connection(r_conn)
        return None
        # ~ if len(l) == 0:
        # ~ return None
        # ~ else:
        # ~ return l  #[0]


def stop_last_domain_status(name):
    r_conn = new_rethink_connection()
    rtable = r.table('domains_status')
    try:
        return rtable. \
            get_all(name, index='name'). \
            nth(-1).update({'state': 'stopped', 'state_reason': 'not running'}). \
            run(r_conn)
        close_rethink_connection(r_conn)
    except:

        close_rethink_connection(r_conn)
        return None


def insert_db_domain_status(dict_domain_status):
    r_conn = new_rethink_connection()
    rtable = r.table('domains_status')

    rtable.insert(dict_domain_status). \
        run(r_conn, durability="soft", noreply=True)
    close_rethink_connection(r_conn)

def get_all_domain_status(name, start=None, end=None):
    r_conn = new_rethink_connection()
    rtable = r.table('domains_status')
    if start and end:
        results = rtable.filter({'name':name}).filter(lambda s: start <= s['when'] and s['when'] <= end).order_by(r.desc('when')).run(r_conn)
    elif start:
        results = rtable.filter({'name': name}).filter(lambda s: start <= s['when']).order_by(r.desc('when')).run(r_conn)
    elif end:
        results = rtable.filter({'name': name}).filter(lambda s: s['when'] <= end).order_by(r.desc('when')).run(r_conn)
    else:
        results = rtable.filter({'name': name}).order_by(r.desc('when')).run(r_conn)
    close_rethink_connection(r_conn)
    return list(results)