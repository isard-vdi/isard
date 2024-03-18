import time

import pytest
from selenium_remote import IsardSelenium

GLOBAL = {
    "frontend_login_url_suffix": "/login",
    "frontend_landing_url_suffix": "/desktops",
    "admin_desktops_title": "Desktops | Isard VDI",
    "admin_desktops_url_suffix": "/isard-admin/desktops",
}


# TODO: Edge implementation
# @pytest.fixture(params=["chrome", "firefox", "edge"], scope="class")
@pytest.fixture(params=["chrome", "firefox"], scope="class")
def driver_init(request):
    if request.param == "chrome":
        isard_selenium = IsardSelenium(hostname="selenium-hub", browser="chrome")
    if request.param == "firefox":
        isard_selenium = IsardSelenium(hostname="selenium-hub", browser="firefox")
    if request.param == "edge":
        isard_selenium = IsardSelenium(hostname="selenium-hub", browser="edge")
    web_driver = isard_selenium.wd
    request.cls.driver = web_driver
    request.cls.isard_selenium = isard_selenium
    yield
    isard_selenium.wd.quit()


@pytest.mark.usefixtures("driver_init")
class BasicTest:
    pass


# Tests login and logout in frontend and admin
class Test_Frontend_Login_Logout(BasicTest):
    @pytest.mark.skip(reason="test in development")
    def test_frontend_login(self):
        assert (
            self.isard_selenium.url + GLOBAL["frontend_login_url_suffix"]
            == self.isard_selenium.wd.current_url
        )
        assert self.isard_selenium.frontendLogin() == True
        time.sleep(1)
        assert (
            self.isard_selenium.url + GLOBAL["frontend_landing_url_suffix"]
            == self.isard_selenium.wd.current_url
        )

    @pytest.mark.skip(reason="test in development")
    def test_frontend_logout(self):
        assert self.isard_selenium.frontendLogout() == True
        time.sleep(1)
        assert (
            self.isard_selenium.url + GLOBAL["frontend_login_url_suffix"]
            == self.isard_selenium.wd.current_url
        )
