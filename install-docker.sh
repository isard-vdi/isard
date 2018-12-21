# Add docker
apk add docker
rc-update add docker boot

# Add docker-compose
apk add py-pip
pip install docker-compose

# cgroup needed for hypervisor
mount -t cgroup -o none,name=systemd cgroup /sys/fs/cgroup/systemd/
echo 'cgroup /sys/fs/cgroup/systemd/ cgroup   none,name=systemd' >> /etc/fstab
