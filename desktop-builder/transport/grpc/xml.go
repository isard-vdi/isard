package grpc

import (
	"context"

	"github.com/isard-vdi/isard/common/pkg/grpc"
	"github.com/isard-vdi/isard/desktop-builder/pkg/proto"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (d *DesktopBuilderServer) XMLGet(ctx context.Context, req *proto.XMLGetRequest) (*proto.XMLGetResponse, error) {
	if err := grpc.Required(grpc.RequiredParams{
		"id": req.Id,
	}); err != nil {
		return nil, err
	}

	xml, err := d.builder.XMLGet(ctx, req.Id)
	if err != nil {
		return nil, status.Errorf(codes.Unknown, "get XML for desktop: %v", err)
	}

	return &proto.XMLGetResponse{Xml: xml}, nil
}
