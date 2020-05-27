package main

import (
	"context"
	"fmt"

	"github.com/isard-vdi/isard/desktop-builder/pkg/proto"
	"google.golang.org/grpc"
)

func main() {
	conn, err := grpc.Dial(":1312", grpc.WithInsecure())
	if err != nil {
		panic(err)
	}
	defer conn.Close()

	cli := proto.NewDesktopBuilderClient(conn)
	rsp, err := cli.XMLGet(context.Background(), &proto.XMLGetRequest{Id: "win10"})
	if err != nil {
		panic(err)
	}

	viewerRsp, err := cli.ViewerGet(context.Background(), &proto.ViewerGetRequest{Xml: rsp.Xml})
	if err != nil {
		panic(err)
	}

	fmt.Println(viewerRsp)

	if err != nil {
		panic(err)
	}
}
