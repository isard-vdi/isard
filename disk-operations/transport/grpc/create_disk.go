package grpc

import (
	"context"
	"fmt"

	"github.com/isard-vdi/isard/disk-operations/pkg/proto"

	"github.com/zchee/go-qcow2"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (h *DiskOperationsServer) CreateDisk(ctx context.Context, req *proto.CreateDiskRequest) (*proto.CreateDiskResponse, error) {
	Disk(req.Name, req.Size)
	return &proto.CreateDiskResponse{Result: true}, nil
	return &proto.CreateDiskResponse{Result: false}, status.Error(codes.Unimplemented, "not implemented yet")
}

func Disk(name string, size int64) error {
	diskPath := name + ".qcow2"
	opts := &qcow2.Opts{
		Filename:      diskPath,
		Size:          size * 107374,
		Fmt:           qcow2.DriverQCow2,
		ClusterSize:   65536,
		Preallocation: qcow2.PREALLOC_MODE_OFF,
		Encryption:    false,
		LazyRefcounts: true,
	}

	_, err := qcow2.Create(opts)
	if err != nil {
		fmt.Print(err)
	}

	return nil
}
