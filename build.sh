#!/bin/sh
set -e

git submodule init
git submodule update --recursive --remote

cp isardvdi.cfg .env
## BUILD_ROOT_PATH env
# This is a workarround for
# https://github.com/docker/compose/issues/7873
# See also BUILD_ROOT_PATH sed section at the end of file
echo "BUILD_ROOT_PATH=$(pwd)" >> .env

. ./.env
PARTS_PATH=docker-compose-parts

parts_files(){
	for part in $@
	do
		local file="$PARTS_PATH/$part.yml"
		if [ -f "$file" ]
		then
			echo -n "-f $file "
		fi
	done
}
merge(){
	local flavour="$1"
	shift || return 0
	local args="$(parts_files $@)"
	if [ -n "$*" -a -n "$args" ]
	then
		if [ -z "$flavour" ]
		then
			local delimiter=""
		else
			local delimiter="."
		fi
		docker-compose $args config > "docker-compose$delimiter$flavour.yml"
	fi
}
parts_variant(){
	local variant="$1"
	shift || return 0
	for part in $@
	do
		echo -n "$part.$variant "
	done
}
variants(){
	local flavour="$1"
	shift || return 0
	if [ -z "$flavour" ]
	then
		local delimiter=""
	else
		local delimiter="."
	fi
	merge "$flavour" $@
	merge "$flavour${delimiter}build" $@ $(parts_variant build $@)
	merge "$flavour${delimiter}devel" $@ $(parts_variant build $@) $(parts_variant devel $@)
}
flavour(){
	local flavour="$1"
	shift || return 0
	local no_stats_parts=""
	local parts=""
	for part in $@
	do
		parts="$parts $part"
		if [ "$part" = "hypervisor" -a -n "$HYPERVISOR_HOST_TRUNK_INTERFACE" ]
		then
			parts="$parts hypervisor-vlans"
			no_stats_parts="$no_stats_parts hypervisor-vlans"
		fi
		if [ "$part" != "stats" ]
		then
			no_stats_parts="$no_stats_parts $part"
		fi
	done
	if [ -n "$no_stats_parts" -a "$no_stats_parts" != " network" ]
	then
		if [ -z "$flavour" ]
		then
			local delimiter=""
		else
			local delimiter="."
		fi
		variants "$flavour${delimiter}no-stats" $no_stats_parts
	fi
	variants "$flavour" $parts
}

## Usage of flavour function
#
# flavour <flavour-name> <part-1> <part-2> ...
# - <flavour-name> is used for the filename: docker-compose.<flavour-name>.yml
# - <part-1> and <part-2> ... shoud be files like docker-compose-parts/<part-1>.yml
# - variants build and devel sould be like docker-compose-parts/<part-1>.build.yml
# and docker-compose-parts/<part-1>.devel.yml
#
flavour "" \
	network \
	db \
	engine \
	static \
	portal \
	hypervisor \
	websockify \
	squid \
	webapp \
	grafana \
	stats \
	api \
	backend \
	vpn \

flavour hypervisor \
	network \
	video \
	hypervisor \
	websockify \
	squid \
	stats \

flavour hypervisor-standalone \
	network \
	hypervisor \
	hypervisor-standalone \
	stats \

flavour video-standalone \
	network \
	video \
	websockify \
	squid \
	stats \

flavour web \
	network \
	db \
	engine \
	static \
	portal \
	webapp \
	grafana \
	stats \
	api \
	backend \

flavour stats \
	network \
	stats \

## BUILD_ROOT_PATH sed section
# Fix the context parameter in the docker-compose file
# See also BUILD_ROOT_PATH env section above
sed -i "s|$(pwd)|.|g" docker-compose*.yml

echo "You have the docker-compose files. Have fun!"
echo "You can download the prebuild images and bring it up:"
echo "   docker-compose pull && docker-compose up -d"
echo "Or build it yourself:"
echo "   docker-compose build && docker-compose up -d"
