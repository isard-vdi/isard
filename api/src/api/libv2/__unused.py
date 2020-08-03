
'''
NOT USED
'''
def enrollment_gen( role, length=6):
    if role not in ['manager','advanced','user']: return False
    chars = digits + ascii_lowercase
    code = False
    while code == False:
        code = "".join([random.choice(chars) for i in range(length)]) 
        if self.enrollment_code_check(code) == False:
            return code
        else:
            code = False


def enrollment_code_check( code):
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





































# ~ def get_category_template_id(cat):
    # ~ with app.app_context():
        # ~ id = r.table('domains').filter(r.row['kind'].match("template")).filter(lambda d: d['allowed']['categories']).order_by('name').pluck('id').run(db.conn)
        # ~ if id is None:
            # ~ return False
        # ~ return id

def get_template(id):
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

def get_default_template_id(user,category,group):
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

def CategoryGet( category_id):
    category = r.table('categories').get(category_id).run(db.conn)
    if category is None:
        raise CategoryNotFound

    return { 'name': category['name'] }

def CreateCategory(category_id, quota):
        if r.table('categories').get(category_id).run(db.conn) is None:
            if create_if_not_exist == False:
                raise CategoryNotFound
            r.table('categories').insert([{'id': category_id,
                                            'name': category_id,
                                            'description': category_id,
                                            'quota': quota,
                                            }], conflict='update').run(db.conn)
def CreateGroup( group_id, quota):
        if r.table('groups').get(group_id).run(db.conn) is None:
            if create_if_not_exist == False:
                raise GroupNotFound
            r.table('groups').insert([{'id': group_id,
                                            'name': group_id,
                                            'description': group_id,
                                            'quota': quota,
                                            }], conflict='update').run(db.conn)




def domain_create_and_start( user, category, group, template, custom):
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








def domain_destroy( user):
    ## StoppingAndDeleting all the user's desktops
    with app.app_context():
        r.table('domains').get_all(user, index='user').filter({'status':'Started','persistent':False}).update({'status':'Stopping'}).run(db.conn)
        r.table('domains').get_all(user, index='user').filter({'status':'Stopped','persistent':False}).update({'status':'Deleting'}).run(db.conn)

        # ~ r.table('domains').get_all(user, index='user').filter({'status':'StoppingAndDeleting'}).delete().run(db.conn)
        # ~ r.table('domains').get_all(user, index='user').filter({'status':'CreatingAndStarting'}).delete().run(db.conn)
        # ~ r.table('domains').get_all(user, index='user').update({'status':'StoppingAndDeleting'}).run(db.conn)

# ~ def domain_destroy_not_started( user):
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
