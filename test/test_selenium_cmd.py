import argparse
import threading
import queue
from pprint import pprint
from time import sleep

from selenium.webdriver import Remote
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

from config_test_selenium import *

TIMEOUT_QUEUES = 1

d_wd = {}

class Wd_thread(threading.Thread):
    def __init__(self,name,id_host):
        threading.Thread.__init__(self)
        self.q = queue.Queue()
        self.id_host = id_host
        self.d_wd = {}
        self.name = name
        self.stop = False
        self.button = False
        
    def run(self):
        self.d_wd['wd']=False
        self.d_wd['running'] = False
        while self.stop is not True:
            try:
                action=self.q.get(timeout=TIMEOUT_QUEUES)

                pprint(action)
                if action['type'] == 'CreateAndLogin':
                    
                    self.d_wd['running'] = True
                    wd = create_wd_and_login(action['num_host'],
                            action['browser_name'],
                            action['user'],
                            action['pwd'])
                            
                    self.d_wd['wd'] = wd
                    self.d_wd['running'] = False
                
                if action['type'] == 'FillFormCreateDesktop':
                    self.d_wd['running'] = True
                    self.button = fill_form_create_desktop_from_template(self.d_wd['wd'],
                            action['name_desktop'],
                            action['kind_template'],
                            action['id_template'])
                    self.d_wd['running'] = False
                
                if action['type'] == 'ClickButton':
                    self.d_wd['running'] = True
                    self.button.click()
                    self.d_wd['running'] = False

            except queue.Empty:
                pass
            except Exception as e:
                log.error('Exception when creating disk template: {}'.format(e))
                return False
                

def init_web_driver(address,browser_name):
    desired_caps = {}
    desired_caps['platform'] = 'LINUX'
    desired_caps['browserName'] = browser_name

    wd = Remote('http://{}:4444/wd/hub'.format(address), desired_caps)
    wd.get(url_base)
    return wd

def login_in_isard(wd,user,pwd):

    u=wd.find_element_by_xpath("//input[@name='user']")
    u.send_keys(user)
    u=wd.find_element_by_xpath("//input[@name='password']")
    u.send_keys(pwd)

    b=[b for b in wd.find_elements_by_xpath("//button") if b.text == 'Login'][0]
    b.click()

def fill_form_create_desktop_from_template(wd,name_desktop,kind_template,id_template):
    wd.get('{}/desktops'.format(url_base))

    b=wd.find_element_by_class_name('btn-new')
    b.click()

    wait = WebDriverWait(wd, 2)
    f = wait.until(EC.visibility_of_element_located((By.XPATH, "//input[@placeholder='New desktop name']")))

    f.send_keys('{}'.format(name_desktop))

    select_kind=Select(wd.find_element_by_xpath("//select[@id='kind']"))
    select_kind.select_by_value(kind_template)

    select_template=Select(wd.find_element_by_xpath("//select[@id='template']"))
    select_template.select_by_value(id_template)

    select_videos=Select(wd.find_element_by_xpath("//select[@id='hardware-videos']"))
    select_videos.select_by_value('qxl32')
    b=[b for b in wd.find_elements_by_xpath("//button") if b.text == 'Create desktop'][0]
    return b
    
def create_desktop_from_template(wd,name_desktop,kind_template,id_template):
    b = fill_form_create_desktop_from_template(wd,name_desktop,kind_template,id_template)
    
    b.click()

def create_wd_and_login(num_host, browser_name,user,pwd):
    address = '{}{}'.format(prefix_address,str(num_host).zfill(2))
    wd = init_web_driver(address,browser_name)
    login_in_isard(wd,user,pwd)    
    return wd

def logout(wd):
    pass
    
threads_wd = {}

def create_desktops_in_threads(s,S,num_test,base_test_name):

    

    for id_host in range(s,S+1):
        thread_name = 'wd{0:02d}'.format(id_host)
        
        t = Wd_thread(thread_name,id_host)
        threads_wd[id_host] = t
        
        action={}
        action['type'] = 'CreateAndLogin'
        action['num_host'] = id_host
        action['browser_name'] = 'firefox'
        action['user'] = user
        action['pwd']  = pwd

        t.daemon = True
        t.start()
        t.q.put(action)

    sleep(0.2)
    while len([i.name for i in threads_wd.values() if i.d_wd['running'] != False]) > 0:
        sleep(0.2)
        print('wait web driver and login started in selenium servers:')
        [print(i.name) for i in threads_wd.values() if i.d_wd['running'] == True]

    print('ready to fill forms')
    read_from_cmd = input('press Enter to continue')
    
    
    for id_host in range(s,S+1):
        
        action = {}
        action['name_desktop']  = '{}_{}'.format(base_test_name,str(num_test).zfill(2))
        action['kind_template'] = kind_template
        action['id_template']   = id_template
        action['type'] = 'FillFormCreateDesktop'
        threads_wd[id_host].q.put(action)
        num_test = num_test + 1

    while len([i.name for i in threads_wd.values() if i.d_wd['running'] != False]) > 0:
        print('wait web driver and login started in selenium servers:')
        [print(i.name) for i in threads_wd.values() if i.d_wd['running'] == True]

    print('ready to create desktop')
    read_from_cmd = input('press Enter to continue')
    

    for id_host in range(s,S+1):
        
        action = {}
        action['type'] = 'ClickButton'
        threads_wd[id_host].q.put(action)
        

    print('ready to close selenium session')
    read_from_cmd = input('press Enter to continue')
    

    for id_host in range(s,S+1):
        
        threads_wd[id_host].d_wd['wd'].close()
        threads_wd[id_host].stop = True
        
        
    return threads_wd
    
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    ## opciones del usuario

    parser.add_argument('-s', '--seleniumServerStart', type=int, default=[1], help='number of selenium server instance',nargs=1)
    parser.add_argument('-S', '--seleniumServerEnd', type=int, default=[1], help='total selenium servers since number of ServerStart',nargs=1)
    parser.add_argument('-n', '--numberTest', type=int, default=[1], help='set the number for suffix in domain name in tests',nargs=1)
    parser.add_argument('-N', '--totalTestPerServer', type=int, default=[1], help='total numbers of tests per seleniumServer',nargs=1)
    parser.add_argument('-b', '--baseTestName', type=int, default=[1], help='prefix_desktop name to test',nargs=1)
    parser.add_argument('-a', '--action', help='set number for test',nargs=1,
                                          required=True,
                                          choices=['DesksInThreads','createDesktop'])
    
    
    args = parser.parse_args()
    num = args.numberTest[0]
    prefix_desktop_test = base_test_name
    if args.baseTestName:
        prefix_desktop_test = args.baseTestName[0]
    
    if (args.action):
        print('asdf')
        print(args.seleniumServerStart)
        print(args.seleniumServerEnd)
        print(args.numberTest)
        print(args.totalTestPerServer)
        if args.action[0] == 'DesksInThreads':
            create_desktops_in_threads(args.seleniumServerStart[0],
                        args.seleniumServerEnd[0],
                        args.numberTest[0],
                        prefix_desktop_test)
        if args.action[0] == 'createDesktop':
            for s in range(args.seleniumServerStart[0],args.seleniumServerEnd[0]+1):
                create_wd_and_login(s, browser_name,name_desktop,kind_template,id_template)
                name_desktop = '{}_{}'.format(base_test_name,str(num).zfill(2))
                    
                address = '{}{}'.format(prefix_address,str(num_host).zfill(2))
                
                print('seleniumServerAdress: {}'.format(address))
                    
                for i in range(args.totalTestPerServer[0]):
                    
                    create_desktop_from_template(wd,name_desktop,kind_template,id_template)
                    num = num + 1
                    
            
            
    
