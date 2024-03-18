import time

import pytest
from selenium_remote import IsardSelenium

GLOBAL = {
    "admin_desktops_title": "Desktops | Isard VDI",
    "admin_desktops_url_suffix": "/isard-admin/desktops",
    "admin_downloads_title": "Downloads | Isard VDI",
    "admin_downloads_url_suffix": "/isard-admin/admin/updates",
}


# TODO: Edge implementation
# @pytest.fixture(params=["chrome", "firefox", "edge"], scope="class")
@pytest.fixture(params=["chrome", "firefox"], scope="class")
def driver_init_login(request):
    if request.param == "chrome":
        isard_selenium = IsardSelenium(hostname="selenium-hub", browser="chrome")
    if request.param == "firefox":
        isard_selenium = IsardSelenium(hostname="selenium-hub", browser="firefox")
    if request.param == "edge":
        isard_selenium = IsardSelenium(hostname="selenium-hub", browser="edge")
    web_driver = isard_selenium.wd
    request.cls.driver = web_driver
    request.cls.isard_selenium = isard_selenium
    request.cls.isard_selenium.frontendLogin()
    yield
    request.cls.isard_selenium.wd.get(request.cls.isard_selenium.url)
    request.cls.isard_selenium.frontendLogout()
    isard_selenium.wd.quit()


@pytest.mark.usefixtures("driver_init_login")
class BasicTest:
    pass


# Downloads tetrOS and checks that browser viewer works correctly
class Test_Domains(BasicTest):
    @pytest.mark.skip(reason="test in development")
    def test_goToAdmin(self):
        assert self.isard_selenium.goToAdmin() == True
        time.sleep(1)
        assert GLOBAL["admin_desktops_title"] == self.isard_selenium.wd.title
        assert (
            self.isard_selenium.url + GLOBAL["admin_desktops_url_suffix"]
            == self.isard_selenium.wd.current_url
        )

    @pytest.mark.skip(reason="test in development")
    def test_goToDownloads(self):
        if (
            self.isard_selenium.url + GLOBAL["admin_desktops_url_suffix"]
            != self.isard_selenium.wd.current_url
        ):
            self.isard_selenium.get(
                self.isard_selenium.url + GLOBAL["admin_desktops_url_suffix"]
            )
        assert self.isard_selenium.goToDownloads() == True
        time.sleep(1)
        assert GLOBAL["admin_downloads_title"] == self.isard_selenium.wd.title
        assert (
            self.isard_selenium.url + GLOBAL["admin_downloads_url_suffix"]
            == self.isard_selenium.wd.current_url
        )

    @pytest.mark.skip(reason="test in development")
    def test_download_domain(self):
        assert self.isard_selenium.downloadDomains("downloaded_tetros") == True

    @pytest.mark.skip(reason="test in development")
    def test_downloaded_domains(self):
        assert (
            self.isard_selenium.checkDownloadedDomains("downloaded_tetros", 30) == True
        )

    @pytest.mark.skip(reason="test in development")
    def test_start_domain(self):
        if (
            self.isard_selenium.url + GLOBAL["admin_desktops_url_suffix"]
            != self.isard_selenium.wd.current_url
        ):
            self.isard_selenium.wd.get(
                self.isard_selenium.url + GLOBAL["admin_desktops_url_suffix"]
            )
        time.sleep(1)
        assert self.isard_selenium.startDomain("downloaded_tetros") == True

    @pytest.mark.skip(reason="test in development")
    def test_stop_domain(self):
        if (
            self.isard_selenium.url + GLOBAL["admin_desktops_url_suffix"]
            != self.isard_selenium.wd.current_url
        ):
            self.isard_selenium.wd.get(
                self.isard_selenium.url + GLOBAL["admin_desktops_url_suffix"]
            )
        time.sleep(1)
        assert self.isard_selenium.stopDomain("downloaded_tetros") == True

    @pytest.mark.skip(reason="test in development")
    def test_delete_domain(self):
        if (
            self.isard_selenium.url + GLOBAL["admin_desktops_url_suffix"]
            != self.isard_selenium.wd.current_url
        ):
            self.isard_selenium.wd.get(
                self.isard_selenium.url + GLOBAL["admin_desktops_url_suffix"]
            )
        time.sleep(1)
        assert self.isard_selenium.deleteDomain("downloaded_tetros") == True
