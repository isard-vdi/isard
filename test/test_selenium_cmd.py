import argparse
from selenium.webdriver import Remote
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select

from config_test_selenium import *


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

def create_desktop_from_template(wd,name_desktop,kind_template,id_template):
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
    b.click()

def logout(wd):
    pass
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    ## opciones del usuario

    parser.add_argument('-s', '--seleniumServerStart', type=int, default=[1], help='number of selenium server instance',nargs=1)
    parser.add_argument('-S', '--seleniumServerCount', type=int, default=[1], help='total selenium servers since number of ServerStart',nargs=1)
    parser.add_argument('-n', '--numberTest', type=int, default=[1], help='set the number for suffix in domain name in tests',nargs=1)
    parser.add_argument('-N', '--totalTestPerServer', type=int, default=[1], help='total numbers of tests per seleniumServer',nargs=1)
    parser.add_argument('-a', '--action', help='set number for test',nargs=1,
                                          required=True,
                                          choices=['createDesktop'])
    
    
    args = parser.parse_args()
    num = args.numberTest[0]
    
    
    if (args.action):
        print('asdf')
        print(args.seleniumServerStart)
        print(args.seleniumServerCount)
        print(args.numberTest)
        print(args.totalTestPerServer)
        if args.action[0] == 'createDesktop':
            for s in range(args.seleniumServerStart[0],args.seleniumServerCount[0]+1):
                
                address = '{}{}'.format(prefix_address,str(s).zfill(2))
                print('seleniumServerAdress: {}'.format(address))
                    
                for i in range(args.totalTestPerServer[0]):
                    name_desktop = '{}_{}'.format(base_test_name,str(num).zfill(2))
                    wd = init_web_driver(address,browser_name)
                    login_in_isard(wd,user,pwd)    
                    create_desktop_from_template(wd,name_desktop,kind_template,id_template)
                    num = num + 1
                    
            
            
    
