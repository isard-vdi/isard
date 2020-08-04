from rethinkdb import r, ReqlTimeoutError
r.connect('isard-db', 28015).repl()
from pprint import pprint
cat=r.db('isard').table('categories').get(False).run()
pprint(cat)
r.db('isard').table('categories').get(False).delete().run()
cat['id']='manager@samltest.id'
r.db('isard').table('categories').insert(cat).run()

#pprint(.update({'id':'manager@samltest.id'}).run())
exit(1)
print(r.db('isard').table('domains').get('_admin_linkatv1').pluck('id','status').run())
status = r.db('isard').table('domains').get('_admin_Template_TetrOS').changes().filter(r.row['status'] == 'Started').run()
