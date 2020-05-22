package grpc

import (
	"context"

	"github.com/isard-vdi/isard/desktop-builder/pkg/proto"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (db *DesktopBuilderServer) XMLGet(ctx context.Context, req *proto.XMLGetRequest) (*proto.XMLGetResponse, error) {
	xml, err := db.env.DesktopBuilder.XMLGet(ctx, req.Id, req.Template)
	if err != nil {
		return nil, status.Errorf(codes.Unknown, "get XML for desktop: %v", err)
	}

	return &proto.XMLGetResponse{Xml: xml}, nil
}
