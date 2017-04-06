from time import sleep
from engine.manager_hypervisors import ManagerHypervisors
from engine.functions import get_threads_running
from engine.functions import check_tables_populated

check_tables_populated()
m=ManagerHypervisors()
sleep(10)
get_threads_running()

while m.quit is False:
    sleep(1)