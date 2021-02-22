import os,time,requests,json,getpass

class ApiClient():
    def __init__(self):
        self.auth=('admin', os.environ['WEBAPP_ADMIN_PWD'])
        server=os.environ['STATS_RETHINKDB_HOST']
        if server=='isard-db':
            self.base_url="http://isard-api:7039/api/v2/"
            self.verifycert=False
        else:
            self.base_url="https://"+os.environ['STATS_RETHINKDB_HOST']+"/debug/api/api/v2/"
            self.verifycert=False
        

    def post(self,url,data):
        resp = requests.post(self.base_url+url, data=data, auth=self.auth, verify=self.verifycert)
        if resp.status_code == 200:
            return json.loads(resp.text)
        raise
