#!/bin/bash
docker rm -vf $(docker ps -a -q)
docker network prune --force
docker volume prune --force
docker rmi -f $(docker images -a -q)
rm -rf /opt/isard

