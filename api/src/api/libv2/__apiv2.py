#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import time
from api import app
from datetime import datetime, timedelta
import pprint

#import pem
#from OpenSSL import crypto

# ~ from contextlib import closing

#import rethinkdb as r
from rethinkdb import RethinkDB; r = RethinkDB()
from rethinkdb.errors import ReqlTimeoutError
# ~ from ..libv1.log import *
import logging as log

from .flask_rethink import RDB
db = RDB(app)
db.init_app(app)

from ..auth.authentication import *

from ..libv2.isardViewer import isardViewer
isardviewer = isardViewer()

# ~ from ..auth.authentication import Password

import bcrypt,string,random

from .apiv2_exc import *

# ~ import threading
#import concurrent.futures
from .ds import DS 
ds = DS()

class ApiV2():
    def __init__(self):
        self.au=auth()

    def UserExists(self,user_id):
        with app.app_context():
            if r.table('users').get(user_id).run(db.conn) is None:
                raise UserNotFound

    def UserCreate(self, provider, category_id, user_uid, user_username, role_id, group_id, password=False, photo='', email=''):
        # password=False generates a random password
        with app.app_context():
            id = provider+'-'+category_id+'-'+user_uid+'-'+user_username
            if r.table('users').get(id).run(db.conn) != None:
                raise UserExists

            if r.table('roles').get(role_id).run(db.conn) is None: raise RoleNotFound
            if r.table('categories').get(category_id).run(db.conn) is None: raise CategoryNotFound
            group = r.table('groups').get(group_id).run(db.conn)
            if group is None: raise GroupNotFound

            if password == False:
                password = ''
            else:
                password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            user = {'id': id,
                    'name': user_username,
                    'uid': user_uid,
                    'provider': provider,
                    'active': True,
                    'accessed': time.time(),
                    'username': user_username,
                    'password': password,
                    'role': role_id,
                    'category': category_id,
                    'group': group_id,
                    'email': email,
                    'photo': photo,
                    'default_templates':[],
                    'quota': group['quota'],  # 10GB
                    }
            if not _check(r.table('users').insert(user).run(db.conn),'inserted'):
                raise NewUserNotInserted #, conflict='update').run(db.conn)
        return user['id']

    def UserUpdate(self, user_id, user_name, user_email='', user_photo=''):
        self.UserExists(user_id)
        if not _check(r.table('users').get(user_id).update({'name':user_name, 'email':user_email, 'photo':user_photo}).run(db.conn),'replaced'):
            raise UpdateFailed

    def UserTemplates(self,user_id):
        with app.app_context():
            if r.table('users').get(user_id).run(db.conn) == None:
                raise UserNotFound
        try:
            with app.app_context():
                ud=r.table('users').get(user_id).run(db.conn)
            if ud == None:
                raise UserNotFound
            with app.app_context():
                data1 = r.table('domains').get_all('base', index='kind').order_by('name').pluck({'id','name','allowed','kind','group','icon','user','description'}).run(db.conn)
                data2 = r.table('domains').filter(r.row['kind'].match("template")).order_by('name').pluck({'id','name','allowed','kind','group','icon','user','description'}).run(db.conn)
            data = data1+data2
            alloweds=[]
            for d in data:
                with app.app_context():
                    d['username']=r.table('users').get(d['user']).pluck('name').run(db.conn)['name']
                if ud['role']=='admin':
                    alloweds.append(d)
                    continue
                if d['user']==ud['id']:
                    alloweds.append(d)
                    continue
                if d['allowed']['roles'] is not False:
                    if len(d['allowed']['roles'])==0:
                        alloweds.append(d)
                        continue
                    else:
                        if ud['role'] in d['allowed']['roles']:
                            alloweds.append(d)
                            continue
                if d['allowed']['categories'] is not False:
                    if len(d['allowed']['categories'])==0:
                        alloweds.append(d)
                        continue
                    else:
                        if ud['category'] in d['allowed']['categories']:
                            alloweds.append(d)
                            continue
                if d['allowed']['groups'] is not False:
                    if len(d['allowed']['groups'])==0:
                        alloweds.append(d)
                        continue
                    else:
                        if ud['group'] in d['allowed']['groups']:
                            alloweds.append(d)
                            continue
                if d['allowed']['users'] is not False:
                    if len(d['allowed']['users'])==0:
                        alloweds.append(d)
                        continue
                    else:
                        if ud['id'] in d['allowed']['users']:
                            alloweds.append(d)
                            continue
            return alloweds
        except Exception as e:
            raise UserTemplatesError

    def UserDesktops(self,user_id):
        with app.app_context():
            if r.table('users').get(user_id).run(db.conn) == None:
                raise UserNotFound
        try:
            with app.app_context():
                return list(r.table('domains').get_all(user_id, index='user').filter({'kind':'desktop'}).order_by('name').pluck({'id','name','icon','user','status','description'}).run(db.conn))

        except Exception as e:
            raise UserDesktopsError

    def UserDelete(self,user_id):
        with app.app_context():
            if r.table('users').get(user_id).run(db.conn) is None:
                raise UserNotFound
        todelete = self._user_delete_checks(user_id)
        for d in todelete:
            try:
                ds.delete_desktop(d['id'],d['status'])
            except:
                raise
        #self._delete_non_persistent(user_id)
        if not _check(r.table('users').get(user_id).delete().run(db.conn),"deleted"):
            raise UserDeleteFailed

    def _user_delete_checks(self,user_id):
        with app.app_context():
            user_desktops = list(r.table("domains").get_all(user_id, index='user').filter({'kind': 'desktop'}).pluck('id','name','kind','user','status','parents').run(db.conn))
            user_templates = list(r.table("domains").get_all(r.args(['base','public_template','user_template']),index='kind').filter({'user':user_id}).pluck('id','name','kind','user','status','parents').run(db.conn))
            derivated = []
            for ut in user_templates:
                id = ut['id']
                derivated = derivated + list(r.table('domains').pluck('id','name','kind','user','status','parents').filter(lambda derivates: derivates['parents'].contains(id)).run(db.conn))
                #templates = [t for t in derivated if t['kind'] != "desktop"]
                #desktops = [d for d in derivated if d['kind'] == "desktop"]
        domains = user_desktops+user_templates+derivated
        return [i for n, i in enumerate(domains) if i not in domains[n + 1:]]


    def Login(self,user_id,user_passwd):
        user=self.au._check(user_id,user_passwd)
        if user == False:
            raise UserLoginFailed

    """ def DesktopNewPersistent(self,user_id,template_id, desktop_name):
        parsed_name = _parse_string(desktop_name)
        desktop_id = '_' + user_id + '_' + parsed_name
        with app.app_context():
            desktops = r.db('isard').table('domains').get(desktop_id).run(db.conn)
        if len(desktops) != None:
            raise DesktopExists

        return self._nonpersistent_desktop_create_and_start(user_id,template_id,desktop_name) """

    def DesktopNewNonpersistent(self,user_id,template_id):
        with app.app_context():
            if r.table('users').get(user_id).run(db.conn) is None:
                raise UserNotFound
        # Has a desktop with this template? Then return it (start it if stopped)
        with app.app_context():
            desktops = list(r.db('isard').table('domains').get_all(user_id, index='user').filter({'from_template':template_id, 'persistent':False}).run(db.conn))
        if len(desktops) == 1:
         with app.app_context():
            desktops = list(r.db('isard').table('domains').get_all(user_id, index='user').filter({'from_template':template_id, 'persistent':False}).run(db.conn))
        if len(desktops) == 1:
            if desktops[0]['status'] == 'Started':
                return desktops[0]['id']
            elif desktops[0]['status'] == 'Stopped':
                self.WaitStatus(desktops[0]['id'], 'Stopped','Starting','Started')
                return desktops[0]['id']

        # If not, delete all nonpersistent based desktops from user
        ds.delete_non_persistent(user_id,template_id)

        # and get a new nonpersistent desktops from this template
        return self._nonpersistent_desktop_create_and_start(user_id,template_id)

    def DesktopViewer(self, desktop_id, protocol):
        try:
            viewer_txt = isardviewer.viewer_data(desktop_id, protocol, get_cookie=False)
        except DesktopNotFound:
            raise
        except DesktopNotStarted:
            raise
        except NotAllowed:
            raise
        except ViewerProtocolNotFound:
            raise
        except ViewerProtocolNotImplemented:
            raise
        return viewer_txt

    def DesktopDelete(self, desktop_id):
        with app.app_context():
            desktop = r.table('domains').get(desktop_id).run(db.conn)
        if desktop == None:
            raise DesktopNotFound
        ds.delete_desktop(desktop_id, desktop['status'])

    def _nonpersistent_desktop_create_and_start(self, user_id, template_id):
        with app.app_context():
            user=r.table('users').get(user_id).run(db.conn)
        if user == None:
            raise UserNotFound
        # Create the domain from that template
        desktop_id = self._nonpersistent_desktop_from_tmpl(user_id, user['category'], user['group'], template_id)
        if desktop_id is False :
            raise DesktopNotCreated

        ds.WaitStatus(desktop_id, 'Any','Any','Started')
        return desktop_id

    def _nonpersistent_desktop_from_tmpl(self, user_id, category, group, template_id):
        with app.app_context():
            template = r.table('domains').get(template_id).run(db.conn)
        if template == None:
            raise TemplateNotFound
        timestamp = time.strftime("%Y%m%d%H%M%S")
        parsed_name=timestamp+'-'+_parse_string(template['name'])

        parent_disk=template['hardware']['disks'][0]['file']
        dir_disk = 'volatiles/'+category+'/'+group+'/'+user_id
        disk_filename = parsed_name+'.qcow2'

        create_dict=template['create_dict']
        create_dict['hardware']['disks']=[{'file':dir_disk+'/'+disk_filename,
                                            'parent':parent_disk}]
        create_dict=_parse_media_info(create_dict)

        new_desktop={'id': '_'+user_id+'-'+parsed_name,
                  'name': parsed_name,
                  'description': template['description'],
                  'kind': 'desktop',
                  'user': user_id,
                  'username': user_id.split('-')[-1],
                  'status': 'CreatingAndStarting',
                  'detail': None,
                  'category': category,
                  'group': group,
                  'xml': None,
                  'icon': template['icon'],
                  'server': template['server'],
                  'os': template['os'],
                  'options': {'viewers':{'spice':{'fullscreen':True}}},
                  'create_dict': {'hardware':create_dict['hardware'],
                                    'origin': template['id']},
                  'hypervisors_pools': template['hypervisors_pools'],
                  'allowed': {'roles': False,
                              'categories': False,
                              'groups': False,
                              'users': False},
                  'persistent':False,
                  'from_template':template['id']}

        with app.app_context():
            if _check(r.table('domains').insert(new_desktop).run(db.conn),'inserted'):
                return new_desktop['id']
        return False

    def DesktopNewPersistent(self, desktop_name, user_id,  memory, vcpus, from_template_id = False, xml_id = False, disk_size = False, iso = False, boot='disk'):
        parsed_name = _parse_string(desktop_name)
        hardware = {'boot_order': [boot],
                    'disks': [],
                    'floppies': [],
                    'graphics': ['default'],
                    'interfaces': ['default'],
                    'isos': [],
                    'memory': 524288,
                    'vcpus': 1,
                    'videos': ['default']}

        with app.app_context():
            try:
                user=r.table('users').get(user_id).pluck('id','category','group','provider','username','uid').run(db.conn)
            except:
                raise UserNotFound
            if iso != False:
                if r.table('media').get(iso).run(db.conn) == None: raise MediaNotFound
            if from_template_id != False:
                template = r.table('domains').get(from_template_id).run(db.conn)
                if template == None: raise TemplateNotFound
                xml = None
            elif xml_id != False:
                xml_data = r.table('virt_install').get(xml_id).run(db.conn)
                if xml_data == None: raise XmlNotFound
                xml = xml_data['xml']
            else:
                raise DesktopPreconditionFailed


        dir_disk, disk_filename = _disk_path(user, parsed_name)

        if from_template_id == False:
            if disk_size == False:
                if boot == 'disk': raise NewDesktopNotBootable
                if boot == 'cdrom' and iso == False: raise NewDesktopNotBootable
                hardware['disks']=[]
            else:
                hardware['disks']=[{'file':dir_disk+'/'+disk_filename,
                                    'size':disk_size}]   # 15G as a format   UNITS NEEDED!!!
            status = 'CreatingDiskFromScratch'
            parents = []
        else:
            hardware['disks']=[{'file':dir_disk+'/'+disk_filename,
                                                'parent':template['create_dict']['hardware']['disks'][0]['file']}]
            status = 'Creating'
            parents = template['parents'] if 'parents' in template.keys() else []

        hardware['boot_order']=[boot]
        hardware['isos']=[] if iso == False else [iso]
        hardware['vcpus']=vcpus
        hardware['memory']=memory*1048576

        create_dict=_parse_media_info({'hardware':hardware})
        if from_template_id != False:
            create_dict['origin']=from_template_id
        else:
            create_dict['create_from_virt_install_xml'] = xml_id

        new_domain={'id': '_'+user_id+'-'+parsed_name,
                  'name': desktop_name,
                  'description': 'Api created',
                  'kind': 'desktop',
                  'user': user['id'],
                  'username': user['username'],
                  'status': status,
                  'detail': None,
                  'category': user['category'],
                  'group': user['group'],
                  'xml': xml,
                  'icon': 'linux',
                  'server': False,
                  'os': 'linux',
                  'options': {'viewers':{'spice':{'fullscreen':True}}},
                  'create_dict': create_dict,
                  'hypervisors_pools': ['default'],
                  #'parents': parents,
                  'allowed': {'roles': False,
                              'categories': False,
                              'groups': False,
                              'users': False}}

        with app.app_context():
            if r.table('domains').get(new_domain['id']).run(db.conn) == None:
                if _check(r.table('domains').insert(new_domain).run(db.conn),'inserted') == False:
                    raise NewDesktopNotInserted
                else:
                    return new_domain['id']
            else:
                raise DesktopExists


    def TemplateNew(self, template_name, user_id, from_desktop_id):
        parsed_name = _parse_string(template_name)
        template_id = '_' + user_id + '-' + parsed_name

        with app.app_context():
            try:
                user=r.table('users').get(user_id).pluck('id','category','group','provider','username','uid').run(db.conn)
            except:
                raise UserNotFound
            desktop = r.table('domains').get(from_desktop_id).run(db.conn)
            if desktop == None: raise DesktopNotFound

        parent_disk=desktop['hardware']['disks'][0]['file']

        hardware = desktop['create_dict']['hardware']

        dir_disk, disk_filename = _disk_path(user, parsed_name)
        hardware['disks']=[{'file':dir_disk+'/'+disk_filename,
                                            'parent':parent_disk}]

        create_dict=_parse_media_info({'hardware':hardware})
        create_dict['origin']=from_desktop_id
        print(create_dict)
        template_dict={'id': template_id,
                  'name': template_name,
                  'description': 'Api created',
                  'kind': 'user_template',
                  'user': user['id'],
                  'username': user['username'],
                  'status': 'CreatingTemplate',
                  'detail': None,
                  'category': user['category'],
                  'group': user['group'],
                  'xml': desktop['xml'], #### In desktop creation is
                  'icon': desktop['icon'],
                  'server': desktop['server'],
                  'os': desktop['os'],
                  'options': desktop['options'],
                  'create_dict': create_dict,
                  'hypervisors_pools': ['default'],
                  'parents': desktop['parents'] if 'parents' in desktop.keys() else [],
                  'allowed': {'roles': False,
                              'categories': False,
                              'groups': False,
                              'users': False}}

        with app.app_context():
            if r.table('domains').get(template_dict['id']).run(db.conn) == None:

                if _check(r.table('domains').get(from_desktop_id).update({"create_dict": {"template_dict": template_dict}, "status": "CreatingTemplate"}).run(db.conn),'replaced') == False:
                    raise NewTemplateNotInserted
                else:
                    return template_dict['id']
            else:
                raise TemplateExists






    def CodeSearch(self,code):
        with app.app_context():
            found=list(r.table('groups').filter({'enrollment':{'manager':code}}).run(db.conn))
            if len(found) > 0:
                category = found[0]['parent_category'] #found[0]['id'].split('_')[0]
                return {'role':'manager', 'category':category, 'group':found[0]['id']}
            found=list(r.table('groups').filter({'enrollment':{'advanced':code}}).run(db.conn))
            if len(found) > 0:
                category = found[0]['parent_category'] #found[0]['id'].split('_')[0]
                return {'role':'advanced', 'category':category, 'group':found[0]['id']}
            found=list(r.table('groups').filter({'enrollment':{'user':code}}).run(db.conn))
            if len(found) > 0:
                category = found[0]['parent_category'] #found[0]['id'].split('_')[0]
                return {'role':'user', 'category':category, 'group':found[0]['id']}
        raise CodeNotFound

    '''
    HELPERS
    '''
    def _parse_string(self, txt):
        import re, unicodedata, locale
        if type(txt) is not str:
            txt = txt.decode('utf-8')
        #locale.setlocale(locale.LC_ALL, 'ca_ES')
        prog = re.compile("[-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9]+$")
        if not prog.match(txt):
            return False
        else:
            # ~ Replace accents
            txt = ''.join((c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn'))
            return txt.replace(" ", "_")

    def _disk_path(self, user, parsed_name):
        with app.app_context():
            group_uid = r.table('groups').get(user['group']).run(db.conn)['uid']

        dir_path = user['category']+'/'+group_uid+'/'+user['provider']+'/'+user['uid']+'-'+user['username']
        filename = parsed_name + '.qcow2'
        return dir_path,filename

    def _check(self,dict,action):
        '''
        These are the actions:
        {u'skipped': 0, u'deleted': 1, u'unchanged': 0, u'errors': 0, u'replaced': 0, u'inserted': 0}
        '''
        if dict[action]:
            return True
        if not dict['errors']: return True
        return False

    def _random_password(self,length=16):
        chars = string.ascii_letters + string.digits + '!@#$*'
        rnd = random.SystemRandom()
        return ''.join(rnd.choice(chars) for i in range(length))

    def _parse_media_info(self, create_dict):
        medias=['isos','floppies','storage']
        for m in medias:
            if m in create_dict['hardware']:
                newlist=[]
                for item in create_dict['hardware'][m]:
                    with app.app_context():
                        newlist.append(r.table('media').get(item['id']).pluck('id','name','description').run(db.conn))
                create_dict['hardware'][m]=newlist
        return create_dict


    '''
    NOT USED
    '''
    def enrollment_gen(self, role, length=6):
        if role not in ['manager','advanced','user']: return False
        chars = digits + ascii_lowercase
        code = False
        while code == False:
            code = "".join([random.choice(chars) for i in range(length)]) 
            if self.enrollment_code__check(code) == False:
                return code
            else:
                code = False


    def enrollment_code__check(self, code):
        with app.app_context():
            found=list(r.table('groups').filter({'enrollment':{'manager':code}}).run(db.conn))
            if len(found) > 0:
                category = found[0]['parent_category'] #found[0]['id'].split('_')[0]
                return {'code':code,'role':'manager', 'category':category, 'group':found[0]['id']}
            found=list(r.table('groups').filter({'enrollment':{'advanced':code}}).run(db.conn))
            if len(found) > 0:
                category = found[0]['parent_category'] #found[0]['id'].split('_')[0]
                return {'code':code,'role':'advanced', 'category':category, 'group':found[0]['id']}
            found=list(r.table('groups').filter({'enrollment':{'user':code}}).run(db.conn))
            if len(found) > 0:
                category = found[0]['parent_category'] #found[0]['id'].split('_')[0]
                return {'code':code,'role':'user', 'category':category, 'group':found[0]['id']}  
        return False 





































    # ~ def get_category_template_id(self,cat):
        # ~ with app.app_context():
            # ~ id = r.table('domains').filter(r.row['kind'].match("template")).filter(lambda d: d['allowed']['categories']).order_by('name').pluck('id').run(db.conn)
            # ~ if id is None:
                # ~ return False
            # ~ return id

    def get_template(self,id):
        # Get template to create domain
        template=None
        with app.app_context():
            try:
                if False:
                    id=id+'_'+'user'
                template = r.table('domains').get(id).without('xml','history_domain','progress').run(db.conn)
            except:
                raise TemplateNotFound
        if template is None:
            # WTF! Asked for a template that does not exist??
            raise TemplateNotFound
        return template

    def get_default_template_id(self,user,category,group):
        with app.app_context():
            try:
                return r.table('users').get(user).run(db.conn)['default_templates'][0]
            except:
                None
            try:
                return r.table('groups').get(group).run(db.conn)['default_templates'][0]
            except:
                None
            try:
                return r.table('categories').get(category).run(db.conn)['default_templates'][0]
            except:
                None
        return False
            # ~ id = r.table('domains').filter(r.row['kind'].match("template")).filter(lambda d: d['allowed']['categories']).order_by('name').pluck('id').run(db.conn)
            # ~ if id is None:
                # ~ return False
            # ~ return id

    def CategoryGet(self, category_id):
        category = r.table('categories').get(category_id).run(db.conn)
        if category is None:
            raise CategoryNotFound

        return { 'name': category['name'] }

    def CreateCategory(self,category_id, quota):
            if r.table('categories').get(category_id).run(db.conn) is None:
                if create_if_not_exist == False:
                    raise CategoryNotFound
                r.table('categories').insert([{'id': category_id,
                                               'name': category_id,
                                               'description': category_id,
                                               'quota': quota,
                                               }], conflict='update').run(db.conn)
    def CreateGroup(self, group_id, quota):
            if r.table('groups').get(group_id).run(db.conn) is None:
                if create_if_not_exist == False:
                    raise GroupNotFound
                r.table('groups').insert([{'id': group_id,
                                               'name': group_id,
                                               'description': group_id,
                                               'quota': quota,
                                               }], conflict='update').run(db.conn)




    def domain_create_and_start(self, user, category, group, template, custom):
        ## StoppingAndDeleting all the user's desktops
        # ~ with app.app_context():
            # ~ r.table('domains').get_all(user, index='user').update({'status':'StoppingAndDeleting'}).run(db.conn)
        ### Check if already started
        with app.app_context():
            desktops = list(r.db('isard').table('domains').get_all(user, index='user').filter({'status':'Started'}).run(db.conn))
            if len(desktops) > 0:
                return desktops[0]
        self.domain_destroy(user)


        # Create the domain from that template
        desktop_id = self.domain_from_tmpl(user, category, group, template, custom)
        if desktop_id is False :
            raise NewDesktopNotInserted

        # Wait for domain to be started
        # ~ for i in range(0,10):
            # ~ time.sleep(1)
            # ~ if r.db('isard').table('domains').get(desktop_id).pluck('status').run(db.conn)['status'] == 'Started':
                # ~ return True
            # ~ i=i+1
        # ~ raise DesktopNotStarted

        # ~ try:
            # ~ thread = threading.Thread(target=self.wait_for_domain, args=(desktop_id,))
            # ~ thread.start()
            # ~ thread.join()
        # ~ except ReqlTimeoutError:
            # ~ raise DesktopNotStarted


        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.wait_for_domain, desktop_id)
        try:
            result = future.result()
        except ReqlTimeoutError:
            raise DesktopNotStarted
        except DesktopFailed:
            raise








    def domain_destroy(self, user):
        ## StoppingAndDeleting all the user's desktops
        with app.app_context():
            r.table('domains').get_all(user, index='user').filter({'status':'Started','persistent':False}).update({'status':'Stopping'}).run(db.conn)
            r.table('domains').get_all(user, index='user').filter({'status':'Stopped','persistent':False}).update({'status':'Deleting'}).run(db.conn)

            # ~ r.table('domains').get_all(user, index='user').filter({'status':'StoppingAndDeleting'}).delete().run(db.conn)
            # ~ r.table('domains').get_all(user, index='user').filter({'status':'CreatingAndStarting'}).delete().run(db.conn)
            # ~ r.table('domains').get_all(user, index='user').update({'status':'StoppingAndDeleting'}).run(db.conn)

    # ~ def domain_destroy_not_started(self, user):
        # ~ ## StoppingAndDeleting all the user's desktops but Started (mantain old started desktop)
        # ~ r.table("domains").get_all(user, index='user').filter(
                        # ~ lambda dom:
                        # ~ (dom["Status"] == "Started")
                    # ~ ).run(conn)


        # ~ with app.app_context():
            # ~ r.table('domains').get_all(user, index='user').filter({'status':'StoppingAndDeleting'}).delete().run(db.conn)
            # ~ r.table('domains').get_all(user, index='user').filter({'status':'CreatingAndStarting'}).delete().run(db.conn)
            # ~ r.table('domains').get_all(user, index='user').update({'status':'StoppingAndDeleting'}).run(db.conn)

    def get_domain_id(self,user):
        with app.app_context():
            try:
                return list(r.table('domains').get_all(user, index='user').run(db.conn))[0]['id']
            except Exception:
                raise

