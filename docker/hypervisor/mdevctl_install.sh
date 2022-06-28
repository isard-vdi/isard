#!/bin/bash
apk add --no-cache cargo uuidgen py3-docutils make git
cd /opt
git clone https://github.com/mdevctl/mdevctl
cd mdevctl
cargo build
make install

mkdir -p /etc/mdevctl.d/scripts.d/callouts
mkdir -p /etc/mdevctl.d/scripts.d/notifiers
apk del cargo py3-docutils make git