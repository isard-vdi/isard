#!/bin/sh

# Set engine keys
if [ ! -f /root/.ssh/id_rsa ] && [ ! -f /root/.ssh/id_ed25519 ]
then
    echo "Generating new rsa keys..."
    cat /dev/zero | ssh-keygen -q -N ""
fi
