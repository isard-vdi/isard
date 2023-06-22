#!/bin/bash

if [[ "$CHECK_MODE" == "server" ]]; then
    /check
else
    env | grep -E "^[[:upper:]].*" | sed "s|/root|/home/$SSH_USER|g" > /env

    usermod -s /bin/bash root
    adduser -D -s /bin/bash "$SSH_USER"
    echo "$SSH_USER:$SSH_PASSWORD" | chpasswd
    echo "$SSH_USER ALL=(ALL:ALL) NOPASSWD: ALL" >> /etc/sudoers

    chown -R "$SSH_USER" /config/xdg
    chown -R "$SSH_USER" /tmp/run/user/app

    mkdir /etc/dropbear
    dropbear -RFE
fi
