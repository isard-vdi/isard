# Grafana

This is an optional (but cool) extra that will bring up a carbon+graphite+grafana container plugged to your IsardVDI with predefined dashboards.

## Installation

```
./build.sh <image version>
docker-compose up -d
```

Connect to your IsardVDI server on port 3000 to access grafana dashboards.

NOTE: Check that you have grafana enabled in IsardVDI config menu.

## Remote Grafana

You can put your grafana in another server by building and running there the remote yml:
 
```
./build.sh <image version>
docker-compose -f remote-grafana.yml up -d
```

## More info

https://isardvdi.readthedocs.io/en/latest/
