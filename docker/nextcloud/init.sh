
# https://docs.nextcloud.com/server/latest/admin_manual/installation/server_tuning.html#tune-php-fpm
# https://spot13.com/pmcalculator/
sed -i \
	-e 's/pm.max_children.*=.*/pm.max_children='"$FPM_MAX_CHILDREN"'/g' \
	-e 's/pm.start_servers.*=.*/pm.start_servers='"$FPM_START_SERVERS"'/g' \
	-e 's/pm.min_spare_servers.*=.*/pm.min_spare_servers='"$FPM_MIN_SPARE_SERVERS"'/g' \
	-e 's/pm.max_spare_servers.*=.*/pm.max_spare_servers='"$FPM_MAX_SPARE_SERVERS"'/g' \
	-e 's/pm.max_requests.*=.*/pm.max_requests='"$FPM_MAX_REQUESTS"'/g' \
	-e 's/pm.process_idle_timeout.*=.*/pm.process_idle_timeout='"$FPM_PROCESS_IDLE_TIMEOUT"'/g' \
		/usr/local/etc/php-fpm.d/www.conf

# https://github.com/nextcloud/server/pull/35873
# while /usr/local/bin/php occ status -e
# while "! f /var/www/html/nextcloud-init-sync.lock"

run_occ() {
	su -p "www-data" -s /bin/sh -c "/usr/local/bin/php occ $1"
}

# Nextcloud 27 recommends to run the following commands:
run_occ "db:add-missing-indices"

# Set Logo and Background
instance_id=$(run_occ "config:system:get instanceid")
cb=$(run_occ "config:app:get theming cachebuster")
cachebuster_cmd="config:app:set theming cachebuster --value=\"$((cb + 1 ))\""
mkdir -p ./data/appdata_$instance_id/theming/global/images

convert -resize 300x300 -fuzz 0 -transparent white \
	/ctheming/images/logo.svg /tmp/logo.png
mv /tmp/logo.png ./data/appdata_$instance_id/theming/global/images/logo
chown www-data:www-data ./data/appdata_$instance_id/theming/global/images/logo
run_occ 'config:app:set theming logoMime --value="image/png"'

cp /ctheming/background.jpg ./data/appdata_$instance_id/theming/global/images/background
chown www-data:www-data ./data/appdata_$instance_id/theming/global/images/background
run_occ 'config:app:set theming backgroundMime --value="image/jpg"'

run_occ "$cachebuster_cmd"

# Config
run_occ 'config:system:set skeletondirectory --value=""'
run_occ 'config:app:set settings profile_enabled_by_default --value="0"'
run_occ 'config:system:set default_language --value="ca"'
run_occ 'config:system:set allow_local_remote_servers  --value=true'

# Disable apps
run_occ 'app:disable firstrunwizard'
run_occ 'app:disable recommendations'
run_occ 'app:disable dashboard'
run_occ 'app:disable circles'

# Install new apps
run_occ 'app:install bruteforcesettings'
run_occ 'config:app:set -n bruteForce whitelist_1 --value="172.16.0.0/12"'
run_occ 'app:enable bruteforcesettings'

# Monitoring
# URL: https://<DOMAIN>/isard-nc/ocs/v2.php/apps/serverinfo/api/v1/info?format=json
# HEADER: NC-Token: <TOKEN>
# TOKEN: occ config:app:get serverinfo token

# Self register
# NOTE: Will recreate a new app token at each restart and will invalidate the previous ones
# Needs to be in background as api will check that Nextcloud is up and running
if [ ! $NEXTCLOUD_AUTO_REGISTER || $NEXTCLOUD_AUTO_REGISTER == "true" ];
then
	python3 /src/authenticate.py &
else
	echo "NEXTCLOUD_AUTO_REGISTER not set, skipping self register"
fi

# Start nextcloud
/usr/bin/supervisord -c /supervisord.conf

