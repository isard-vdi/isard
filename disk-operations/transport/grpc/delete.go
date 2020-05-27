package grpc

import (
	"context"

	"github.com/isard-vdi/isard/common/pkg/grpc"
	"github.com/isard-vdi/isard/disk-operations/pkg/proto"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (d *DiskOperationsServer) Delete(ctx context.Context, req *proto.DeleteRequest) (*proto.DeleteResponse, error) {
	if err := grpc.Required(grpc.RequiredParams{
		"path": req.Path,
	}); err != nil {
		return nil, err
	}

	if err := d.diskoperations.Delete(req.Path); err != nil {
		return nil, status.Errorf(codes.Unknown, "delete disk: %v", err)
	}

	return &proto.DeleteResponse{}, nil
}
