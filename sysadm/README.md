# IsardVDI System administration

By default IsardVDI will open some container ports to the public world:

```
      Name                    Command               State                       Ports                     
----------------------------------------------------------------------------------------------------------
isard-api          python3 start.py                 Up      0.0.0.0:7039->7039/tcp                        
isard-backend      /backend                         Up      0.0.0.0:1312->1312/tcp, 8080/tcp              
isard-db           rethinkdb --bind all             Up      28015/tcp, 29015/tcp, 0.0.0.0:8080->8080/tcp  
isard-engine       /usr/bin/supervisord -c /e ...   Up                                                    
isard-grafana      /sbin/tini -- /bin/bash /r ...   Up      0.0.0.0:2004->2004/tcp, 0.0.0.0:3000->3000/tcp
isard-hypervisor   sh run.sh                        Up      0.0.0.0:2022->22/tcp                          
isard-portal       /docker-entrypoint.sh hapr ...   Up      0.0.0.0:443->443/tcp, 0.0.0.0:80->80/tcp      
isard-redis        docker-entrypoint.sh redis ...   Up      6379/tcp                                      
isard-squid        /bin/sh /run.sh                  Up                                                    
isard-static       /docker-entrypoint.sh ngin ...   Up      80/tcp                                        
isard-stats        python3 run.py                   Up                                                    
isard-webapp       /usr/bin/supervisord -c /e ...   Up      5000/tcp                                      
isard-websockify   /websockify                      Up       
```

This will lead to a compromised system in terms of security as the only visible ports outside world should be 80 and 443.

To apply  a base security to your installation here you have some example scripts for Debian 10:

- debian_docker.sh: This is not a security script, it is only the first thing you should do: install docker & docker-compose
- debian_firewall.sh: This will do many things:
  - Install fail2ban
  - Install firewalld
  - Modify Debian 10 firewalld default nf_tables to old iptables behaviour. This is required in newer OS (centos 8 also) till we got a working configuration for nfs_tables ;-)
  - Remove all existing firewalld configurations and apply the required for an IsardVDI server:
    - Add masquerade to avoid exposing all docker ports to outside world
    - Allow for ssh (default port 22) access to the server. WARNING: You should modify the script if you are using another port!!!!
    - Allow ports 80 and 443 for normal IsardVDI operation (this are the only two ports required for IsardVDI)
    - Restart firewalld, fail2ban and docker services to apply configuration

