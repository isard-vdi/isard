package grpc

import (
	"context"
	"errors"

	"github.com/isard-vdi/isard/common/pkg/grpc"
	"github.com/isard-vdi/isard/disk-operations/diskoperations"
	"github.com/isard-vdi/isard/disk-operations/pkg/proto"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (d *DiskOperationsServer) Derivate(ctx context.Context, req *proto.DerivateRequest) (*proto.DerivateResponse, error) {
	if err := grpc.Required(grpc.RequiredParams{
		"path":         req.Path,
		"backing file": req.BackingFile,
	}); err != nil {
		return nil, err
	}

	if req.ClusterSize == 0 {
		req.ClusterSize = 4096
	}

	if err := d.diskoperations.Derivate(req.Path, req.BackingFile, int(req.ClusterSize)); err != nil {
		if errors.Is(err, diskoperations.ErrBackingFileNotFound) {
			return nil, status.Errorf(codes.NotFound, "derivate disk: %v", err)
		}

		return nil, status.Errorf(codes.Unknown, "derivate disk: %v", err)
	}

	return &proto.DerivateResponse{}, nil
}
