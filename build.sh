#!/bin/sh
set -e

if [ ! $(which docker) ]; then
	echo "REQUIREMENT: docker not found in system."
	echo "             Follow guide at https://docs.docker.com/engine/install/"
	echo "             or use scripts in sysadmin folder."
	exit 1
fi

if [ ! $(which docker-compose) ]; then
	echo "REQUIREMENT: docker-compose not found in system."
	echo "             Follow guide at https://docs.docker.com/compose/install/"
	echo "             or use scripts in sysadmin folder."
	exit 1
fi

# We need docker-compose >= 1.28 to use service profiles
# docker-compose >= 1.27.3 to use depends_on with service_healthy
# docker-compose < 1.26 preserves environment variable quotations
# Use SKIP_CHECK_DOCKER_COMPOSE_VERSION=true environment variable to skip the check
REQUIRED_DOCKER_COMPOSE_VERSION="1.28"

GITLAB_PROJECT_ID="21522757"
CHANGELOG_URL="https://gitlab.com/isard/isardvdi/-/releases/"

PARTS_PATH=docker-compose-parts
ALLINONE_KEY="all-in-one"
ALLINONE_PARTS="
	network
	db
	engine
	static
	portal
	hypervisor
	websockify
	squid
	webapp
	stats
	api
	authentication
	vpn
	guac
	toolbox
	backupninja
"
HYPERVISOR_KEY="hypervisor"
HYPERVISOR_PARTS="
	network
	video
	hypervisor
	websockify
	squid
	stats
	guac
	guac-vpnc
"
HYPERVISOR_STANDALONE_KEY="hypervisor-standalone"
HYPERVISOR_STANDALONE_PARTS="
	network
	hypervisor
	hypervisor-standalone
	stats
"
VIDEO_STANDALONE_KEY="video-standalone"
VIDEO_STANDALONE_PARTS="
	network
	video
	websockify
	squid
	guac
"
TOOLBOX_KEY="toolbox"
TOOLBOX_PARTS="
	network
	toolbox
"
TOOLBOXBASE_KEY="toolbox-base"
TOOLBOXBASE_PARTS="
	toolbox-base
"
WEB_KEY="web"
WEB_PARTS="
	network
	db
	engine
	static
	portal
	webapp
	api
	authentication
	vpn
"

docker_compose_version(){
	docker-compose --version | sed 's/^docker-compose version \([^,]\+\),.*$/\1/'
}

check_docker_compose_version(){
	# We cannot use sort -C because is not included in BusyBox v1.33.1 of docker:dind image
	{
		echo "$REQUIRED_DOCKER_COMPOSE_VERSION"
		docker_compose_version
	} | sort -c -V 2> /dev/null
}

get_config_files(){
	ls isardvdi*.cfg
}

get_config_name(){
	echo "$1" | sed -n 's/^isardvdi\.\?\(.*\)\.cfg$/\1/p'
}

is_official_build(){
	if \
		${GITLAB_CI-false} \
		&& [ "$CI_PROJECT_ID" = "$GITLAB_PROJECT_ID" ] \
		&& (
			[ "$CI_COMMIT_BRANCH" = "$CI_DEFAULT_BRANCH" ] \
			|| echo "$CI_COMMIT_TAG" | grep -q "^v"
		)
	then
		return 0
	else
		return 1
	fi
}

create_env(){
	cp "$1" .env
	## BUILD_ROOT_PATH env
	# This is a workarround for
	# https://github.com/docker/compose/issues/7873
	# See also BUILD_ROOT_PATH sed section at the end of file
	echo "BUILD_ROOT_PATH=$(pwd)" >> .env
	. ./.env
	# Only display numbered version in official builds via gitlab-ci
	if is_official_build && test -e .VERSION
	then
		version="$(cat .VERSION)"
		version_date="$(date +%Y-%m-%d)"
		version_id="$version $version_date"
		echo SRC_VERSION_ID="$version_id" >> .env
		echo SRC_VERSION_LINK="${CHANGELOG_URL}v${version}" >> .env
	else
		echo SRC_VERSION_LINK= >> .env
		if [ -n "$CI_COMMIT_REF_SLUG" ]
		then
			echo SRC_VERSION_ID="$CI_COMMIT_REF_SLUG" >> .env
		else
			version="$(git name-rev --name-only --always --no-undefined HEAD)"
			if ! git diff --quiet
			then
				version="$version-dirty"
			fi
			echo SRC_VERSION_ID="$version" >> .env
		fi
	fi
}

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
	local config_name="$1"
	shift || return 0
	local args="$(parts_files $@)"
	if [ -n "$*" -a -n "$args" ]
	then
		if [ -z "$config_name" ]
		then
			local delimiter=""
		else
			local delimiter="."
		fi
		docker-compose $args config > "docker-compose$delimiter$config_name.yml"
	fi
}
parts_variant(){
	local variant="$1"
	shift || return 0
	for part in $@
	do
		if ! echo $parts | grep -q "\(^\|\s\)$part\(\s\|$\)"
		then
			parts="$parts $part "
		fi
		parts="$parts $part.$variant "
	done
	echo -n $parts
}
variants(){
	local config_name="$1"
	shift || return 0
	if check_docker_compose_version
	then
		local version="current"
	else
		local version="legacy"
	fi
	case $USAGE in
		production)
			merge "$config_name" $(parts_variant $version $(parts_variant $FLAVOUR $@))
			;;
		test)
			merge "$config_name" $(parts_variant $version $(parts_variant $FLAVOUR $@) $(parts_variant test $@))
			;;
		build)
			merge "$config_name" $(parts_variant $version $(parts_variant $FLAVOUR $@) $(parts_variant test $@) $(parts_variant build $@))
			;;
		devel)
			merge "$config_name" $(parts_variant $version $(parts_variant $FLAVOUR $@) $(parts_variant test $@) $(parts_variant build $@) $(parts_variant devel $@))
			;;
		*)
			echo "Error: unknow usage $USAGE"
			exit 1
			;;
	esac
}
flavour(){
## Usage of flavour function
#
# flavour <config-name> <part-1> <part-2> ...
# - <config-name> is used for the filename: docker-compose.<config-name>.yml
# - <part-1> and <part-2> ... should be files like:
# docker-compose-parts/<part>[.<current/legacy>].yml
# docker-compose-parts/<part>.<test/build/devel>[.<current/legacy>].yml
# docker-compose-parts/<part>.<flavour>[.<current/legacy>].yml

	local config_name="$1"
	shift || return 0
	local parts=""
	for part in $@
	do
		parts="$parts $part"
		if [ "$part" = "hypervisor" -a -n "$HYPERVISOR_HOST_TRUNK_INTERFACE" ]
		then
			parts="$parts hypervisor-vlans"
                        echo "WARNING: Will take host interface $HYPERVISOR_HOST_TRUNK_INTERFACE and put it inside hypervisor container"
                        echo "         So interface WILL DISSAPPEAR from host"
                        echo "         With this configuration, when you restart container the interface could be missing,"
                        echo "         so, better do 'docker-compose  -f docker-compose.hypervisor.yml down' and wait a minute"
                        echo "         till the interface $HYPERVISOR_HOST_TRUNK_INTERFACE is visible in the host again!"
                        echo ""
		fi
	done
	variants "$config_name" $parts
}

create_docker_compose_file(){
	config_file="$1"
	create_env "$config_file"
	config_name="$(get_config_name "$config_file")"

	if [ -z "$USAGE" ]
	then
		USAGE="production"
	fi
	if [ -z "$ENABLE_STATS" ]
	then
		ENABLE_STATS="true"
	fi
	if [ -z "$BACKUP_DB_ENABLED" ]
	then
		BACKUP_DB_ENABLED="false"
	fi
	if [ -z "$BACKUP_DISKS_ENABLED" ]
	then
		BACKUP_DISKS_ENABLED="false"
	fi
	if [ -z "$FLAVOUR" ]
	then
		FLAVOUR="all-in-one"
	fi
	case $FLAVOUR in
		$ALLINONE_KEY)
			parts=$ALLINONE_PARTS
			;;
		$HYPERVISOR_KEY)
		  parts=$HYPERVISOR_PARTS
			;;
		$HYPERVISOR_STANDALONE_KEY)
			parts=$HYPERVISOR_STANDALONE_PARTS
			;;
		$VIDEO_STANDALONE_KEY)
			parts=$VIDEO_STANDALONE_PARTS
			;;
		$TOOLBOX_KEY)
			parts=$TOOLBOX_PARTS
			;;
		$TOOLBOXBASE_KEY)
			parts=$TOOLBOXBASE_PARTS
			;;
		$WEB_KEY)
			parts=$WEB_PARTS
			;;
		*)
			echo "Error: Flavour $FLAVOUR of $config_file not found"
			exit 1
			;;
	esac

	if [ -n "$ENABLE_STATS" -a "$ENABLE_STATS" != "true" ]
	then
		parts="$(echo $parts | sed 's/stats//')"
	fi
	if [ "$BACKUP_DB_ENABLED" = "false" ] && [ "$BACKUP_DISKS_ENABLED" = "false" ]
	then
		parts="$(echo $parts | sed 's/backupninja//')"
	fi
	flavour "$config_name" $parts
}

if !(${SKIP_CHECK_DOCKER_COMPOSE_VERSION-false} || check_docker_compose_version)
then
	echo "ERROR: Please use docker-compose greather than or equal to $REQUIRED_DOCKER_COMPOSE_VERSION.
Use SKIP_CHECK_DOCKER_COMPOSE_VERSION=true environment variable to skip the check" >&2
	exit 1
fi

git submodule init
git submodule update --recursive --remote

get_config_files | while read config_file
do
	(create_docker_compose_file "$config_file")
done

## BUILD_ROOT_PATH sed section
# Fix the context parameter in the docker-compose file
# See also BUILD_ROOT_PATH env section above
sed -i "s|$(pwd)|.|g" docker-compose*.yml

echo "You have the docker-compose files. Have fun!"
echo "You can download the prebuild images and bring it up:"
echo "   docker-compose pull && docker-compose up -d"
echo "Or build it yourself:"
echo "   docker-compose build && docker-compose up -d"
