package grpc

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/proto/desktopbuilder"

	"github.com/go-pg/pg/v10"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (d *DesktopBuilderServer) XMLGet(ctx context.Context, req *desktopbuilder.XMLGetRequest) (*desktopbuilder.XMLGetResponse, error) {
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

	return &desktopbuilder.XMLGetResponse{Xml: xml}, nil
}
