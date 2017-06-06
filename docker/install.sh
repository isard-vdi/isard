sudo dnf remove docker \
                  docker-common \
                  container-selinux \
                  docker-selinux \
                  docker-engine
sudo dnf -y install dnf-plugins-core
sudo dnf config-manager \
    --add-repo \
    https://download.docker.com/linux/fedora/docker-ce.repo
sudo dnf makecache fast
sudo dnf install docker-ce docker-compose -y
sudo systemctl enable docker
sudo systemctl start docker
