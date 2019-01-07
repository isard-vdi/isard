apk add sshpass
if [ -f /NEWHYPER ]
then
    rm /NEWHYPER
fi
echo "Trying to ssh into $HYPERVISOR..."
ssh-keyscan $HYPERVISOR > /NEWHYPER
if [ ! -s /NEWHYPER ]
then
    echo "Hypervisor $HYPERVISOR could not be reached. Aborting"
    exit 1
else
    cat /NEWHYPER >> /root/.ssh/known_hosts
    sshpass -p "$PASSWORD" ssh-copy-id root@"$HYPERVISOR"
    if [ $? -ne 0 ]
    then
       sed '/'"$HYPERVISOR"'/d' /root/.ssh/known_hosts > /root/.ssh/known_hosts
       echo "Can't access $HYPERVISOR as root user. Aborting"
       exit 1
    fi
fi

echo "Hypervisor ssh access granted."
virsh -c qemu+ssh://"$HYPERVISOR"/system quit
if [ $? -ne 0 ]
then
   echo "Can't access libvirtd daemon. Please ensure that libvirt daemon is running in $HYPERVISOR. Aborting"
   sed '/'"$HYPERVISOR"'/d' /root/.ssh/known_hosts > /root/.ssh/known_hosts
   exit 1
fi

echo "Access to $HYPERVISOR granted and found libvirtd service running."
echo "Now you can create this hypervisor in IsardVDI web interface."

