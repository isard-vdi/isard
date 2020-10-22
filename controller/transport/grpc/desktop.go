package grpc

import (
	"context"

	"gitlab.com/isard/isardvdi/common/pkg/grpc"
	"gitlab.com/isard/isardvdi/controller/pkg/proto"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (c *ControllerServer) DesktopStart(ctx context.Context, req *proto.DesktopStartRequest) (*proto.DesktopStartResponse, error) {
	if err := grpc.Required(grpc.RequiredParams{
		"id": &req.Id,
	}); err != nil {
		return nil, err
	}

	viewer, err := c.Controller.DesktopStart(ctx, req.Id)
	if err != nil {
		return nil, status.Errorf(codes.Unknown, "start desktop: %v", err)
	}

	return &proto.DesktopStartResponse{Viewer: viewer}, nil
}
