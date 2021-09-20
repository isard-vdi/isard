import os
from time import sleep

from stats import HypStats

hyp_hostname = os.environ.get('STATS_HYP_HOSTNAME', 'isard-hypervisor')
hyp_user = os.environ.get('STATS_HYP_USER', 'root')
hyp_port = int(os.environ.get('STATS_HYP_PORT', 2022))

send_to_influx = True if os.environ.get('STATS_SEND_TO_INFLUX', 'true') == 'true' else False
send_shutdown_if_no_viewer = True if os.environ.get('STATS_SEND_SHUTDOWN_IF_NO_VIEWER', 'true') == 'true' else False
url_api_shutdown = os.environ.get('STATS_SEND_SHUTDOWN_API_URL', 'http://isard-engine')
type_conn_ss = os.environ.get('STATS_TYPE_CONN_SS', 'docker')

h = HypStats(hyp_hostname=hyp_hostname,
             hyp_user=hyp_user,
             hyp_port=hyp_port,
             type_conn_ss=type_conn_ss)

while True:
    h.stats_loop()

