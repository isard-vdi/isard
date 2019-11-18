# guac

A Guacamole client in Go.

[![GoDoc](https://godoc.org/github.com/wwt/guac?status.svg)](http://godoc.org/github.com/wwt/guac)

## To run
## Development

First start guacd in a container, for example:

```sh
docker run --name guacd -d -p 4822:4822 guacamole/guacd
```

Next run provided main:

```sh
cd guac/cmd/guac
go run guac.go
```

Now you can connect with an example UI (coming soon)

## Acknowledgements

Initially forked from https://github.com/johnzhd/guacamole_client_go which is a direct rewrite of the Java Guacamole
client. This project no longer resembles that one but it helped it get off the ground!

Some of the comments are taken directly from the official Apache Guacamole Java client.
