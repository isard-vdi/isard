package grpc

import (
	"context"

	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/model"
	"gitlab.com/isard/isardvdi/pkg/proto/diskoperations"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (d *DiskOperationsServer) DiskCreate(ctx context.Context, req *diskoperations.DiskCreateRequest) (*diskoperations.DiskCreateResponse, error) {
	if err := grpc.Required(grpc.RequiredParams{
		"type":      &req.Type,
		"size":      &req.Type,
		"user_id":   &req.UserId,
		"entity_id": &req.EntityId,
		"name":      &req.Name,
	}); err != nil {
		return nil, err
	}

	id, err := d.DiskOperations.Create(model.DiskType(req.Type), int(req.Size), int(req.UserId), int(req.EntityId), req.Name, req.Description)
	if err != nil {
		return nil, status.Errorf(codes.Unknown, "create disk: %v", err)
	}

	return &diskoperations.DiskCreateResponse{
		Id: int64(id),
	}, nil
}
