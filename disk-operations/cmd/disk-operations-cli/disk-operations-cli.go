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

	_, err = cli.DeleteDisk(context.Background(), &proto.DeleteDiskRequest{
		Filename: "/opt/isard/tests/derivated.qcow2",
	})
	if err != nil {
		panic(err)
	}

	_, err = cli.DeleteDisk(context.Background(), &proto.DeleteDiskRequest{
		Filename: "/opt/isard/tests/prova.qcow2",
	})
	if err != nil {
		panic(err)
	}

	_, err = cli.CreateDisk(context.Background(), &proto.CreateDiskRequest{
		Filename: "/opt/isard/tests/prova.qcow2",
		Size:     1,
	})
	if err != nil {
		panic(err)
	}

	_, err = cli.DerivateDisk(context.Background(), &proto.DerivateDiskRequest{
		Backingfile: "/opt/isard/tests/prova.qcow2",
		Filename:    "/opt/isard/tests/derivated.qcow2",
	})
	if err != nil {
		panic(err)
	}
}
