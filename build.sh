#!/bin/bash
if [ "$1" == "-h" ] || [ "$1" == "--help" ]; then
    echo "Pass parameters:"
    echo "  without parameters will build everything: web+hyper with video as a docker-compose .yml"
    echo "  <web> (only web, no hypevisor nor video)"
    echo "  <hypervisor> (only hypervisor with video)"
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
    HYPER_YAML=isard-hypervisor.yml
else
    HYPER_YAML=isard-hypervisor-vlans.yml
fi

if [ -z $1 ]; then
    echo "Building docker-compose.yml..."
    docker-compose  -f ymls/isard-db.yml \
            -f ymls/isard-engine.yml \
            -f ymls/isard-static.yml \
            -f ymls/isard-portal.yml \
            -f ymls/$HYPER_YAML \
            -f ymls/isard-websockify.yml \
            -f ymls/isard-squid.yml \
            -f ymls/isard-webapp.yml \
            -f ymls/isard-grafana.yml \
            -f ymls/isard-stats.yml \
            -f ymls/isard-api.yml \
            -f ymls/isard-backend.yml \
            config > docker-compose.yml
        docker-compose -f docker-compose.yml \
                -f ymls/devel/isard-db.yml.devel \
                -f ymls/devel/isard-portal.yml.devel \
                -f ymls/devel/isard-engine.yml.devel \
                -f ymls/devel/isard-webapp.yml.devel \
                -f ymls/devel/isard-stats.yml.devel \
                -f ymls/devel/isard-api.yml.devel \
                config > docker-compose.yml.devel
    echo "You have the docker-compose.yml and docker-compose.yml.devel compose files. Have fun!"
    echo "You can download the prebuild images and bring it up:"
    echo "   docker-compose pull && docker-compose up -d"
    echo "Or build it yourself:"
    echo "   docker-compose build && docker-compose up -d"
fi

if [[ $1 == "hypervisor" ]]; then
    echo "Building hypervisor.yml..."
    docker-compose  -f ymls/isard-video.yml \
            -f ymls/$HYPER_YAML \
            -f ymls/isard-websockify.yml \
            -f ymls/isard-squid.yml \
            -f ymls/isard-stats.yml \
            config > hypervisor.yml
        docker-compose -f hypervisor.yml \
                -f ymls/devel/isard-stats.yml.devel \
                config > devel-hypervisor.yml
    echo "You have the hypervisor.yml and devel-hypervisor.yml compose files. Have fun!"
fi

if [[ $1 == "web" ]]; then
    echo "Building web.yml..."
    docker-compose  -f ymls/isard-db.yml \
            -f ymls/isard-engine.yml \
            -f ymls/isard-static.yml \
            -f ymls/isard-portal.yml \
            -f ymls/isard-webapp.yml \
            -f ymls/isard-grafana.yml \
            -f ymls/isard-stats.yml \
            -f ymls/isard-api.yml \
            -f ymls/isard-backend.yml \
            config > web.yml
        docker-compose -f web.yml \
                -f ymls/devel/isard-db.yml.devel \
                -f ymls/devel/isardvdi-portal.yml.devel \
                -f ymls/devel/isard-engine.yml.devel \
                -f ymls/devel/isard-webapp.yml.devel \
                -f ymls/devel/isard-stats.yml.devel \
                config > devel-web.yml
    echo "You have the web.yml and devel-web.yml compose files. Have fun!"
fi

# Fix the context parameter in the docker-compose file
sed -i "s|$(pwd)|.|g" docker-compose.yml
sed -i "s|$(pwd)|.|g" docker-compose.yml.devel
