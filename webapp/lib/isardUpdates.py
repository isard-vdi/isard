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
        self.updateFromWeb()
        import pprint
        pprint.pprint([[(k,y['id']) for y in v] for k,v in self.web.items()])
        # This should be an option to the user
        #~ if not self.is_registered(): 
            #~ self.register()
            #~ self.updateFromConfig()

    def updateFromWeb(self):
        self.web={}
        self.kinds=['media','domains','builders','virt_install','virt_builder']
        for k in self.kinds:
            self.web[k]=self.getKind(kind=k)
                
        
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
        web=self.web[kind]
        dbb=list(r.table(kind).run(db.conn))
        result=[]
        for w in web:
            found=False
            for d in dbb:
                # ~ if kind == 'domains' or kind == 'media':
                    # ~ if d['id']=='_'+username+'_'+w['id']:
                        # ~ found=True
                        # ~ w['id']='_'+username+'_'+w['id']
                        # ~ w['new']=False
                        # ~ w['status']=d['status']                        
                        # ~ break
                # ~ else:
                    if d['id']==w['id']:
                        found=True
                        w['new']=False
                        w['status']=d['status']      
                        break
                        
            if not found: 
                w['id']=='_'+username+'_'+w['id']
                w['new']=True
                w['status']='Available'
            result.append(w)
            # ~ else:
                # ~ result.append(
            
        return result
        #~ return [i for i in web for j in dbb if i['id']==j['id']]

    def getNewKindId(self,kind,username,id):
        web=[d for d in self.web[kind] if d['id'] == id]
        # If id is not in this kind, something went wrong. Don't continue!
        if len(web)==0: return False
        web=web[0]
        # ~ if kind == 'domains' or kind == 'media':
            # ~ dbb=r.table(kind).get('_'+username+'_'+web['id']).run(db.conn)
        # ~ else:
        dbb=r.table(kind).get(web['id']).run(db.conn)
        # If this id is not in database already, download it!
        if dbb is None:
            return web
        else:
            # The user has this domain already?
            return False

        
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
   
   
    '''
    RETURN FORMATTED DOMAINS TO INSERT ON TABLES
    '''             
    def formatDomains(self,data,current_user):
        for d in data:
            # ~ d['id']='_'+current_user.id+'_'+d['id']
            d['progress']={}
            d['status']='DownloadStarting'
            d['detail']=''
            d['hypervisors_pools']=d['create_dict']['hypervisors_pools']
            d.update(self.get_user_data(current_user))
            for disk in d['create_dict']['hardware']['disks']:
                disk['file']=current_user.path+disk['file']
        return data
        
    def formatMedias(self,data,current_user):
        for d in data:
            # ~ if 'path' in d.keys():
                d.update(self.get_user_data(current_user))
                d['progress']={}
                d['status']='DownloadStarting'                    
                d['path']=current_user.path+d['url-isard']
        return data

    def get_user_data(self,current_user):
        return {'category': current_user.category,
                'group': current_user.group,
                'user': current_user.id}        
