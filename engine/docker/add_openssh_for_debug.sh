apk add openssh-server openssh-sftp-server
apk add vim bash
echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC4LDFN0XnQgmuzaRLzYUbpqCMA7DgReOKzQ5GVgnsn0v7RBJiuRX7CZWjzW5JGJGx5J2n0SH56wyI+HpP1oznsC8ZsYMjQ2POSYPeMh9feIqltBS3xgML80cnwQoHyY2nR1UgPE4PeqONxE8xPCWL4nm5Bo4AV5sgbbPywpGNtHVSyZqIv6lTW0zFvj+KgR8FO90WaKAYo4S39w5HzIY7rc2bNIAKKOKgZpROwehX8KqoD0annD5NhTwHwgsrN7IiU6ZfVlIOThejZK02rR7pxqxYTdYgVKRLwClsEj+dRvfTIhJmM0VS46Q6FclDNjk459rEwvhnS5XvexLTtJBKL beto@tux" >> /root/.ssh/authorized_keys
echo "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQDDdMWJ9oE+qbxGT0MmEoaW2QFaJ2fQ8wX8TiCt5qbq6Q7G6CgfAcUGVCkmuwPfDmvf6VIplS4zv14NWSnLveaUfaICNJeXZfeDIZ5mcdWuV30ddaHImnrZChaq+lj09aiYh5lfT1/WEl9+k7Y0bU6wSpNhBnNQdxgDe7nSOFN0M4jM8bvfom9jvA5Oz0Et92lOFpjct22sw/1AfG3MUH2hdf2/rtlIyr6vQ1DY9NGrGQQNcnYZw3KSsBjvTY+0kbPCdQhBiww6uIVcgQ/yRMEoFbiNkr0AfyaGV83blIzfz30uSVZ/fGqsWFNKTcmUzKuZMHyk+Wmc8v2wrTCCBd5jZUaXD0B9t5SLBxSbcyakC1D/Sm1JddDn/AqlLYQ1pRXnPFlRiDONLh7b1bbMVZkDMFl+RXnYLKcRyQ634tlsazkaaZy2/SlMnjyNiFkJkyn8jObtpKHE88ofiVOG/RM1e8X2Cixi5XjMSq2Qh2hjBG9mneGs3fPkPQsSkvcEbMk= beto@tux" >> /root/.ssh/authorized_keys
sed -i -e 's|[#]*PermitRootLogin prohibit-password|PermitRootLogin yes|g' /etc/ssh/sshd_config
sed -i -e 's|[#]*PasswordAuthentication yes|PasswordAuthentication yes|g' /etc/ssh/sshd_config
sed -i -e 's|[#]*ChallengeResponseAuthentication yes|ChallengeResponseAuthentication yes|g' /etc/ssh/sshd_config
sed -i -e 's|[#]*ChallengeResponseAuthentication yes|ChallengeResponseAuthentication yes|g' /etc/ssh/sshd_config
sed -i -e 's|AllowTcpForwarding no|AllowTcpForwarding yes|g' /etc/ssh/sshd_config
sed -i -e 's|GatewayPorts no|GatewayPorts yes|g' /etc/ssh/sshd_config
echo "root:probandoandoloando" |chpasswd
ssh-keygen -A
for i in $(env); do echo $i>>/root/loadenv; done
/usr/sbin/sshd -D -e -f /etc/ssh/sshd_config &
