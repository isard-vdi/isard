#!/bin/bash
if [ "$1" == "-h" ] || [ "$1" == "--help" ]; then
    echo "Pass parameters:"
    echo "  without parameters will build everything: web+hyper with video as a docker-compose .yml"
    echo "  <web> (only web, no hypevisor nor video)"
    echo "  <hypervisor> (only hypervisor with video)"
    echo "  <hypervisor-standalone> (only hypervisor without video)"
    echo "  <video-standalone> (only video without hypervisor)"
    exit 1
fi

read_var() {
    VAR=$(grep $1 $2 | xargs)
    IFS="=" read -ra VAR <<< "$VAR"
    echo ${VAR[1]}
}

set -e
git submodule init
git submodule update --recursive --remote

cp isardvdi.cfg .env
echo "BUILD_ROOT_PATH=$(pwd)" >> .env
cp isardvdi.cfg ymls/.env

HYPERVISOR_HOST_TRUNK_INTERFACE=$(read_var HYPERVISOR_HOST_TRUNK_INTERFACE .env)
echo $HYPERVISOR_HOST_TRUNK_INTERFACE
if [ -z "$HYPERVISOR_HOST_TRUNK_INTERFACE" ]; then
    HYPER_YAMLS="-f ymls/isard-hypervisor.yml"
else
    HYPER_YAMLS="-f ymls/isard-hypervisor.yml -f ymls/isard-hypervisor-vlans.yml"
fi

docker-compose \
    -f ymls/isard-stats.yml \
    config > docker-compose.stats.yml
docker-compose \
    -f docker-compose.stats.yml \
    -f ymls/devel/isard-stats.yml.devel \
    config > docker-compose.stats.devel.yml

if [ -z $1 ]; then
    echo "Building docker-compose.yml..."
    docker-compose  -f ymls/isard-db.yml \
            -f ymls/isard-engine.yml \
            -f ymls/isard-static.yml \
            -f ymls/isard-portal.yml \
            $HYPER_YAMLS \
            -f ymls/isard-websockify.yml \
            -f ymls/isard-squid.yml \
            -f ymls/isard-webapp.yml \
            -f ymls/isard-grafana.yml \
            -f ymls/isard-api.yml \
            -f ymls/isard-backend.yml \
            config > docker-compose.no-stats.yml
        docker-compose \
                -f docker-compose.no-stats.yml \
                -f ymls/devel/isard-db.yml.devel \
                -f ymls/devel/isard-portal.yml.devel \
                -f ymls/devel/isard-engine.yml.devel \
                -f ymls/devel/isard-webapp.yml.devel \
                -f ymls/devel/isard-api.yml.devel \
                config > docker-compose.no-stats.devel.yml
    docker-compose \
            -f docker-compose.no-stats.yml \
            -f docker-compose.stats.yml \
            config > docker-compose.yml
    docker-compose \
            -f docker-compose.no-stats.devel.yml \
            -f docker-compose.stats.devel.yml \
            config > docker-compose.devel.yml
    echo "You can download the prebuild images and bring it up:"
    echo "   docker-compose pull && docker-compose up -d"
    echo "Or build it yourself:"
    echo "   docker-compose build && docker-compose up -d"
fi

if [[ $1 == "hypervisor" ]]; then
    echo "Building hypervisor.yml..."
    docker-compose  -f ymls/isard-video.yml \
            $HYPER_YAMLS \
            -f ymls/isard-websockify.yml \
            -f ymls/isard-squid.yml \
            config > docker-compose.hypervisor.no-stats.yml
    docker-compose \
            -f docker-compose.hypervisor.no-stats.yml \
            -f docker-compose.stats.yml \
            config > docker-compose.hypervisor.yml
    docker-compose \
            -f docker-compose.hypervisor.no-stats.yml \
            -f docker-compose.stats.devel.yml \
            config > docker-compose.hypervisor.devel.yml
fi

if [[ $1 == "hypervisor-standalone" ]]; then
    echo "Building docker-compose.hypervisor-standalone.yml..."
    docker-compose $HYPER_YAMLS \
            -f ymls/isard-hypervisor-standalone.yml \
            config > docker-compose.hypervisor-standalone.no-stats.yml
    docker-compose \
            -f docker-compose.hypervisor-standalone.no-stats.yml \
            -f docker-compose.stats.yml \
            config > docker-compose.hypervisor-standalone.yml
    docker-compose \
            -f docker-compose.hypervisor-standalone.no-stats.yml \
            -f docker-compose.stats.devel.yml \
            config > docker-compose.hypervisor-standalone.devel.yml
fi

if [[ $1 == "video-standalone" ]]; then
    echo "Building video-standalone.yml..."
    docker-compose  -f ymls/isard-video.yml \
            -f ymls/isard-websockify.yml \
            -f ymls/isard-squid.yml \
            config > docker-compose.video-standalone.no-stats.yml
    docker-compose \
            -f docker-compose.video-standalone.no-stats.yml \
            -f docker-compose.stats.yml \
            config > docker-compose.video-standalone.yml
    docker-compose \
            -f docker-compose.video-standalone.no-stats.yml \
            -f docker-compose.stats.devel.yml \
            config > docker-compose.video-standalone.devel.yml
fi

if [[ $1 == "web" ]]; then
    echo "Building web.yml..."
    docker-compose  -f ymls/isard-db.yml \
            -f ymls/isard-engine.yml \
            -f ymls/isard-static.yml \
            -f ymls/isard-portal.yml \
            -f ymls/isard-webapp.yml \
            -f ymls/isard-grafana.yml \
            -f ymls/isard-api.yml \
            -f ymls/isard-backend.yml \
            config > docker-compose.web.no-stats.yml
        docker-compose \
                -f docker-compose.web.no-stats.yml \
                -f ymls/devel/isard-db.yml.devel \
                -f ymls/devel/isardvdi-portal.yml.devel \
                -f ymls/devel/isard-engine.yml.devel \
                -f ymls/devel/isard-webapp.yml.devel \
                config > docker-compose.web.no-stats.devel.yml
    docker-compose \
            -f docker-compose.web.no-stats.yml \
            -f docker-compose.stats.yml \
            config > docker-compose.web.yml
    docker-compose \
            -f docker-compose.web.no-stats.devel.yml \
            -f docker-compose.stats.devel.yml \
            config > docker-compose.web.devel.yml
fi

# Fix the context parameter in the docker-compose file
sed -i "s|$(pwd)|.|g" docker-compose*.yml
echo "You have the docker-compose files. Have fun!"
