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
	scheduler
	authentication
	vpn
	guac
	redis
	storage
	backupninja
	infrastructure
	check
	notifier
	sessions
	bastion
	apiv4
	socketio
	changefeed
	change-handler
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
	scheduler
	authentication
	vpn
	stats
	guac
	redis
	infrastructure
	notifier
	sessions
	bastion
	backupninja
	apiv4
	socketio
	changefeed
	change-handler
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

WEB_STORAGE_KEY="web+storage"
WEB_STORAGE_PARTS="
	$WEB_PARTS
	storage
"

WEB_STORAGE_VIDEO_KEY="web+storage+video"
WEB_STORAGE_VIDEO_PARTS="
	$WEB_PARTS
	storage
	$(echo "$VIDEO_STANDALONE_PARTS" | sed -e '/network/d' -e '/video/d' -e '/stats/d')
"

WEB_STORAGE_MONITOR_KEY="web+storage+monitor"
WEB_STORAGE_MONITOR_PARTS="
	$WEB_PARTS
	storage
	$(echo "$MONITOR_STANDALONE_PARTS" | sed -e '/network/d' -e '/monitor-proxy/d')
"

WEB_STORAGE_VIDEO_MONITOR_KEY="web+storage+video+monitor"
WEB_STORAGE_VIDEO_MONITOR_PARTS="
	$WEB_PARTS
	storage
	$(echo "$VIDEO_STANDALONE_PARTS" | sed -e '/network/d' -e '/video/d' -e '/stats/d')
	$(echo "$MONITOR_STANDALONE_PARTS" | sed -e '/network/d' -e '/monitor-proxy/d')
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
	ls isardvdi*.cfg 2>/dev/null
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
	# Add an empty line to the end of the .env file
	echo "" >> .env
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
		# Fix for Docker Compose v2.24+ which defaults create_host_path to false
		sed -i -e 's/create_host_path: false/create_host_path: true/g' \
		       -e 's/bind: {}/bind: {create_host_path: true}/g' \
		       -e 's/bind: {propagation:/bind: {create_host_path: true, propagation:/g' \
		       "docker-compose$delimiter$config_name.yml"
		# Handle multi-line bind with propagation but no create_host_path (Docker Compose v5+)
		sed -i '/bind:$/{N;N;/create_host_path/!s/\(bind:\n\)\([[:space:]]*\)\(propagation:[^\n]*\n\)/\1\2create_host_path: true\n\2\3/}' \
		       "docker-compose$delimiter$config_name.yml"
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
	done

	# Handle HYPERVISOR_HOST_TRUNK_INTERFACE mapping logic
	if [ -n "$HYPERVISOR_HOST_TRUNK_INTERFACE" ]; then
		if echo "$parts" | grep -q "\(^\|\s\)hypervisor\(\s\|$\)"; then
			# Hypervisor is present, add hypervisor-vlans
			parts="$parts hypervisor-vlans"
			echo "WARNING: Will take host interface $HYPERVISOR_HOST_TRUNK_INTERFACE and put it inside hypervisor container"
			echo "         So interface WILL DISSAPPEAR from host"
			echo "         With this configuration, when you restart container the interface could be missing,"
			echo "         so, better do '$DOCKER_COMPOSE -f docker-compose.hypervisor.yml down' and wait a minute"
			echo "         till the interface $HYPERVISOR_HOST_TRUNK_INTERFACE is visible in the host again!"
			echo ""
		elif echo "$parts" | grep -q "\(^\|\s\)vpn\(\s\|$\)"; then
			# No hypervisor but VPN is present, add vpn-vlans
			parts="$parts vpn-vlans"
			echo "WARNING: Will take host interface $HYPERVISOR_HOST_TRUNK_INTERFACE and put it inside vpn container"
			echo "         So interface WILL DISSAPPEAR from host"
			echo "         With this configuration, when you restart container the interface could be missing,"
			echo "         so, better do '$DOCKER_COMPOSE -f docker-compose.yml down' and wait a minute"
			echo "         till the interface $HYPERVISOR_HOST_TRUNK_INTERFACE is visible in the host again!"
			echo ""
		fi
	fi

	# Handle INFRASTRUCTURE_HOST_IP port opening logic
	if [ -n "$INFRASTRUCTURE_HOST_IP" ]; then
		echo "INFO: INFRASTRUCTURE_HOST_IP is set to $INFRASTRUCTURE_HOST_IP"
		echo "      Opening core infrastructure service ports on this IP"
		
		# Check which core infrastructure services are present and add their infrastructure-ports parts
		if echo "$parts" | grep -q "\(^\|\s\)db\(\s\|$\)"; then
			parts="$parts db.infrastructure-ports"
			echo "      - Database port 28015 exposed on $INFRASTRUCTURE_HOST_IP"
		fi
		if echo "$parts" | grep -q "\(^\|\s\)redis\(\s\|$\)"; then
			parts="$parts redis.infrastructure-ports"
			echo "      - Redis port 6379 exposed on $INFRASTRUCTURE_HOST_IP"
		fi
		# Check for monitor service (contains loki and prometheus)
		if echo "$parts" | grep -q "\(^\|\s\)monitor\(\s\|$\)"; then
			parts="$parts monitor.infrastructure-ports"
			echo "      - Loki port 3100 exposed on $INFRASTRUCTURE_HOST_IP"
			echo "      - Prometheus port 9090 exposed on $INFRASTRUCTURE_HOST_IP"
		fi
		echo ""
	fi

	# Add IPv6 sysctl for squid if IPv6 is available on the host
	if [ -f /proc/sys/net/ipv6/conf/all/disable_ipv6 ]; then
		if echo "$parts" | grep -q "\(^\|\s\)squid\(\s\|$\)"; then
			parts="$parts squid.ipv6"
		fi
	fi

	variants "$config_name" $parts
}

remove_part() {
    local part="$1"
    sed "s/\(^\|[[:blank:]]\)${part}\([[:blank:]]\|$\)/\1\2/g"
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
		$STORAGE_KEY)
			parts=$STORAGE_PARTS
			;;
		$WEB_KEY)
			parts=$WEB_PARTS
			;;
		$WEB_STORAGE_KEY)
			parts=$WEB_STORAGE_PARTS
			;;
		$WEB_STORAGE_VIDEO_KEY)
			parts=$WEB_STORAGE_VIDEO_PARTS
			;;
		$WEB_STORAGE_MONITOR_KEY)
			parts=$WEB_STORAGE_MONITOR_PARTS
			;;
		$WEB_STORAGE_VIDEO_MONITOR_KEY)
			parts=$WEB_STORAGE_VIDEO_MONITOR_PARTS
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
		$HAPROXY_BUILD_KEY)
			parts=$HAPROXY_BUILD_PARTS
			;;
		*)
			echo "Error: Flavour $FLAVOUR of $config_file not found"
			exit 1
			;;
	esac

	if [ -n "$ENABLE_STATS" -a "$ENABLE_STATS" != "true" ]; then
                parts=$(echo $parts | remove_part "monitor" | remove_part  "db-stats" | remove_part "stats")
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
		parts="$(echo $parts | remove_part "backupninja")"
	fi

	if [ -z "$INFRASTRUCTURE_MANAGEMENT" ] || [ "$INFRASTRUCTURE_MANAGEMENT" != "true" ]
	then
		parts="$(echo $parts | remove_part "infrastructure")"

		# If the flavour is check, it doesn't require INFRASTRUCTURE_MANAGEMENT to be set
		if [ "$FLAVOUR" != "check" ]
		then
			parts="$(echo $parts | remove_part "check")"
		fi
	fi

	if [ -z "$BASTION_ENABLED" ] || [ "$BASTION_ENABLED" != "true" ]
	then
		# If BASTION_ENABLED is not true, remove the bastion part
		echo "BASTION_ENABLED is not true, removing bastion part"
		parts="$(echo $parts | remove_part "bastion")"
	else
		# If BASTION_ENABLED is true, we need to ensure that the bastion-open-port part is included if BASTION_SSH_PORT is set
		# and is different from HTTPS_PORT (to avoid port conflict when both use 443)
		if [ -n "$BASTION_SSH_PORT" ] && [ "$BASTION_SSH_PORT" != "${HTTPS_PORT:-443}" ]
		then
			parts="$parts bastion-open-port"
		fi
	fi

	if [ -n "$REDIS_PASSWORD" ]
	then
		echo "REDIS_PASSWORD is true, adding redis password part"
		parts="$parts redis.passwd"
	fi

	# Add openapi container
	if [ "$ENABLE_OPENAPI" = "true" ]
	then
		echo "Adding openapi"
		parts="$parts openapi"
	fi

	# Expand monitoring
	if [ "$TEMPO" = "true" ]
	then
		echo "Adding Tempo"
		parts="$parts monitor-tempo"
	fi

	if [ "$PYROSCOPE_EBPF" = "true" ]
	then
		echo "Adding Pyroscope"
		parts="$parts monitor-pyroscope"
	fi

	# Build the docker-compose.yml
	flavour "$config_name" $parts

	# Expand monitoring
	if [ "$TEMPO" != "true" ]
	then
		echo "Clean Tempo vars"
		sed -i '/\bTEMPO.*/d' docker-compose*.yml
	fi

	if [ "$FARO_ENABLED" != "true" ]
	then
		echo "Clean Faro vars"
		sed -i '/\bFARO_.*/d' docker-compose*.yml
	fi

	if [ "$PYROSCOPE_EBPF" != "true" ]
	then
		echo "Clean Pyroscope"
		sed -i '/\bPYROSCOPE.*/d' docker-compose*.yml
	fi


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

	if [ -z "$USAGE" ]
	then
		USAGE="production"
	fi

	case "$USAGE" in
	build | devel)
		if ! docker buildx version >/dev/null 2>&1; then
			echo "ERROR: 'docker buildx' is required to build the codegen image. Install the docker-buildx package for your distribution." >&2
			exit 1
		fi
		DOCKER_IMAGE="${DOCKER_IMAGE_PREFIX}codegen:${DOCKER_IMAGE_TAG}"
		docker build --pull -t "$DOCKER_IMAGE" -f ./docker/codegen/Dockerfile .
		;;
	test | production)
		DOCKER_IMAGE="${DOCKER_IMAGE_PREFIX}codegen:${DOCKER_IMAGE_TAG}"
		docker pull "$DOCKER_IMAGE"
		;;
	*)
		echo "Error: unknown usage $USAGE for code generation"
		exit 1
		;;
	esac

        # Ensure the codegen cache directory exists
	CODEGEN_CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/isardvdi/codegen"
	mkdir -p "$CODEGEN_CACHE"

	# Redirect stdin from /dev/null so the codegen container does not
	# steal stdin from the outer `echo "$CONFIG_FILES" | while read`
	# loop — without it, only the first cfg gets processed when more
	# than one isardvdi*.cfg exists in cwd.
	docker run --rm -u "$(id -u)" \
		-e HOME=/tmp \
		-v "$(pwd):/build" \
		-v "$CODEGEN_CACHE:/cache" \
		"$DOCKER_IMAGE" </dev/null
	echo "Generated the code successfully"
}

if !(${SKIP_CHECK_DOCKER_COMPOSE_VERSION-false} || check_docker_compose_version)
then
	echo "ERROR: Please use docker-compose greather than or equal to $REQUIRED_DOCKER_COMPOSE_VERSION.
Use SKIP_CHECK_DOCKER_COMPOSE_VERSION=true environment variable to skip the check" >&2
	exit 1
fi

git submodule init
git submodule update --recursive --remote

CONFIG_FILES=$(get_config_files)
if [ -z "$CONFIG_FILES" ]; then
	echo "ERROR: no isardvdi*.cfg found in $(pwd)." >&2
	echo "Copy isardvdi.cfg.example to isardvdi.cfg and set USAGE=." >&2
	exit 1
fi

for config_file in $CONFIG_FILES
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

# isard-network MTU drift handling.  Two env-var knobs (same convention as
# SKIP_CHECK_DOCKER_COMPOSE_VERSION above):
#   SKIP_CHECK_ISARD_NETWORK_MTU=true   acknowledge the drift and continue the
#                                       build without changing anything
#   ISARD_RECREATE_ISARD_NETWORK=true   perform the destructive recreate
#                                       (docker compose down -> docker network
#                                       rm isard-network -> docker compose up
#                                       -d) so the new MTU actually applies.
#                                       This restarts the stack on THIS host
#                                       and kills running desktops on a host
#                                       running the hypervisor role.
_isard_net_drift(){
	# Echo "<live>|<requested>" when the live isard-network MTU differs from
	# what the freshly generated docker-compose.yml requests; echo nothing
	# and return 0 when there is no drift or it cannot be determined.
	# Single source of truth, used by the gate and the recreate.
	command -v docker >/dev/null 2>&1 || return 0
	docker network ls >/dev/null 2>&1 || return 0
	docker network inspect isard-network >/dev/null 2>&1 || return 0

	_req=$(awk -F: '/com\.docker\.network\.driver\.mtu/ {gsub(/[^0-9]/,"",$2); print $2; exit}' docker-compose.yml 2>/dev/null)
	[ -z "$_req" ] && return 0

	_live=$(docker network inspect isard-network --format '{{index .Options "com.docker.network.driver.mtu"}}' 2>/dev/null)
	{ [ -z "$_live" ] || [ "$_live" = "<no value>" ]; } && _live=1500

	[ "$_live" = "$_req" ] && return 0
	echo "$_live|$_req"
}

recreate_isard_network(){
	# Destructive opt-in: the only mechanism that actually applies a new MTU.
	# Reached only via ISARD_RECREATE_ISARD_NETWORK=true.  The env var IS the
	# consent: build.sh runs non-interactively under sysadm/upgrade.sh, so
	# there is deliberately no y/N prompt.
	_drift=$(_isard_net_drift) || true  # || true: detector may abort under set -e if docker-compose.yml is absent; empty => no drift
	if [ -z "$_drift" ]; then
		echo "isard-network MTU already correct, nothing to do."
		exit 0
	fi
	_live=${_drift%|*}
	_req=${_drift#*|}
	_compose="$DOCKER_COMPOSE -f docker-compose.yml"
	[ -f docker-compose-open-ports.yml ] && _compose="$_compose -f docker-compose-open-ports.yml"

	cat >&2 <<EOF

================================================================================
RECREATING docker network 'isard-network'  (MTU $_live -> $_req)

This runs '$_compose down' on THIS host: the IsardVDI control plane
stops, and on a host running the hypervisor role every running desktop on
this node is killed (can take minutes on a busy node).  Proceeding because
ISARD_RECREATE_ISARD_NETWORK=true was set.
================================================================================

EOF

	$_compose down || { echo "ERROR: '$_compose down' failed; stack may be partially down — run '$_compose up -d' to restore. isard-network NOT recreated; re-run with ISARD_RECREATE_ISARD_NETWORK=true once resolved." >&2; exit 1; }

	if docker network inspect isard-network >/dev/null 2>&1; then
		_rmlog=$(mktemp)
		if ! docker network rm isard-network >"$_rmlog" 2>&1; then
			if grep -q 'active endpoints' "$_rmlog"; then
				echo "ERROR: isard-network still has active endpoints after '$_compose down'." >&2
				echo "       Something outside this compose project is attached to it." >&2
				echo "       Detach/stop it, then re-run with ISARD_RECREATE_ISARD_NETWORK=true." >&2
			else
				echo "ERROR: 'docker network rm isard-network' failed:" >&2
				cat "$_rmlog" >&2
			fi
			rm -f "$_rmlog"
			exit 1
		fi
		rm -f "$_rmlog"
	fi

	$_compose up -d || { echo "ERROR: '$_compose up -d' failed after network removal; re-run build.sh to recover." >&2; exit 1; }

	_after=$(_isard_net_drift) || true
	if [ -z "$_after" ]; then
		echo "OK: isard-network recreated, MTU is now $_req."
		exit 0
	fi
	echo "FAIL: isard-network MTU still wrong after recreate ($_after); investigate." >&2
	exit 1
}

check_isard_network_mtu(){
	# Gate. No drift -> return 0 (build continues). On drift, in order:
	#   SKIP_CHECK_ISARD_NETWORK_MTU=true -> acknowledge, continue
	#   ISARD_RECREATE_ISARD_NETWORK=true -> perform the recreate (exits)
	#   otherwise                         -> FATAL, exit 1
	_drift=$(_isard_net_drift) || true  # || true: detector may abort under set -e if docker-compose.yml is absent; empty => no drift
	[ -z "$_drift" ] && return 0

	if [ "${SKIP_CHECK_ISARD_NETWORK_MTU:-false}" = "true" ]; then
		echo "isard-network MTU drift acknowledged via SKIP_CHECK_ISARD_NETWORK_MTU, continuing." >&2
		return 0
	fi

	if [ "${ISARD_RECREATE_ISARD_NETWORK:-false}" = "true" ]; then
		recreate_isard_network
		return 0
	fi

	_live=${_drift%|*}
	_req=${_drift#*|}
	cat >&2 <<EOF

================================================================================
FATAL: docker network 'isard-network' MTU drift
  live network    : $_live
  compose requests: $_req

Docker cannot change a network's MTU in place. 'docker compose up -d' keeps the
OLD network and silently fragments/drops geneve traffic. Build stopped.

To fix (maintenance window — restarts the stack on THIS host; kills running
desktops on a hypervisor node):

  sudo ISARD_RECREATE_ISARD_NETWORK=true bash build.sh     # guided down->rm->up
      (or by hand:)
  sudo $DOCKER_COMPOSE down && sudo docker network rm isard-network && sudo $DOCKER_COMPOSE up -d
      (add '-f docker-compose-open-ports.yml' to the down and up commands if you use open ports)

Already handled / fresh install / intentional / CI?
  export SKIP_CHECK_ISARD_NETWORK_MTU=true   and re-run build.sh
================================================================================

EOF
	exit 1
}
check_isard_network_mtu

ensure_etc_timezone(){
	# Ubuntu 26.04+ (and other modern systemd distros) ship NO /etc/timezone
	# file -- only the /etc/localtime symlink. The generated compose bind-mounts
	# `/etc/timezone:ro` into every container; when the host file is missing
	# Docker auto-creates it as an empty DIRECTORY, which then cannot mount onto
	# the container's /etc/timezone file and breaks every service at `up`.
	# Materialize it from /etc/localtime (or timedatectl) so the existing mounts
	# work on both old (file present) and new (file absent) hosts. Idempotent and
	# best-effort: it never aborts the build if it cannot write.
	[ -f /etc/timezone ] && return 0
	if [ "$(id -u)" = 0 ]; then SUDO=""; else SUDO="sudo"; fi
	_tz=""
	if [ -L /etc/localtime ]; then
		_tz=$(readlink -f /etc/localtime 2>/dev/null | sed -n 's@.*/zoneinfo/@@p')
	fi
	if [ -z "$_tz" ] && command -v timedatectl >/dev/null 2>&1; then
		_tz=$(timedatectl show -p Timezone --value 2>/dev/null)
	fi
	[ -z "$_tz" ] && _tz="Etc/UTC"
	# A prior failed Docker mount may have left /etc/timezone as an empty dir.
	[ -d /etc/timezone ] && $SUDO rmdir /etc/timezone 2>/dev/null || true
	if printf '%s\n' "$_tz" | $SUDO tee /etc/timezone >/dev/null 2>&1; then
		echo "Created /etc/timezone ($_tz) for container bind-mounts (this host shipped none)."
	else
		echo "WARNING: /etc/timezone is missing and could not be created ($_tz). Containers that bind-mount it will fail to start; create it manually:  echo $_tz | sudo tee /etc/timezone" >&2
	fi
	return 0
}
ensure_etc_timezone

disable_wgquick_apparmor(){
	# Ubuntu >=25.04 ships an ENFORCING AppArmor profile 'wg-quick' in the
	# `apparmor` package (/etc/apparmor.d/wg-quick; absent on <=24.04 LTS).
	# AppArmor transitions by executable, so the profile also confines the
	# wg-quick that runs INSIDE the isard-vpn container and denies exec of the
	# container's /bin/busybox -> `wg-quick up` fails (exit 126) -> the WireGuard
	# interface never comes up -> the hypervisor never registers Online ("No
	# hypervisors online to execute next virt action"). The vpn container is
	# privileged/unconfined, so this per-executable host profile is the ONLY
	# thing blocking it (security_opt: apparmor=unconfined would NOT help -- an
	# unconfined process still transitions into a named profile on exec).
	# Disable the host profile so the VPN + hypervisor work. Reversible,
	# non-fatal, best-effort -- same spirit as ensure_etc_timezone above.
	# Opt out with SKIP_FIX_WGQUICK_APPARMOR=true.
	[ "${SKIP_FIX_WGQUICK_APPARMOR:-false}" = "true" ] && return 0
	[ "$(cat /sys/module/apparmor/parameters/enabled 2>/dev/null)" = "Y" ] || return 0
	# Only relevant when this deployment actually runs the WireGuard vpn container.
	grep -q "isard-vpn" docker-compose.yml 2>/dev/null || return 0
	if [ "$(id -u)" = 0 ]; then SUDO=""; else SUDO="sudo"; fi
	# Enforcing? (complain/absent/unloaded -> nothing to do). Profiles list is root-only.
	$SUDO grep -qE "^wg-quick \(enforce\)$" /sys/kernel/security/apparmor/profiles 2>/dev/null || return 0
	echo "WARNING: host AppArmor profile 'wg-quick' is ENFORCING -- on Ubuntu >=25.04 it confines the" >&2
	echo "         isard-vpn container's wg-quick and denies exec of its busybox, so WireGuard never comes" >&2
	echo "         up and the hypervisor stays Offline. Disabling it on this host now (reversible)." >&2
	echo "         Opt out: SKIP_FIX_WGQUICK_APPARMOR=true . Re-enable:  sudo rm /etc/apparmor.d/disable/wg-quick && sudo apparmor_parser -r /etc/apparmor.d/wg-quick" >&2
	$SUDO mkdir -p /etc/apparmor.d/disable 2>/dev/null
	$SUDO ln -sf /etc/apparmor.d/wg-quick /etc/apparmor.d/disable/wg-quick 2>/dev/null
	if $SUDO apparmor_parser -R /etc/apparmor.d/wg-quick 2>/dev/null; then
		echo "         -> 'wg-quick' profile disabled + unloaded. If isard-vpn is already up, restart it:  $DOCKER_COMPOSE restart isard-vpn" >&2
	else
		echo "         -> could not unload automatically; run:  sudo apparmor_parser -R /etc/apparmor.d/wg-quick && sudo $DOCKER_COMPOSE restart isard-vpn" >&2
	fi
	return 0
}
disable_wgquick_apparmor

echo "You have the docker-compose files. Have fun!"
echo "You can download the prebuild images and bring it up:"
echo "   $DOCKER_COMPOSE pull && $DOCKER_COMPOSE up -d"
echo "Or build it yourself:"
echo "   $DOCKER_COMPOSE build && $DOCKER_COMPOSE up -d"
