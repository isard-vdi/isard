from time import sleep

from engine.models.manager_hypervisors import ManagerHypervisors
from engine.services.lib.functions import check_tables_populated
from engine.services.lib.functions import get_threads_running

check_tables_populated()
m=ManagerHypervisors(with_status_threads=False)
sleep(10)
get_threads_running()

while m.quit is False:
    sleep(1)
