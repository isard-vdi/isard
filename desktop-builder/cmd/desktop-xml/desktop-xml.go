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
	xml, err := cli.GetXmlFromId(context.Background(), &proto.GetXmlFromIdRequest{
		Xml: "linkat",
		Id:  "juanito",
	})
	if err != nil {
		panic(err)
	}
	fmt.Print(xml.String())
}
