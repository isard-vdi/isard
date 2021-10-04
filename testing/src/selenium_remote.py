from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import Select

import urllib
import paramiko

from selenium.webdriver.support.ui import WebDriverWait

class IsardSelenium():
    def __init__(self, url='https://isard-portal',
                 username='admin',
                 password='IsardVDI',
                 launch = True,
                 browser = 'firefox',
                 hostname = False,
                 ssh = True,
                 ssh_username = 'admin',
                 ssh_passwd = 'IsardVDI',
                 ssh_port=22):


        self.hostname = hostname
        self.username = username
        self.password = password
        self.ssh = ssh
        self.ssh_username = ssh_username
        self.ssh_passwd = ssh_passwd
        self.ssh_port = ssh_port
        self.url = url

        self.wd = False
        self.wait = False

        self.profile = webdriver.FirefoxProfile()
        
        # Certs error ignore
        self.firefox_capabilities = DesiredCapabilities.FIREFOX
        self.firefox_capabilities['marionette'] = True
        self.firefox_capabilities['handleAlerts'] = True
        self.firefox_capabilities['acceptSslCerts'] = True
        self.firefox_capabilities['acceptInsecureCerts'] = True

        self.profile.set_preference("browser.download.manager.showWhenStarting", False)
        self.profile.set_preference("browser.download.dir", "/tmp/")
        self.profile.set_preference("browser.download.folderList", 2)
        self.profile.set_preference("browser.download.manager.focusWhenStarting",False)
        self.profile.set_preference("browser.download.manager.closeWhenDone",True)

        #Esto es lo más importante para que guarde a disco y no pida confirmación
        self.profile.set_preference("browser.helperApps.neverAsk.saveToDisk","application/x-virt-viewer")

        
        if hostname is not False:
            if browser == 'firefox':
                self.desired_caps = {'platform':'LINUX','browserName':'firefox'}
            elif browser == 'chrome':
                self.desired_caps = {'platform':'LINUX','browserName':'chrome'}
            else:
                raise ValueError('browser invalid')
        if browser == 'firefox':
            self.WDriver = webdriver.Firefox
        elif browser == 'chrome':
            self.WDriver = webdriver.Chrome
        else:
            raise ValueError('browser invalid')

        if launch is True:
            self.launch_wd()
        
    def launch_wd(self):
        if self.hostname is False:
            self.wd = self.WDriver()
            self.wd.get(self.url)
        else:
            try:
                self.wd = webdriver.Remote('http://{}:4444/wd/hub'.format(self.hostname),
                                       desired_capabilities=self.firefox_capabilities,
                                       browser_profile=self.profile)
                self.wait = WebDriverWait(self.wd, 20)
                self.wd.get(self.url)
            except urllib.error.URLError:
                print('Host {} no connectat'.format(self.hostname))

    def login(self):
        # Select category
        select_kind=Select(self.wd.find_element_by_xpath("//select"))
        select_kind.select_by_value('default')
        # Put username
        username = self.wd.find_element_by_xpath("//input[@placeholder='Username']")
        username.send_keys('admin')
        # Put password
        passwd = self.wd.find_element_by_xpath("//input[@placeholder='Password']")
        passwd.send_keys('IsardVDI')
        # Click login button
        button = self.wd.find_element_by_xpath("//button[contains(text(),'Login')]")
        button.click()

    def goToWebadmin(self):
        self.wd.get(self.url + '/isard-admin/desktops')