# Isard VDI with nginx ssl proxy server

It is highly recommended to have firewalld activated. Follow this guide to allow
access to Isard VDI app.

## Firewalld service
```
systemctl enable firewalld
systemctl start firewalld
```

## Without nginx as a frontend proxy
```
firewall-cmd --zone=public --add-port=5000/tcp --permanent
```

## With nginx as an SSL frontend proxy

```
dnf install nginx
cp server/isard.conf /etc/nginx/conf.d/
```
**Remember to modify paths and server_name accordingly in isard.conf**

### Generate and install self-signed certificate
```
openssl req -x509 -newkey rsa:4096 -keyout server.pem -out server.pem -days 365

sudo chown root:root server.*
sudo chmod 600 server.*
sudo mkdir /etc/pki/nginx
sudo mv server.crt /etc/pki/nginx
sudo mkdir /etc/pki/nginx/private
sudo mv server.key /etc/pki/nginx/private
```

## Start and enable nginx:
```
systemctl enable nginx
systemctl start nginx
```

And finally add https rule on firewalld:

```
firewall-cmd --zone=public --add-service=https --permanent
```
