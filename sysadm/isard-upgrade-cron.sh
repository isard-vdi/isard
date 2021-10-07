#!/bin/sh -e

## Example cron:
## 12 4 * * * root /opt/isard/src/isardvdi/sysadm/isard-upgrade-cron.sh >/tmp/isard-upgrade.log 2>&1

KILL_SWITCH_URL="https://isardvdi.com/kill_switch"
GITLAB_PIPELINES_API="https://gitlab.com/api/v4/projects/21522757/pipelines"

if [ -n "$1" ]
then
	CONFIG_NAME=".$1"
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
echo "isardvdi.cfg.example has no changes. Proceeding to execute automatic upgrade"
git stash -u
if ! git merge --ff @{u}
then
	git merge --abort
	git stash pop
	echo "Error: merge conflicts" >&2
	exit 1
fi
git stash pop
./build.sh
services="$(docker-compose -f docker-compose$CONFIG_NAME.yml config --services | sed '/^isard-hypervisor$/d' | sed '/^isard-pipework$/d')"
docker-compose -f docker-compose$CONIG_NAME.yml pull $services
docker-compose -f docker-compose$CONFIG_NAME.yml up -d $services
