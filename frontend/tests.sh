#!/bin/sh

docker-compose run -e DISPLAY -e DBUS_SESSION_BUS_ADDRESS -v /var/run/dbus/system_bus_socket:/var/run/dbus/system_bus_socket -v $XDG_RUNTIME_DIR:$XDG_RUNTIME_DIR -u $(id -u):$(id -g) isard-cypress yarn test:e2e
