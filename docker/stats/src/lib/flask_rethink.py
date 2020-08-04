# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

import os
import rethinkdb as r

class RethinkDB(object):
    def __init__(self):
        self.conn = None
        self.host=os.environ['STATS_RETHINKDB_HOST']
        self.port=os.environ['STATS_RETHINKDB_PORT']
        self.auth_key=''
        self.db=os.environ['STATS_RETHINKDB_DB']
        try:
            c = r.connect(host=self.host,
                             port=self.port,
                             auth_key='',
                             db=self.db)
            self.check_database(c)
            c.close() 
        except Exception as e:
            print(e)
            exit(1)
            raise
                                    
    def __enter__(self):
        try:
            self.conn = r.connect(host=self.host,
                             port=self.port,
                             auth_key='',
                             db=self.db)
        except:
            raise
        return self.conn
        
    def __exit__(self,a,b,c):
        self.conn.close()

    def check_database(self,c):
        try:
            while not r.db_list().contains(self.db).run(c):
                time.sleep(1)
            self.create_tables(c)
        except Exception as e:
            # ~ exc_type, exc_obj, exc_tb = sys.exc_info()
            # ~ fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            # ~ log.error(exc_type, fname, exc_tb.tb_lineno)
            print(e)
            None

    def create_tables(self,c):
        print('create')
        if not r.table_list().contains('domains').run(c):
            print('domains')
            r.table_create('domains', primary_key="id").run(c)
            self.index_create('domains',['user'],c)
        if not r.table_list().contains('run').run(c):
            print('run')
            r.table_create('run', primary_key="id").run(c)  
            self.index_create('run',['domain','event'],c)          
        if not r.table_list().contains('viewer').run(c):
            print('viewer')
            r.table_create('viewer', primary_key="id").run(c) 
            self.index_create('viewer',['domain','event','protocol'],c)           
                        
    def index_create(self,table,indexes,c):
        indexes_ontable=r.table(table).index_list().run(c)
        apply_indexes = [mi for mi in indexes if mi not in indexes_ontable]
        for i in apply_indexes:
            r.table(table).index_create(i).run(c)
            r.table(table).index_wait(i).run(c)
