#!/bin/sh
set -e

if [ ! $(which docker) ]; then
	echo "REQUIREMENT: docker not found in system."
	echo "             Follow guide at https://docs.docker.com/engine/install/"
	echo "             or use scripts in sysadmin folder."
	exit 1
fi

if [ ! "$(docker compose version 2> /dev/null)" ]; then

	if [ ! $(which docker-compose) ]; then
		echo "REQUIREMENT: docker-compose not found in system."
		echo "             Follow guide at https://docs.docker.com/compose/install/"
		echo "             or use scripts in sysadmin folder."
		exit 1

	else
		export DOCKER_COMPOSE="docker-compose"
	fi
else
	export DOCKER_COMPOSE="docker compose"
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
	db-stats
	engine
	static
	portal
	hypervisor
	websockify
	squid
	squid-hypervisor
	webapp
	stats
	monitor
	api
	scheduler
	authentication
	vpn
	guac
	redis
	storage
	backupninja
	core_worker
	nc
	postgres
	infrastructure
	check
	notifier
	sessions
	bastion
"
HYPERVISOR_KEY="hypervisor"
HYPERVISOR_PARTS="
	network
	video
	hypervisor
	websockify
	squid
	squid-hypervisor
	stats
	storage
	backupninja
"
HYPERVISOR_STANDALONE_KEY="hypervisor-standalone"
HYPERVISOR_STANDALONE_PARTS="
	network
	hypervisor
	stats
	storage
	backupninja
"
VIDEO_STANDALONE_KEY="video-standalone"
VIDEO_STANDALONE_PARTS="
	network
	video
	websockify
	squid
	stats
"
STORAGE_KEY="storage"
STORAGE_PARTS="
	network
	storage
	stats
	backupninja
"
WEB_KEY="web"
WEB_PARTS="
	network
	db
	db-stats
	engine
	static
	portal
	webapp
	api
	scheduler
	authentication
	vpn
	stats
	guac
	redis
	core_worker
	nc
	postgres
	infrastructure
	notifier
	sessions
	bastion
	backupninja
"
MONITOR_STANDALONE_KEY="monitor"
MONITOR_STANDALONE_PARTS="
	network
	stats
	monitor
	monitor-proxy
"
WEB_MONITOR_KEY="web+monitor"
# We remove the stats part, since it's already in the web parts. Also the proxy, since web already has one
WEB_MONITOR_PARTS="
	$WEB_PARTS
	$(echo "$MONITOR_STANDALONE_PARTS" | sed -e '/stats/d' -e '/monitor-proxy/d')
"

BACKUPNINJA_STANDALONE_KEY="backupninja"
BACKUPNINJA_STANDALONE_PARTS="
	network
	backupninja
"

CHECK_STANDALONE_KEY="check"
CHECK_STANDALONE_PARTS="
	network
	check
"

NEXTCLOUD_INSTANCE_KEY="nextcloud"
NEXTCLOUD_INSTANCE_PARTS="
	network
	postgres
	nc
	nc-proxy
"

# BASE image builds
HAPROXY_BUILD_KEY="haproxy"
HAPROXY_BUILD_PARTS="
	haproxy
"
docker_compose_version(){
	$DOCKER_COMPOSE version --short | sed 's/^docker-compose version \([^,]\+\),.*$/\1/'
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
	local version_args="$1"
	shift || return 0
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
		$DOCKER_COMPOSE $version_args $args config > "docker-compose$delimiter$config_name.yml"
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
		# docker-compose config v2 hide not specified profiles
		local version_args="--profile test"
	else
		local version="legacy"
		local version_args=""
	fi
	case $USAGE in
		production)
			merge "$version_args" "$config_name" $(parts_variant $version $(parts_variant $FLAVOUR $@))
			;;
		build)
			merge "$version_args" "$config_name" $(parts_variant $version $(parts_variant $FLAVOUR $@) $(parts_variant build $@))
			;;
		test)
			merge "$version_args" "$config_name" $(parts_variant $version $(parts_variant $FLAVOUR $@) $(parts_variant build $@) $(parts_variant test $@))
			;;
		devel)
			merge "$version_args" "$config_name" $(parts_variant $version $(parts_variant $FLAVOUR $@) $(parts_variant test $@) $(parts_variant build $@) $(parts_variant devel $@))
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
                        echo "         so, better do '$DOCKER_COMPOSE  -f docker-compose.hypervisor.yml down' and wait a minute"
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
	if [ -z "$GOLANG_BUILD_IMAGE" ]
	then
		export GOLANG_BUILD_IMAGE="golang:1.23-alpine3.20"
	fi
	if [ -z "$GOLANG_RUN_IMAGE" ]
	then
		export GOLANG_RUN_IMAGE="alpine:3.20"
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
		$STORAGE_KEY)
			parts=$STORAGE_PARTS
			;;
		$WEB_KEY)
			parts=$WEB_PARTS
			;;
		$MONITOR_STANDALONE_KEY)
			parts=$MONITOR_STANDALONE_PARTS
			;;
		$WEB_MONITOR_KEY)
			parts=$WEB_MONITOR_PARTS
			;;
		$BACKUPNINJA_STANDALONE_KEY)
			parts=$BACKUPNINJA_STANDALONE_PARTS
			;;
		$CHECK_STANDALONE_KEY)
			parts=$CHECK_STANDALONE_PARTS
			;;
		$NEXTCLOUD_INSTANCE_KEY)
			parts=$NEXTCLOUD_INSTANCE_PARTS
			;;
		$HAPROXY_BUILD_KEY)
			parts=$HAPROXY_BUILD_PARTS
			;;
		*)
			echo "Error: Flavour $FLAVOUR of $config_file not found"
			exit 1
			;;
	esac

	if [ -n "$ENABLE_STATS" -a "$ENABLE_STATS" != "true" ]; then
		parts="$(echo $parts | sed 's/monitor//' | sed 's/db-stats//' | sed 's/stats//')"
	else
		TARGET_DIR="/opt/isard/monitor/grafana/data"
		REQUIRED_UID=472
		REQUIRED_GID=472

		# Check if directory exists
		if [ -d "$TARGET_DIR" ]; then
			# Directory exists, check ownership
			CURRENT_UID=$(stat -c "%u" "$TARGET_DIR")
			CURRENT_GID=$(stat -c "%g" "$TARGET_DIR")

			if [ "$CURRENT_UID" -eq "$REQUIRED_UID" ] && [ "$CURRENT_GID" -eq "$REQUIRED_GID" ]; then
				echo "✔ Grafana data directory exists with correct ownership. Skipping setup."
			else
				echo "⚠ Warning: Grafana data directory exists but has incorrect ownership."
				echo "   Current:  UID=$CURRENT_UID, GID=$CURRENT_GID"
				echo "   Expected: UID=$REQUIRED_UID, GID=$REQUIRED_GID"
			fi
		else
			echo "📂 Creating Grafana data directory..."
			if mkdir -p "$TARGET_DIR" 2>/dev/null; then
				echo "✔ Directory created successfully."
			else
				echo "❌ Error: Failed to create directory. Check permissions."
			fi
		fi

		# Ensure correct ownership
		if chown -R "$REQUIRED_UID:$REQUIRED_GID" "$TARGET_DIR" 2>/dev/null; then
			echo "✔ Ownership set correctly for Grafana data."
		else
			echo "⚠ Warning: Insufficient permissions to change ownership."
			echo "   Please run the following manually:"
			echo "   sudo chown -R $REQUIRED_UID:$REQUIRED_GID $TARGET_DIR"
		fi
	fi


	if [ "$BACKUP_DB_ENABLED" = "false" ] && [ "$BACKUP_DISKS_ENABLED" = "false" ]
	then
		if [ "$FLAVOUR" = "backupninja" ]
		then
			echo "ERROR: flavour backupninja needs at least BACKUP_DB_ENABLED or BACKUP_DISKS_ENABLED in cfg"
			exit 1
		fi
		parts="$(echo $parts | sed 's/backupninja//')"
	fi

	if [ "$NEXTCLOUD_INSTANCE" != "true" ] && [ "$FLAVOUR" != "nextcloud" ]
	then
		parts="$(echo $parts | sed 's/postgres//' | sed 's/nc//' )"
	fi

	if [ -z "$INFRASTRUCTURE_MANAGEMENT" ] || [ "$INFRASTRUCTURE_MANAGEMENT" != "true" ]
	then
		parts="$(echo $parts | sed 's/infrastructure//')"

		# If the flavour is check, it doesn't require INFRASTRUCTURE_MANAGEMENT to be set
		if [ "$FLAVOUR" != "check" ]
		then
			parts="$(echo $parts | sed 's/check//')"
		fi
	fi

	# If BASTION_ENABLED is not true, remove the bastion part
	if [ -z "$BASTION_ENABLED" ] || [ "$BASTION_ENABLED" != "true" ]
	then
		echo "BASTION_ENABLED is not true, removing bastion part"
		parts="$(echo $parts | sed 's/bastion//')"
	fi

	# Build the docker-compose.yml
	flavour "$config_name" $parts

	if [ "$BACKUP_NFS_ENABLED" = "true" ]
	then
		if [ -z "$BACKUP_NFS_SERVER" ] || [ -z "$BACKUP_NFS_FOLDER" ]
		then
			echo "ERROR: backupninja with nfs enabled needs setting BACKUP_NFS_SERVER and BACKUP_NFS_FOLDER in cfg"
			exit 1
		fi
		if [ ! -z "$BACKUP_DIR" ]
		then
			echo "ERROR: backupninja with nfs enabled needs BACKUP_DIR to be commented/removed as conflicts"
			exit 1
		fi
		sed -i '/\/backup:\/backup/d' docker-compose*.yml
	fi
}

generate_code(){
	create_env "$1"

	case "$USAGE" in 
	build | test | devel)
		DOCKER_IMAGE="${DOCKER_IMAGE_PREFIX}codegen:${DOCKER_IMAGE_TAG}"
		docker pull $DOCKER_IMAGE
		docker build -t "$DOCKER_IMAGE" -f ./docker/codegen/Dockerfile .
		docker run --rm -u $(id -u) -v "$(pwd):/build" "$DOCKER_IMAGE"
		echo "Generated the code successfully"
		;;
	*)
		;;
	esac
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

	if [ "$CODEGEN" != "false" ]; then
		(generate_code "$config_file")
	fi
done

## BUILD_ROOT_PATH sed section
# Fix the context parameter in the docker-compose file
# See also BUILD_ROOT_PATH env section above
sed -i "s|$(pwd)|.|g" docker-compose*.yml

echo "You have the docker-compose files. Have fun!"
echo "You can download the prebuild images and bring it up:"
echo "   $DOCKER_COMPOSE pull && $DOCKER_COMPOSE up -d"
echo "Or build it yourself:"
echo "   $DOCKER_COMPOSE build && $DOCKER_COMPOSE up -d"
