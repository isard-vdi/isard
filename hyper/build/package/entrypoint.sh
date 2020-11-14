#!/bin/sh

# Generate Spice viewer certificates
if [ ! -f /etc/pki/libvirt-spice/ca-cert.pem ]; then
    cd /etc/pki/libvirt-spice

    # Self signed cert generic data
    C=CA
    L=Barcelona
    O=localdomain
    CN_CA=$O
    CN_HOST=*.$O
    OU=$O

    KEY_LENGHT=4096

    echo '#### Creating $KEY_LENGHT-bit RSA key:'
    openssl genrsa -out ca-key.pem $KEY_LENGHT

    echo '#### Using the key to create a self-signed certificate to your CA:'
    openssl req -new -x509 -days 99999 -key ca-key.pem -out ca-cert.pem -sha256 \
        -subj "/C=$C/L=$L/O=$O/CN=$CN_CA"

    echo '#### Creating server certificate:'
    openssl genrsa -out server-key.pem $KEY_LENGHT

    echo '#### Creating a certificate signing request for the server:'
    openssl req -new -key server-key.pem -sha256 -out server-key.csr \
          -subj "/CN=$CN_HOST"

    echo '#### Creating  server certificate:'
    RND=$(( ( RANDOM % 1000 ) + 1 ))
    openssl x509 -req -days 99999 -in server-key.csr -CA ca-cert.pem -CAkey ca-key.pem \
          -set_serial $RND -sha256 -out server-cert.pem

    cd -
fi


chown root:kvm /dev/kvm

# Start the services
virtlogd&
libvirtd&

sleep 2
# TODO: Check a domain creation

/hyper
