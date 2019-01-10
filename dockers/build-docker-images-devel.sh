#!/bin/bash

# Check that the version number was provided
if [ -z "$1" ]; then
	echo "You need to specify a IsardVDI version! e.g. '1.1.0'"
	exit 1
fi

MAJOR=${1:0:1}
MINOR=${1:0:3}
PATCH=$1

# If a command fails, the whole script is going to stop
set -e

# Checkout to the specified version tag
#git checkout $1 > /dev/null

# Array containing all the images to build
images=(
	#alpine-pandas
	#nginx
	#hypervisor
	app-devel
)

# Build all the images and tag them correctly
for image in "${images[@]}"; do
	echo -e "\n\n\n"
	echo "Building $image"
	echo -e "\n\n\n"
	docker build -f=dockers/$image/Dockerfile -t isard/$image:latest  -t isard/$image:$MAJOR -t isard/$image:$MINOR -t isard/$image:$PATCH .
done

