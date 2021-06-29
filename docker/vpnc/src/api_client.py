import os,time,requests,json,getpass
import traceback

class ApiClient():
    def __init__(self):
        self.auth=('admin', os.environ['WEBAPP_ADMIN_PWD'])
        if os.environ['HOSTNAME']=='localhost':
            self.base_url="http://isard-api:7039/api/v2/"
        else:
            self.base_url="https://"+os.environ['WEPAPP_DOMAIN']+"/debug/api/api/v2/"
        self.verifycert=False
        

    def post(self,url,data):
        resp = requests.post(self.base_url+url, data=data, auth=self.auth, verify=self.verifycert)
        if resp.status_code == 200:
            return json.loads(resp.text)
        raise

    def get(self,url):
        resp = requests.get(self.base_url+url, auth=self.auth, verify=self.verifycert)
        if resp.status_code == 200:
            return json.loads(resp.text)
        raise