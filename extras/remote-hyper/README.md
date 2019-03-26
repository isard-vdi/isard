# IsardVDI Generic Hypervisor

It brings up a remote hypervisor. Instructions can be found at documentation: 

https://isardvdi.readthedocs.io/en/latest/admin/hypervisors/

## Quick steps

1. Mount your storage in /opt/isard.
2. Check that exists /opt/isard/certs/default as they are used to connect to viewers securely.
3. Bring it up: docker-compose up -d
