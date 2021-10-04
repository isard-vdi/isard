from selenium_remote import IsardSelenium

i = IsardSelenium(hostname='selenium-hub')
i.login()
i.goToWebadmin()