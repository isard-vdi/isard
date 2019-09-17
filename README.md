# guac

Guacamole client in Go.

Initially forked from https://github.com/johnzhd/guacamole_client_go which is a direct rewrite of the Java Guacamole client.

## To run

To run a gaucd to connect to:

```shell script
docker run --name guacd -d -p 4822:4822 guacamole/guacd
```

## Notes

Example query parameters from the official guac client:

```
token=3E095C96B7E96186DAEF2C3D9C58215BCF120CB8D3C499F69089AB7C2D107BB3
GUAC_DATA_SOURCE=ATC_Provider
GUAC_ID=Windows_RDP-4e83d5408e0869f75231cf3b94c0504f
GUAC_TYPE=c
GUAC_WIDTH=1126
GUAC_HEIGHT=480
GUAC_DPI=96
GUAC_AUDIO=audio%2FL8
GUAC_AUDIO=audio%2FL16
GUAC_IMAGE=image%2Fjpeg
GUAC_IMAGE=image%2Fpng
GUAC_IMAGE=image%2Fwebp
```
