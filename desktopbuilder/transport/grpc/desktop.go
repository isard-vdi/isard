package grpc

import (
	"context"
	"errors"

	"github.com/go-pg/pg/v10"
	"gitlab.com/isard/isardvdi/common/pkg/grpc"
	"gitlab.com/isard/isardvdi/desktopbuilder/pkg/proto"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (d *DesktopBuilderServer) XMLGet(ctx context.Context, req *proto.XMLGetRequest) (*proto.XMLGetResponse, error) {
	if err := grpc.Required(grpc.RequiredParams{
		"id": &req.Id,
	}); err != nil {
		return nil, err
	}

	xml, err := d.DesktopBuilder.XMLGet(ctx, req.Id)
	if err != nil {
		if errors.Is(err, pg.ErrNoRows) {
			return nil, status.Error(codes.NotFound, "desktop not found")
		}

		return nil, status.Errorf(codes.Unknown, "build desktop XML: %v", err)

	}

	return &proto.XMLGetResponse{Xml: xml}, nil
}
