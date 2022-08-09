import urllib
from time import sleep

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait


class IsardSelenium:
    def __init__(
        self,
        url="https://isard-portal",
        username="admin",
        password="IsardVDI",
        launch=True,
        browser="firefox",
        hostname=False,
        ssh=True,
        ssh_username="admin",
        ssh_passwd="IsardVDI",
        ssh_port=22,
    ):

        self.hostname = hostname
        self.username = username
        self.user_id = "_local-default-" + self.username + "-" + self.username
        self.password = password
        self.browser = browser
        self.ssh = ssh
        self.ssh_username = ssh_username
        self.ssh_passwd = ssh_passwd
        self.ssh_port = ssh_port
        self.url = url

        self.wd = False
        self.wait = False

        if browser == "firefox":
            self.WDriver = webdriver.Firefox
            self.profile = webdriver.FirefoxProfile()
            self.desired_caps = {"platformName": "linux", "browserName": "firefox"}
            # Downloads dir conf
            self.profile.set_preference(
                "browser.download.manager.showWhenStarting", False
            )
            self.profile.set_preference("browser.download.dir", "/tmp/")
            self.profile.set_preference("browser.download.folderList", 2)
            self.profile.set_preference(
                "browser.download.manager.focusWhenStarting", False
            )
            self.profile.set_preference("browser.download.manager.closeWhenDone", True)
            # Esto es lo más importante para que guarde a disco y no pida confirmación
            self.profile.set_preference(
                "browser.helperApps.neverAsk.saveToDisk", "application/x-virt-viewer"
            )
            self.desired_caps = DesiredCapabilities.FIREFOX
        elif browser == "chrome":
            self.WDriver = webdriver.Chrome
            self.desired_caps = {"platformName": "linux", "browserName": "chrome"}
            self.desired_caps = DesiredCapabilities.CHROME
        elif browser == "edge":
            self.WDriver = webdriver.Edge
            self.desired_caps = {
                "platformName": "windows",
                "browserName": "MicrosoftEdge",
            }
            self.desired_caps = DesiredCapabilities.EDGE
        else:
            raise ValueError("browser invalid")
        # Certs error ignore
        self.desired_caps["marionette"] = True
        self.desired_caps["handleAlerts"] = True
        self.desired_caps["acceptSslCerts"] = True
        self.desired_caps["acceptInsecureCerts"] = True

        if launch:
            self.launch_wd()

    def launch_wd(self):
        if not self.hostname:
            self.wd = self.WDriver()
            self.wd.get(self.url)
        else:
            try:
                if self.browser == "firefox":
                    self.wd = webdriver.Remote(
                        "http://{}:4444/wd/hub".format(self.hostname),
                        desired_capabilities=self.desired_caps,
                        browser_profile=self.profile,
                    )
                elif self.browser == "chrome":
                    self.wd = webdriver.Remote(
                        "http://{}:4444/wd/hub".format(self.hostname),
                        desired_capabilities=self.desired_caps,
                    )
                else:
                    # TODO: Edge compatiblity
                    self.wd = webdriver.Edge(
                        "http://{}:4444/wd/hub".format(self.hostname),
                        capabilities=self.desired_caps,
                    )
                self.wait = WebDriverWait(self.wd, 20)
                self.wd.get(self.url)
            except urllib.error.URLError:
                print("Host {} no connectat".format(self.hostname))

    def frontendLogin(self):
        try:
            WebDriverWait(self.wd, 10).until(
                EC.presence_of_element_located((By.ID, "app"))
            )
        except Exception as e:
            print("!!!!ERROR: The login page isn't available")
        try:
            # Select category
            select_kind = Select(self.wd.find_element("xpath", "//select"))
            select_kind.select_by_value("default")
        except Exception as e:
            print("No category dropdown is available, skipping.")
        # Put username
        print("Introducing username.")
        username = self.wd.find_element("xpath", "//input[@placeholder='Username']")
        username.send_keys(self.username)
        # Put password
        print("Introducing password.")
        passwd = self.wd.find_element("xpath", "//input[@placeholder='Password']")
        passwd.send_keys(self.password)
        try:
            # Click login button
            print("Login in.")
            self.wd.find_element("xpath", "//button[contains(text(),'Login')]").click()
            return True
        except Exception as e:
            print("Error while loggin in.")

    def frontendLogout(self):
        try:
            WebDriverWait(self.wd, 10).until(
                EC.presence_of_element_located((By.ID, "app"))
            )
        except Exception as e:
            print("!!!!ERROR: The page isn't available")
        # Logout
        self.wd.find_element(
            "xpath",
            "//*[local-name()='svg' and @class='bi-power text-white b-icon bi']",
        ).click()
        return True

    def goToAdmin(self):
        try:
            # Checking that the page is loaded by looking for the navbar
            WebDriverWait(self.wd, 10).until(
                EC.presence_of_element_located((By.ID, "navbar"))
            )
        except Exception as e:
            print("!!!!ERROR: The navbar isn't available")
        # Administration page
        print("Redirecting to administration page.")
        self.wd.find_element("xpath", "//a[@href='/isard-admin/desktops']").click()
        return True

    def goToDownloads(self):
        try:
            # Checking that the page is loaded by looking for the sidebar
            WebDriverWait(self.wd, 10).until(
                EC.presence_of_element_located((By.ID, "sidebar-menu"))
            )
        except Exception as e:
            print("ERROR: The sidebar isn't available")
        # Downloads page
        self.wd.find_element("xpath", "//a[@href='/isard-admin/admin/updates']").click()
        return True

    def downloadDomains(self, domain_name):
        id_domain = self.user_id + "_" + domain_name
        try:
            print("Registering user.")
            self.wd.find_element(
                "xpath",
                "//form[@action='/isard-admin/admin/updates_register']//button[@id='register']",
            ).click()
        except Exception as e:
            print(
                "Tried to click on register but the user was already registered, skipping."
            )
        print("Attempting to download a resource:")
        try:
            WebDriverWait(self.wd, 10).until(
                EC.presence_of_element_located((By.ID, "domains_tbl_wrapper"))
            )
        except Exception as e:
            print("!!!!ERROR: The domains table isn't available")
        try:
            print("Downloading domain")
            self.wd.find_element(
                "xpath", "//tr[@id='" + id_domain + "']//button[@id='btn-download']"
            ).click()
        except Exception as e:
            print("Tried to download domain but it was already downloaded, skipping.")
        return True

    def checkDownloadedDomains(self, domain_name, wait_time):
        id_domain = self.user_id + "_" + domain_name
        try:
            print("Waiting for domain")
            WebDriverWait(self.wd, wait_time).until(
                EC.visibility_of_element_located(
                    (
                        By.XPATH,
                        "//tr[@id='"
                        + id_domain
                        + "']//td[@class='sorting_1']//span[@class='label label-info pull-right']",
                    )
                )
            )
            print("Domain DOWNLOADED")
            return True
        except Exception as e:
            print("Domain is not downloaded.")

    def goToHome(self):
        # Checking that the page is loaded by looking for the sidebar
        WebDriverWait(self.wd, 10).until(
            EC.presence_of_element_located((By.ID, "sidebar-menu"))
        )
        # Home page
        print("Redirecting to home page.")
        self.wd.find_element("xpath", "//a[@href='/']").click()
        return True

    def startDomain(self, domain_name):
        id_domain = self.user_id + "_" + domain_name
        try:
            WebDriverWait(self.wd, 10).until(
                EC.presence_of_element_located((By.ID, "desktops_wrapper"))
            )
        except Exception as e:
            print("!!!!ERROR: The domains table isn't available")
        try:
            WebDriverWait(self.wd, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//tr[@id='" + id_domain + "']//button[@id='btn-play']")
                )
            )
            self.wd.find_element(
                "xpath",
                (
                    "//table[@id='desktops']"
                    + "//tr[@id='{}']"
                    + "//button[@id='btn-play']"
                ).format(id_domain),
            ).click()
            sleep(5)
            self.wd.find_element(
                "xpath", "//div[@id='modalOpenViewer']//button[@class='close']"
            ).click()
            return True

        except Exception as e:
            print("Domain wasn't started.")

    def domainOpenViewer(self, domain_name, type):
        id_domain = self.user_id + "_" + domain_name
        try:
            WebDriverWait(self.wd, 10).until(
                EC.presence_of_element_located((By.ID, "desktops_wrapper"))
            )
        except Exception as e:
            print("!!!!ERROR: The domains table isn't available")
        try:
            WebDriverWait(self.wd, 10).until(
                EC.presence_of_element_located(
                    (
                        By.XPATH,
                        "//tr[@id='" + id_domain + "']//button[@id='btn-display']",
                    )
                )
            )
            self.wd.find_element(
                "xpath",
                (
                    "//table[@id='desktops']"
                    + "//tr[@id='{}']"
                    + "//button[@id='btn-display']"
                ).format(id_domain),
            ).click()
            sleep(5)
            self.wd.find_element(
                "xpath", "//div[@id='modalOpenViewer']//button[@data-type='vnc']"
            ).click()
            return True

        except Exception as e:
            print("Domain wasn't started.")

    # TODO: Check VNC viewer
    def checkBrowserViewer(self):
        self.wd.switch_to.window(self.wd.window_handles[-1])
        WebDriverWait(self.wd, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, "//div[@id='top_bar']//div[@id='status']")
            )
        )
        return (
            self.wd.find_element(
                "xpath", "//div[@id='top_bar']//div[@id='status']"
            ).text
            == "IsardVDI.com"
        )

    def stopDomain(self, domain_name):
        id_domain = self.user_id + "_" + domain_name
        try:
            WebDriverWait(self.wd, 10).until(
                EC.presence_of_element_located((By.ID, "desktops_wrapper"))
            )
        except Exception as e:
            print("!!!!ERROR: The domains table isn't available")
        try:
            self.wd.find_element(
                "xpath",
                (
                    "//table[@id='desktops']"
                    + "//tr[@id='{}']"
                    + "//button[@id='btn-stop']"
                ).format(id_domain),
            ).click()
            sleep(2)
            # Force stop
            self.wd.find_element(
                "xpath",
                (
                    "//table[@id='desktops']"
                    + "//tr[@id='{}']"
                    + "//button[@id='btn-stop']"
                ).format(id_domain),
            ).click()
            # popup message to confirmation destroy
            self.wd.find_element(
                "xpath", "//div[@role='alert']/.//button[contains(text(),'Ok')]"
            ).click()
            return True

        except Exception as e:
            print("Domain wasn't stopped.")

    def deleteDomain(self, domain_name):
        id_domain = self.user_id + "_" + domain_name
        WebDriverWait(self.wd, 10).until(
            EC.presence_of_element_located(
                (By.XPATH, "//tr[@id='" + id_domain + "']//button[@id='btn-play']")
            )
        )
        try:
            self.wd.find_element(
                "xpath",
                (
                    "//table[@id='desktops']"
                    + "//tr[@id='{}']"
                    + "//button[@class='btn btn-xs btn-info']"
                ).format(id_domain),
            ).click()
            sleep(0.2)
            self.wd.find_element(
                "xpath",
                (
                    "//div[@id='actions-{}']"
                    + "//button[contains(@class,'btn-delete')]"
                ).format(id_domain),
            ).click()
            # popup message to confirmation destroy
            self.wd.find_element(
                "xpath", "//div[@role='alert']/.//button[contains(text(),'Ok')]"
            ).click()
            return True

        except WebDriverException as e:
            print("error in webdriver: ", e)
