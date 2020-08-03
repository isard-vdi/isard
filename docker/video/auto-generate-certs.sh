cd /certs

# Self signed cert generic data
C=CA
L=Barcelona
O=localdomain
CN_CA=$O
CN_HOST=*.$O
OU=$O

echo '#### Creating 2048-bit RSA key:'
openssl genrsa -out ca-key.pem 2048

echo '#### Using the key to create a self-signed certificate to your CA:'
openssl req -new -x509 -days 9999 -key ca-key.pem -out ca-cert.pem -sha256 \
        -subj "/C=$C/L=$L/O=$O/CN=$CN_CA"

echo '#### Creating server certificate:'
openssl genrsa -out server-key.pem 2048

echo '#### Creating a certificate signing request for the server:'
openssl req -new -key server-key.pem -sha256 -out server-key.csr \
          -subj "/CN=$CN_HOST"

echo '#### Creating  server certificate:'
RND=$(( ( RANDOM % 1000 ) + 1 ))
openssl x509 -req -days 9999 -in server-key.csr -CA ca-cert.pem -CAkey ca-key.pem \
          -set_serial $RND -sha256 -out server-cert.pem

echo '#### Concatenate certs for haprox'
cat server-cert.pem server-key.pem > chain.pem
chmod 440 *
cd /
