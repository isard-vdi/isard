StatsD + Graphite + Grafana 2
---------------------------------------------

This image contains a sensible default configuration of StatsD, Graphite and Grafana. This image is used as a base for [dokku](https://github.com/progrium/dokku) graphite-statsd plugin.
There are two ways for using this image:


### Using the Docker Index ###

This image is published under [jlachowski repository on the Docker Index](https://hub.docker.com/u/jlachowski/) and all you
need as a prerequisite is having Docker installed on your machine. The container exposes the following ports:

- `80`: the Grafana web interface.
- `2003`: the Carbon port. 
- `8125`: the StatsD port.
- `8126`: the StatsD administrative port.

To start a container with this image you just need to run the following command:

```bash
docker run -d -p 80:80 -p 2003:2003 -p 8125:8125/udp -p 8126:8126 --name jlachowski-grafana-dashboard jlachowski/grafana-graphite-statsd
```

If you already have services running on your host that are using any of these ports, you may wish to map the container
ports to whatever you want by changing left side number in the `-p` parameters. Find more details about mapping ports
in the [Docker documentation](http://docs.docker.io/use/port_redirection/#port-redirection).


### Building the image yourself ###

The Dockerfile and supporting configuration files are available in our [Github repository](https://github.com/jlachowski/docker-grafana-graphite).
This comes specially handy if you want to change any of the StatsD, Graphite or Grafana settings, or simply if you want
to know how tha image was built.


### Using the Dashboards ###

Once your container is running all you need to do is:
- open your browser pointing to the host/port you just published
- login with the default username (admin) and password (admin)
- configure a new datasource to point at the Graphite metric data (URL - http://localhost:8000)
- then play with the dashboard at your wish...
