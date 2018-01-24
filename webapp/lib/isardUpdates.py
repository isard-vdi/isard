import requests, os, json
import rethinkdb as r
import time
from webapp import app
from .flask_rethink import RethinkDB
from .log import *
db = RethinkDB(app)
db.init_app(app)

class Updates(object):
    def __init__(self):
        self.updateFromConfig()
        # This should be an option to the user
        #~ if not self.is_registered(): 
            #~ self.register()
            #~ self.updateFromConfig()
    
    def updateFromConfig(self):
        with app.app_context():
            cfg=r.table('config').get(1).pluck('resources').run(db.conn)['resources']
        self.url=cfg['url']
        self.code=cfg['code']

    def is_registered(self):
        return self.code

    def register(self):
        try:
            req= requests.post(self.url+'/register' ,allow_redirects=False, verify=False, timeout=3)
            if req.status_code==200:
                with app.app_context():
                    r.table('config').get(1).update({'resources':{'code':req.json()}}).run(db.conn)
                    self.updateFromConfig()
                    return True
            else:
                print('Error response code: '+str(req.status_code)+'\nDetail: '+r.json())
        except Exception as e:
            print("Error contacting.\n"+str(e))
        return False

    def getNewKind(self,kind,username):
        web=self.getKind(kind=kind)
        dbb=list(r.table(kind).run(db.conn))
        result=[]
        for w in web:
            found=False
            for d in dbb:
                if kind == 'domains':
                    if d['id']=='_'+username+'_'+w['id']:
                        found=True
                        break
                else:
                    if d['id']==w['id']:
                        found=True
                        break
                        
            # ~ if found: 
            w['new']=found
            result.append(w)
            # ~ else:
                # ~ result.append(
            
        return result
        #~ return [i for i in web for j in dbb if i['id']==j['id']]

        
    def getKind(self,kind='builders'):
        try:
            req= requests.post(self.url+'/get/'+kind+'/list', headers={'Authorization':str(self.code)},allow_redirects=False, verify=False, timeout=3)
            if req.status_code==200:
                return req.json()
                #~ return True
            else:
                print('Error response code: '+str(req.status_code)+'\nDetail: '+req.json())
        except Exception as e:
            print("Error contacting.\n"+str(e))
        return False
                
