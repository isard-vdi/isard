package main

import (
	"context"

	"github.com/isard-vdi/isard/hyper/pkg/proto"

	"google.golang.org/grpc"
)

func main() {
	conn, err := grpc.Dial(":1312", grpc.WithInsecure())
	if err != nil {
		panic(err)
	}
	defer conn.Close()

	cli := proto.NewHyperClient(conn)

	_, err = cli.DesktopStart(context.Background(), &proto.DesktopStartRequest{
		Xml: "<xml>",
	})
	if err != nil {
		panic(err)
	}
}
