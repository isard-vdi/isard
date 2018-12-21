spice_key="/etc/pki/libvirt-spice/server-key.pem"
if [ -f "$spice_key" ]
then
    echo "$spice_key found, so not generating new spice certificates."
    exit 1
fi
C=CA
L=Barcelona
O=$( cut -d '.' -f 2- <<< "$(cat /etc/hostname)" )
CN_CA=$O
CN_HOST=*.$O
OU=$O

echo $O > /etc/pki/libvirt-spice/domain_name
echo 'Using the openssl command, create a 2048-bit RSA key:'
openssl genrsa -out cakey.pem 2048

echo 'Use the key to create a self-signed certificate to your local CA:'
openssl req -new -x509 -days 1095 -key cakey.pem -out cacert.pem -sha256 \
        -subj "/C=$C/L=$L/O=$O/CN=$CN_CA"

echo 'Check your CA certificate:'
openssl x509 -noout -text -in cacert.pem

echo 'Create Server & client keys'
openssl genrsa -out serverkey.pem 2048
openssl genrsa -out clientkey.pem 2048

echo 'Create a certificate signing request for the server. Remember to change the kvmhost.company.org address (used in the server certificate request) to the fully qualified domain name of your KVM host:'
openssl req -new -key serverkey.pem -out serverkey.csr \
          -subj "/C=$C/O=$O/CN=$CN_HOST"

echo 'Create a certificate signing request for the client:'
openssl req -new -key clientkey.pem -out clientkey.csr \
          -subj "/C=$C/O=$O/OU=$OU/CN=root"

echo 'Create client and server certificates:'
openssl x509 -req -days 3650 -in clientkey.csr -CA cacert.pem -CAkey cakey.pem \
          -set_serial 1 -out clientcert.pem
openssl x509 -req -days 3650 -in serverkey.csr -CA cacert.pem -CAkey cakey.pem \
          -set_serial 94345 -out servercert.pem

mkdir -p /etc/pki
mkdir -p /etc/pki/libvirt-spice
mv cacert.pem ca-cert.pem
mv servercert.pem server-cert.pem
mv serverkey.pem server-key.pem
cp ca-cert.pem /etc/pki/libvirt-spice/ca-cert.pem
cp server-cert.pem /etc/pki/libvirt-spice/server-cert.pem
cp server-key.pem /etc/pki/libvirt-spice/server-key.pem
chown qemu /etc/pki/libvirt-spice/*
chmod 440 /etc/pki/libvirt-spice/*
#systemctl restart libvirtd
#echo '4.- Modify /etc/libvirt/qemu.conf to activate certificate with spice'
#echo '    spice_tls = 1'
#echo '    spice_tls_x509_cert_dir = "/etc/pki/libvirt-spice"'

