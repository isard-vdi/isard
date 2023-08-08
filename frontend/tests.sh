#!/bin/sh

docker run -it --rm --ipc=host -p "9323:9323" -w "/frontend" -v "$PWD:/frontend" -e "DOCKER=true" --add-host=host.docker.internal:host-gateway mcr.microsoft.com/playwright:v1.36.0-jammy yarn playwright test