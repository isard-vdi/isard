#!/bin/sh -e

# In pacemaker environments you can set up compose resource with the same name as
# the IsardVDI config. For example:
# - Resource:     isard (ocf::heartbeat:compose):	Started cluster1-cs
# - Config:       isardvdi.isard.cfg
# Then set the configs/resource names that should be pulled and checked for restart.

CONFIGS="isard hyper1 hyper2"
EXCLUDE_HYPER=1

for CONFIG_NAME in $CONFIGS; do
    # Download newer images for each flavour but do not bring it up
    ./isard-upgrade-cron.sh -c $config -n
    # Check which service is running in this host and restart only this one.
     server=$(pcs resource status | awk "/\s*$CONFIG_NAME\s+\(ocf::heartbeat:compose\):/{print \$NF}")
     if [ "$server" = "$(hostname)" ];then
         if [ $EXCLUDE_HYPER = 1 ]
         then
            services="$(docker-compose -f ../docker-compose.$CONFIG_NAME.yml config --services | sed '/^isard-\(hypervisor\|pipework\)$/d')"
         else
            services="$(docker-compose -f ../docker-compose.$CONFIG_NAME.yml config --services)"
         fi
         pcs resource unmanage $CONFIG_NAME \
         && docker-compose -f ../docker-compose.$CONFIG_NAME.yml up -d $services \
         && pcs resource manage $CONFIG_NAME
     fi
done
