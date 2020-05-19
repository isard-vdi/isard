package main

import (
	"context"

	"github.com/isard-vdi/isard/disk-operations/pkg/proto"
	"google.golang.org/grpc"
)

func main() {
	conn, err := grpc.Dial(":1312", grpc.WithInsecure())
	if err != nil {
		panic(err)
	}
	defer conn.Close()

	cli := proto.NewDiskOperationsClient(conn)

	_, err = cli.CreateDisk(context.Background(), &proto.CreateDiskRequest{
		Name: "prova",
		Size: 1,
	})
	if err != nil {
		panic(err)
	}
}
