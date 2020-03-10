if [ -z $1 ]; then
	echo "You must provide <on> or <off> parameter"
	exit 1
fi
if [ "$1" = "on" ]; then
	rm /etc/nginx/maintenance.conf
	cp /maintenance.conf /etc/nginx/
	nginx -s reload
	echo "Maintenance mode active"
	exit 0
fi
if [ "$1" = "off" ]; then
	rm /etc/nginx/maintenance.conf
	touch /etc/nginx/maintenance.conf
	nginx -s reload
	echo "Maintenance mode disabled"
	exit 0
fi
echo "You must provide <on> or <off> parameter"
exit 1

