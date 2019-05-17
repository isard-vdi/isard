if [[ -z $PASSWORD ]]
then
    echo "Usage:"
    echo "  docker exec -e PASSWORD=<NEW_ROOT_PASS> isard_isard-generic-hyper_1 bash -c '/reset-hyper.sh'"
    exit 1
fi

rm -v /etc/ssh/ssh_host_*
ssh-keygen -f /etc/ssh/ssh_host_rsa_key -N '' -t rsa
ssh-keygen -f /etc/ssh/ssh_host_dsa_key -N '' -t dsa
echo "root:$PASSWORD" |chpasswd
pkill -9 sshd
echo "You can add this new hypervisor in IsardVDI with PORT=2022 and your new root password"
