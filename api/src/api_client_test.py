import time,requests,json,getpass

# Set global vars
## Valid certificate domain or localhost/IP for self-signed.
## If self-signed set verifycert=False, else True
domain="localhost"
verifycert=False
## End set global vars


# ~ auth=('isard', getpass.getpass())
auth=('admin', 'IsardVDI')
#base_url="https://"+domain+"/debug/api/api/v2/"
base_url="http://localhost:7039/api/v2/"
base_jumper_url="http://localhost:7039/"

# Create new users
def user_post(user_uid, user_username, provider, role_id, category_id, group_id, password=False):
    print("\n----------------------- USER POST (NEW)")
    global auth, verifycert
    url = base_url + "user"
    data = {"provider":provider, "user_uid":user_uid, "user_username":user_username, "role":role_id, "category":category_id, "group":group_id, "password":password}
    print(" DATA SENT: "+str(data))    
    resp = requests.post(url, data=data, auth=auth, verify=verifycert)
    
    print("       URL: "+url)    
    print("STATUS CODE: "+str(resp.status_code))
    print("   RESPONSE: "+resp.text)
    if resp.status_code == 200:
        return json.loads(resp.text)
    raise

def get_templates(user_id):
    print("\n----------------------- TEMPLATES GET")
    global auth, verifycert
    url = base_url + "user/"+user_id+"/templates"
    data = {}
    print(" DATA SENT: "+str(data)) 
    resp = requests.get(url, data=data, auth=auth, verify=verifycert)
    
    print("       URL: "+url)    
    print("STATUS CODE: "+str(resp.status_code))
    print("   RESPONSE: "+resp.text)
    if resp.status_code == 200:
        return json.loads(resp.text)
    raise

def start_desktop(desktop_id):
    print("\n----------------------- DESKTOP START")
    global auth, verifycert
    url = base_url + "desktop/start/"+desktop_id
    data = {}
    print(" DATA SENT: "+str(data))
    resp = requests.get(url, data=data, auth=auth, verify=verifycert)

    print("       URL: "+url)
    print("STATUS CODE: "+str(resp.status_code))
    print("   RESPONSE: "+resp.text)
    import pprint
    pprint.pprint(json.loads(resp.text))
    if resp.status_code == 200:
        return json.loads(resp.text)
    raise

def stop_desktop(desktop_id):
    print("\n----------------------- DESKTOP STOP")
    global auth, verifycert
    url = base_url + "desktop/stop/"+desktop_id
    data = {}
    print(" DATA SENT: "+str(data))
    resp = requests.get(url, data=data, auth=auth, verify=verifycert)

    print("       URL: "+url)    
    print("STATUS CODE: "+str(resp.status_code))
    print("   RESPONSE: "+resp.text)
    import pprint
    pprint.pprint(json.loads(resp.text))
    if resp.status_code == 200:
        return json.loads(resp.text)
    raise

def get_desktops(user_id):
    print("\n----------------------- DESKTOPS GET")
    global auth, verifycert
    url = base_url + "user/"+user_id+"/desktops"
    data = {}
    print(" DATA SENT: "+str(data)) 
    resp = requests.get(url, data=data, auth=auth, verify=verifycert)
    
    print("       URL: "+url)    
    print("STATUS CODE: "+str(resp.status_code))
    print("   RESPONSE: "+resp.text)
    import pprint
    pprint.pprint(json.loads(resp.text))
    if resp.status_code == 200:
        return json.loads(resp.text)
    raise

def post_desktop(user_id, template_id):
    print("\n----------------------- DESKTOP POST (NEW)")    
    url = base_url + "desktop"
    data = { "id": user_id, "template": template_id }
    print(" DATA SENT: "+str(data)) 
    resp = requests.post(url, data=data, auth=auth)
    print("       URL: "+url)    
    print("STATUS CODE: "+str(resp.status_code))
    print("   RESPONSE: "+resp.text)
    if resp.status_code == 200:
        return json.loads(resp.text)
    raise

def post_persistent_desktop(desktop_name, user_id,  memory, vcpus, from_template_id = False, xml_id = False, disk_size = False, iso = False, boot='disk'):
    print("\n----------------------- PERSISTENT DESKTOP POST (NEW)")    
    url = base_url + "persistent_desktop"
    #data = { "name": desktop_name, "user_id": user_id, "memory": memory, "vcpus": vcpus , "xml_id": xml_id}
    data = { "name": desktop_name, "user_id": user_id, "memory": memory, "vcpus": vcpus , "template_id": from_template_id}
    print(" DATA SENT: "+str(data)) 
    resp = requests.post(url, data=data, auth=auth)
    print("       URL: "+url)    
    print("STATUS CODE: "+str(resp.status_code))
    print("   RESPONSE: "+resp.text)
    if resp.status_code == 200:
        return json.loads(resp.text)
    raise

def post_template(template_name, user_id, desktop_id):
    print("\n----------------------- TEMPLATE POST (NEW)")    
    url = base_url + "template"
    #data = { "name": desktop_name, "user_id": user_id, "memory": memory, "vcpus": vcpus , "xml_id": xml_id}
    data = { "name": template_name, "user_id": user_id, "desktop_id": desktop_id}
    print(" DATA SENT: "+str(data)) 
    resp = requests.post(url, data=data, auth=auth)
    print("       URL: "+url)    
    print("STATUS CODE: "+str(resp.status_code))
    print("   RESPONSE: "+resp.text)
    if resp.status_code == 200:
        return json.loads(resp.text)
    raise

def get_spice_viewer(desktop_id):
    print("\n----------------------- VIEWER GET")    
    # spice-client / vnc-html5
    url = base_url + "desktop/"+desktop_id+"/viewer/spice-client"
    data = {}
    print(" DATA SENT: "+str(data)) 
    resp = requests.get(url, data=data, auth=auth)

    print("       URL: "+url)    
    print("STATUS CODE: "+str(resp.status_code))
    print("   RESPONSE: "+resp.text)
    if resp.status_code == 200:
        return json.loads(resp.text)
    raise

def get_jumper_viewer(token):
    print("\n----------------------- JUMPER VIEWER GET")    
    # spice-client / vnc-html5
    url = base_jumper_url + "viewer/"+token
    data = {}
    print(" DATA SENT: "+str(data)) 
    resp = requests.get(url, data=data)
    
def get_html5_viewer(desktop_id):
    print("\n----------------------- VIEWER GET")    
    # spice-client / vnc-html5
    url = base_url + "desktop/"+desktop_id+"/viewer/vnc-html5"
    data = {}
    print(" DATA SENT: "+str(data)) 
    resp = requests.get(url, data=data, auth=auth)

    print("       URL: "+url)    
    print("STATUS CODE: "+str(resp.status_code))
    print("   RESPONSE: "+resp.text)
    if resp.status_code == 200:
        return json.loads(resp.text)
    raise

def user_delete(user_id):
    print("\n----------------------- USER DELETE")
    global auth, verifycert
    url = base_url + "user/"+user_id
    data = {}
    print(" DATA SENT: "+str(data))  
    resp = requests.delete(url, data=data, auth=auth, verify=verifycert)
    print("       URL: "+url)    
    print("STATUS CODE: "+str(resp.status_code))
    print("   RESPONSE: "+resp.text)
    if resp.status_code == 200:
        return json.loads(resp.text)
    raise

def register(code):
    print("\n----------------------- REGISTER")    
    global auth, verifycert
    url = base_url + "register"
    data = {'code': code}
    print(" DATA SENT: "+str(data)) 
    resp = requests.post(url, data=data, auth=auth, verify=verifycert)
    print("       URL: "+url)
    print("STATUS CODE: "+str(resp.status_code))
    print("   RESPONSE: "+resp.text)
    if resp.status_code == 200:
        return json.loads(resp.text)
    raise

#get_html5_viewer('_local-default-admin-admin_downloaded_slax93')
#exit(1)

def get_categories():
    print("\n----------------------- CATEGORIES GET")
    global auth, verifycert
    url = base_url + "categories"
    data = {}
    print(" DATA SENT: "+str(data)) 
    resp = requests.get(url, data=data, auth=auth, verify=verifycert)
    
    print("       URL: "+url)    
    print("STATUS CODE: "+str(resp.status_code))
    print("   RESPONSE: "+resp.text)
    if resp.status_code == 200:
        return json.loads(resp.text)
    raise

get_desktops('local-default-admin-admin')
start_desktop('_local-default-admin-admin-asdfdsaf')

## https://localhost/viewer/8Dx9PynTHxHlSsdfk9X8VIe9M2TbFKwz6Bi_xSfdvO_u3y-H6eq2Rg
#get_jumper_viewer('8Dx9PynTHxHlSsdfk9X8VIe9M2TbFKwz6Bi_xSfdvO_u3y-H6eq2Rg')
exit(0)

desktop_id='_local+default+admin+admin+downloaded_tetros'

def test_users():
    user_uid = 'useruid'
    user_username = 'hander'
    provider = 'local'
    code = 'code'

    try:
        user = register(code)
    except Exception as e:
        print("register exc: "+str(e))
        exit(1)

    try:
        user_id = user_post(user_uid,user_username,provider,user['role'],user['category'],user['group'])['id']
    except:
        exit(1)

    try:
        user_delete(user_id)
    except:
        None

def test_persistent_desktop():
    user_id='local_default_admin_admin' 
    desktop_name = 'test'
    memory = 1.5
    vcpus = 1
    disk_size = '1M'
    xml_id = 'win7Virtio'

    
    try:
        desktop_id = post_persistent_desktop(desktop_name, user_id, memory, vcpus, xml_id= xml_id, disk_size=disk_size)
    except Exception as e:
        print("post_desktops exc: "+str(e))
        exit(1)

def test_templates():
    try:
        templates = get_templates(user_id)
    except:
        exit(1)    
    # [{"id": "_admin_aaaa", "name": "aaaa", "icon": "linux"}]

    if len(templates)==0:
        print("No templates to create desktop. Exitting")
        exit(1)

    try:
        template_id = templates[0]["id"]
    except:
        exit(1)

    try:
        desktop_id = post_desktop(id,template_id)['id']
    except:
        exit(1)

    try:
        desktop_id = post_desktop(id,template_id)['id']
    except:
        exit(1)


    try:
        desktop_id = post_desktop(id,template_id)['id']
    except:
        exit(1)

        
    try:
        viewer = get_viewer(desktop_id)
    except:
        exit(1)
    try:
        user_delete(id)
    except:
        exit(1)


def tree_create():
    ## Admin user must download tetros from updates and convert it to template.
    user_id='local_default_admin_admin' 
    template_id='_local_default_admin_admin_downloaded_tetros'
    template_id='_local_default_admin_admin_Template_TetrOS'
    desktop_name = 'desktop'
    template_name = 'template'
    memory=1
    vcpus=1


    template={'id':template_id}
    for i in range(0,5):
        desktop = post_persistent_desktop(desktop_name+str(i), user_id, memory, vcpus, from_template_id=template['id'])
        time.sleep(4)
        template = post_template(template_name+str(i), user_id, desktop['id'])
        time.sleep(4)


#tree_create()




#test_users()
#test_persistent_desktop()


def test_full(provider, user_uid, user_username, code):

    ## REGISTER AND ADD USER
    try:
        user = register(code)
    except Exception as e:
        print("register exc: "+str(e))
        exit(1)

    try:
        user_id = user_post(user_uid,user_username,provider,user['role'],user['category'],user['group'])['id']
    except:
        exit(1)

    try:
        user_delete(user_id)
    except:
        None

    try:
        user_id = user_post(user_uid,user_username,provider,user['role'],user['category'],user['group'])['id']
    except:
        exit(1)

    ## CREATE DESKTOP FOR USER
    try:
        templates = get_templates(user_id)
    except:
        user_delete(user_id)
        exit(1)    
    # [{"id": "_admin_aaaa", "name": "aaaa", "icon": "linux"}]

    if len(templates)==0:
        print("No templates to create desktop. Exitting")
        user_delete(user_id)
        exit(1)

    try:
        template_id = templates[0]["id"]
    except:
        user_delete(user_id)
        exit(1)

    try:
        desktop_id = post_desktop(user_id,template_id)['id']
    except:
        user_delete(user_id)
        exit(1)

    try:
        desktop_id = post_desktop(user_id,template_id)['id']
    except:
        user_delete(user_id)
        exit(1)

    try:
        desktop_id = post_desktop(user_id,template_id)['id']
    except:
        user_delete(user_id)
        exit(1)

    try:
        viewer = get_viewer(desktop_id)
    except:
        user_delete(user_id)
        exit(1)  


    ## In the end clear everything
    try:
        user_delete(user_id)
    except:
        None
        
test_full('local','useruid','usertest','code')
