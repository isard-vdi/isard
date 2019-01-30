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
        # ~ self.working=True
        self.reload_updates()
        
    def reload_updates(self):
        self.updateFromConfig()
        self.updateFromWeb()
        
    def updateFromWeb(self):
        
        self.web={}
        self.kinds=['media','domains','builders','virt_install','virt_builder','videos','viewers']
        failed=0
        for k in self.kinds:
            self.web[k]=self.getKind(kind=k)
            if self.web[k]==500:
                # The id is no longer in updates server.
                # We better reset it
                with app.app_context():
                    r.table('config').get(1).update({'resources':{'code':False}}).run(db.conn)
                    self.code=False
        # ~ if len(self.kinds)==failed:
            # ~ self.working=False
        
    def updateFromConfig(self):
        with app.app_context():
            cfg=r.table('config').get(1).pluck('resources').run(db.conn)['resources']
        self.url=cfg['url']
        self.code=cfg['code']

    def is_conected(self):
        try:
            req= requests.get(self.url,allow_redirects=False, verify=False, timeout=3)
            if req.status_code==200:
                return True
        except:
            return False
        return False
        
    def is_registered(self):
        if self.is_conected():
            return self.code
            # ~ if self.working:
                # ~ return self.code 
            # ~ else:
                # we have an invalid code. (changes in web database?)
                # ~ with app.app_context():
                    # ~ r.table('config').get(1).update({'resources':{'code':False}}).run(db.conn)
        return False

    def register(self):
        try:
            req= requests.post(self.url+'/register' ,allow_redirects=False, verify=False, timeout=3)
            if req.status_code==200:
                with app.app_context():
                    r.table('config').get(1).update({'resources':{'code':req.json()}}).run(db.conn)
                    self.code=req.json()
                    self.updateFromConfig()
                    self.updateFromWeb()
                    return True
            else:
                print('Error response code: '+str(req.status_code)+'\nDetail: '+r.json())
        except Exception as e:
            print("Error contacting.\n"+str(e))
        return False

    def getNewKind(self,kind,username):
        if kind == 'viewers':
            return self.web[kind]
        web=self.web[kind]
        with app.app_context():
            dbb=list(r.table(kind).run(db.conn))
        result=[]
        for w in web:
            dict={}
            found=False
            for d in dbb:
                if kind == 'domains' or kind == 'media':
                    if d['id']=='_'+username+'_'+w['id']:
                        dict=w.copy()                       
                        found=True
                        dict['id']='_'+username+'_'+dict['id']
                        dict['new']=False
                        dict['status']=d['status']    
                        dict['progress']=d.get('progress',False)
                        break
                else:
                    if d['id']==w['id']:
                        dict=w.copy()
                        found=True
                        dict['new']=False
                        dict['status']='Downloaded'
                        break
                        
            if not found: 
                dict=w.copy()
                if kind == 'domains' or kind == 'media':
                    dict['id']='_'+username+'_'+dict['id']
                dict['new']=True
                dict['status']='Available'
            result.append(dict)
        return result
        #~ return [i for i in web for j in dbb if i['id']==j['id']]

    def getNewKindId(self,kind,username,id):
        if kind == 'domains' or kind == 'media':
            web=[d.copy() for d in self.web[kind] if '_'+username+'_'+d['id'] == id]
        else:
            web=[d.copy() for d in self.web[kind] if d['id'] == id]
            
        if len(web)==0: return False
        w=web[0].copy()
        
        if kind == 'domains' or kind == 'media':
            with app.app_context():
                dbb=r.table(kind).get('_'+username+'_'+w['id']).run(db.conn)
            if dbb is None:
                w['id']='_'+username+'_'+w['id']
                return w
        else:
            with app.app_context():
                dbb=r.table(kind).get(w['id']).run(db.conn)
            if dbb is None:
                return w
        return False

        
    def getKind(self,kind='builders'):
        try:
            req = requests.post(self.url+'/get/'+kind+'/list', headers={'Authorization':str(self.code)},allow_redirects=False, verify=False, timeout=3)
            if req.status_code==200:
                return req.json()
                #~ return True
            elif req.status_code==500:
                return 500
            else:
                print('Error response code: '+str(req.status_code)+'\nDetail: '+req.json())
        except Exception as e:
            print("Error contacting.\n"+str(e))
        return False
   
   
    '''
    RETURN FORMATTED DOMAINS TO INSERT ON TABLES
    '''    
    # ~ def formatDomain(self,dom,current_user):
        # ~ d=dom.copy()
        # ~ d['progress']={}
        # ~ d['status']='DownloadStarting'
        # ~ d['detail']=''
        # ~ d['accessed']=time.time()
        # ~ d['hypervisors_pools']=d['create_dict']['hypervisors_pools']
        # ~ d.update(self.get_user_data(current_user))
        # ~ for disk in d['create_dict']['hardware']['disks']:
            # ~ if not disk['file'].startswith(current_user.path):
                # ~ disk['file']=current_user.path+disk['file']
        # ~ return d
                     
    def formatDomains(self,data,current_user):
        new_data=data.copy()
        for d in new_data:
            d['progress']={}
            d['status']='DownloadStarting'
            d['detail']=''
            d['accessed']=time.time()
            d['hypervisors_pools']=d['create_dict']['hypervisors_pools']
            d.update(self.get_user_data(current_user))
            for disk in d['create_dict']['hardware']['disks']:
                if not disk['file'].startswith(current_user.path):
                    disk['file']=current_user.path+disk['file']
        return new_data
        
    def formatMedias(self,data,current_user):
        new_data=data.copy()
        for d in new_data:
            d.update(self.get_user_data(current_user))
            d['progress']={}
            d['status']='DownloadStarting'
            d['accessed']=time.time()
            if d['url-isard'] is False:
                d['path']=current_user.path+d['url-web'].split('/')[-1] 
            else:
                d['path']=current_user.path+d['url-isard']
            # ~ if not d['path'].startswith(current_user.path):                  
                # ~ d['path']=current_user.path+d['url-isard']                
        return new_data

    def get_user_data(self,current_user):
        return {'category': current_user.category,
                'group': current_user.group,
                'user': current_user.id}        


    '''
    DOWNLOAD MISSING DOMAIN RESOURCES
    '''
    def get_missing_resources(self,domain,username):
        missing_resources={'videos':[]}
        
        dom_videos=domain['create_dict']['hardware']['videos']
        with app.app_context():
            sys_videos=list(r.table('videos').pluck('id').run(db.conn))
        sys_videos=[sv['id'] for sv in sys_videos]
        for v in dom_videos:
            if v not in sys_videos:
                resource=self.getNewKindId('videos',username,v)
                if resource is not False:
                    missing_resources['videos'].append(resource)
        ## graphics and interfaces missing
        return missing_resources

