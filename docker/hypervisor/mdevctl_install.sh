#!/bin/bash
apk add --no-cache cargo uuidgen py3-docutils make git
cd /opt
# mdevctl v1.2.0
git clone https://github.com/mdevctl/mdevctl
cd mdevctl
git checkout ec4b9a04ce15ad7dccef2dc99b20a53987eb16bc
cargo build
make install

mkdir -p /etc/mdevctl.d/scripts.d/callouts
mkdir -p /etc/mdevctl.d/scripts.d/notifiers
apk del cargo py3-docutils make git