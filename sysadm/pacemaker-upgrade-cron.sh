#!/bin/sh -e

# In pacemaker environments you can set up compose resource with the same name as
# the IsardVDI config. For example:
# - Resource:     isard (ocf::heartbeat:compose):	Started cluster1-cs
# - Config:       isardvdi.isard.cfg
# The script will pull all the images coming from all *.cfg and will restart
# only the one's running in this pacemaker cluster.
# By default Hypervisor is excluded from restart. You can disable this by setting
# in environment EXCLUDE_HYPER=0

EXCLUDE_HYPER=${EXCLUDE_HYPER-1}

script_path=$(readlink -f "$0")
cfgs_path="${script_path%/*/*}"

ls $cfgs_path/isardvdi*.cfg | sed -n "s|^$cfgs_path/isardvdi\.\?\([^\.]*\)\.cfg$|\1|p" | while read config_name
do
    # Download newer images for each flavour but do not bring it up
    "${script_path%/*}"/isard-upgrade-cron.sh -c "$config_name" -n
    # Check which service is running in this host and restart only this one.
     server=$(pcs resource status | awk "/\s*$config_name\s+\(ocf::heartbeat:compose\):/{print \$NF}")
     if [ "$server" = "$(hostname)" ];then
         if [ $EXCLUDE_HYPER = 1 ]
         then
            services="$(docker-compose -f "$cfgs_path"/docker-compose.$config_name.yml config --services | sed '/^isard-\(hypervisor\|pipework\)$/d')"
         else
            services="$(docker-compose -f "$cfgs_path"/docker-compose.$config_name.yml config --services)"
         fi
         pcs resource unmanage $config_name \
         && docker-compose -f "$cfgs_path"/docker-compose.$config_name.yml --ansi never up -d $services \
         && pcs resource manage $config_name
         docker image prune -f --filter "until=72h"
     fi
done
