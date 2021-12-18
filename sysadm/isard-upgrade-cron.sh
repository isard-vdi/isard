#!/bin/sh -e

# This script requires jq to work.
# Debian derivates installation:
# apt install jq

# Also requires git >= 2.22.0
# In debian get the latest from backports.
# apt install -t buster-backports git

## Example cron:
#SHELL=/bin/bash
#PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin
## 12 4 * * * root /opt/isard/src/isardvdi/sysadm/isard-upgrade-cron.sh >/tmp/isard-upgrade.log 2>&1

script_path=$(readlink -f "$0")
lock_path="${script_path%/*/*/*}"

lockdir=$lock_path/upgrade_lock
pidfile=$lock_path/upgrade_lock/pid

lock_upgrade(){
  echo "Trying to lock $lockdir"
  until mkdir "$lockdir" 2> /dev/null
  do
    echo "Lock Exists: $lockdir owned by $(cat $pidfile)"
          sleep 10
  done


  echo "$(hostname) ($$)" > $pidfile
  trap 'rm -rf "$lockdir"; exit $?' INT TERM EXIT
}

unlock_upgrade(){
  rm -rf "$lockdir"
  trap - INT TERM EXIT
}


lock_upgrade

KILL_SWITCH_URL="https://isardvdi.com/kill_switch"
GITLAB_PIPELINES_API="https://gitlab.com/api/v4/projects/21522757/pipelines"

CONFIG_NAME=""
DOCKERCOMPOSE_UP=1
EXCLUDE_HYPER=0

while [ $# -gt 0 ]
do
  key="$1"
  case $key in
    -c|--config)
      CONFIG_NAME="$2" # Defaults to use isardvdi.cfg. If set to VALUE will use isardvdi.VALUE.cfg
      shift
      shift
      ;;
    -h|--exclude-hyper) # This avoids bringing down started desktops
      EXCLUDE_HYPER=1
      shift
      ;;
    -n|--noup) # This avoid bringing up any container, it will only download newer images.
      DOCKERCOMPOSE_UP=0
      shift
      ;;
    *)
      echo "ERROR: Bad flag $key" >&2
      exit 1
      ;;
  esac
done

if [ ! -z $CONFIG_NAME ]; then
	CONFIG_NAME=".${CONFIG_NAME}"
fi
echo "- Using isardvdi$CONFIG_NAME.cfg"
if [ $DOCKERCOMPOSE_UP = 0 ]
then
	echo "- Will not bring up containers, just download newer images."
fi
if [ $EXCLUDE_HYPER = 1 ]
then
	echo "- Will not bring up isard-hypervisor."
fi

SRC=$(dirname $0)/..

if [ ! -d "$SRC/.git" ]
then
	echo "Error: $(realpath $SRC) is not a root git folder" >&2
  exit 1
fi

cd $SRC

if [ "$(wget -qO - "$KILL_SWITCH_URL" | head -1)" != "on" ]
then
	echo "Upgrade disabled by $KILL_SWITCH_URL" >&2
	exit 1
fi

# Check if isardvdi.cfg DOCKER_IMAGE_TAG is the same that git remote traked branch
DOCKER_IMAGE_TAG="$(sed -n '/^DOCKER_IMAGE_TAG=/h;g;$s/^[^=]\+=\(.*\)$/\1/p;' isardvdi$CONFIG_NAME.cfg)"
REMOTE_BRANCH="$(git config --get branch.$(git branch --show-current).merge | sed 's|refs/heads/||')"
if [ "$DOCKER_IMAGE_TAG" != "$REMOTE_BRANCH" ]
then
	echo "Error: DOCKER_IMAGE_TAG ($DOCKER_IMAGE_TAG) differs from remote tracked branch ($REMOTE_BRANCH)" >&2
	exit 1
fi

git fetch $REMOTE

# Check if there is a BREAKING CHANGES due to change of major version
CURRENT_MAJOR_VERSION="$(git name-rev --name-only HEAD | sed -n 's|^tags/v\([^\.]\+\)\.[^\.]\+\.[^\^]\+$|\1|p')"
if [ -z "$CURRENT_MAJOR_VERSION" ]
then
	echo "Error: Current major version not detected. Please, checkout a branch with a version tag." >&2
	exit 1
fi
CANDIDATE_MAJOR_VERSION="$(git name-rev --name-only @{u} | sed -n 's|^tags/v\([^\.]\+\)\.[^\.]\+\.[^\^]\+$|\1|p')"
if [ -z "$CANDIDATE_MAJOR_VERSION" ]
then
	echo "Error: Candidate major version not detected. Maybe a version is not released yet. Try again later." >&2
	exit 1
fi
if [ "$CURRENT_MAJOR_VERSION" != "$CANDIDATE_MAJOR_VERSION" ]
then
  echo "Error: Current major version is $CURRENT_MAJOR_VERSION and there is the new major version $CANDIDATE_MAJOR_VERSION. Please read BREAKING CHANGES at https://gitlab.com/isard/isardvdi/-/releases" >&2
	exit 1
fi

# Check if there are docker images for last commit of remote traked branch
sha="$(git rev-parse @{u})"
success_pipelines="$(wget -qO - "$GITLAB_PIPELINES_API?status=success&sha=$sha" | jq 'reduce .[] as $_ (0;.+1)')"
if [ "$success_pipelines" = 0 ]
then
	echo "No successfull pipelines (no docker images generated) for last commit of remote tracked branch. Please, wait." >&2
	exit 1
fi

if ! git diff --exit-code @{u} -- isardvdi.cfg.example
then
	# TODO: Script that sources isardvdi.cfg and generates new from isardvdi.cfg.example
	echo "
Has changes in isardvdi.cfg.example. Upgrade manually!
git stash -u
git merge --ff @{u}
git stash pop
(compare and fix new/removed envvars from isardvdi.cfg.example to isardvdi$CONFIG_NAME.cfg)
Run the cron script now or wait for the cron to be executed automatically
" >&2
	exit 1
fi
echo "isardvdi.cfg.example has no changes. Proceeding to execute automatic upgrade (it can take some minutes)"
if [ -n "$(git status --ignore-submodules --porcelain)" ]
then
  git stash -u
  stashed=true
fi
if ! git merge --ff @{u}
then
  git merge --abort
  echo "Error: merge conflicts" >&2
  error=true
fi
if ${stashed-false}
then
  git stash pop
fi
if ${error-false}
then
  exit 1
fi
./build.sh
if [ $EXCLUDE_HYPER = 1 ]
then
	services="$(docker-compose -f docker-compose$CONFIG_NAME.yml config --services | sed '/^isard-hypervisor$/d' | sed '/^isard-pipework$/d')"
else
	services="$(docker-compose -f docker-compose$CONFIG_NAME.yml config --services)"
fi
docker-compose -f docker-compose$CONFIG_NAME.yml --ansi never pull $services

if [ $DOCKERCOMPOSE_UP = 1 ]
then
  echo "Bringing up new images: ${services} (isard-hypervisor is kept running)."
  docker-compose -f docker-compose$CONFIG_NAME.yml --ansi never up -d $services
  docker image prune -f --filter "until=72h"
else
  echo "Not bringing up new images, they were only pulled."
fi

unlock_upgrade
