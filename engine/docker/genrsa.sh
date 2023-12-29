#!/bin/sh

# Set engine keys
if [ ! -f /root/.ssh/id_rsa ]
then
    echo "Generating new rsa keys..."
    cat /dev/zero | ssh-keygen -q -N ""
fi
