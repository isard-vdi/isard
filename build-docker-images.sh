#!/bin/bash

# Check that the version number was provided
if [ -z "$1" ]; then
	echo "You need to specify a IsardVDI version! e.g. '1.1.0'"
	exit 1
fi

if [ $1 = "-f" ]; then
   force=1
   if [ -z "$2" ]; then
	 echo "You need to specify a IsardVDI version with -f option! e.g. '1.1.0'"
	 exit 1
   fi
   version=$2
else
  force=0
  version=$1
fi

MAJOR=${version:0:1}
MINOR=${version:0:3}
PATCH=$version

# If a command fails, the whole script is going to stop
set -e

# Checkout to the specified version tag
if [ force = 1 ]; then
    git checkout $1 > /dev/null
fi

# Array containing all the images to build
images=(
	#alpine-pandas
	#grafana
	nginx
	hypervisor
	app
)

# Build all the images and tag them correctly
for image in "${images[@]}"; do
	echo -e "\n\n\n"
	echo "Building $image"
	echo -e "\n\n\n"
	cmd="docker build -f dockers/$image/Dockerfile -t isard/$image:latest  -t isard/$image:$MAJOR -t isard/$image:$MINOR -t isard/$image:$PATCH ."
	echo $cmd
	$cmd
done

