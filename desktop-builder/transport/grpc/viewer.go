package grpc

import (
	"context"
	"errors"

	"github.com/isard-vdi/isard/common/pkg/grpc"
	"github.com/isard-vdi/isard/desktop-builder/desktopbuilder"
	"github.com/isard-vdi/isard/desktop-builder/pkg/proto"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (d *DesktopBuilderServer) ViewerGet(ctx context.Context, req *proto.ViewerGetRequest) (*proto.ViewerGetResponse, error) {
	if err := grpc.Required(grpc.RequiredParams{
		"xml": req.Xml,
	}); err != nil {
		return nil, err
	}

	viewer, err := d.builder.ViewerGet(req.Xml)
	if err != nil {
		if errors.Is(err, desktopbuilder.ErrNoGraphics) {
			return nil, status.Errorf(codes.FailedPrecondition, "get viewer for the desktop: %v", err)
		}

		return nil, status.Errorf(codes.Unknown, "get viewer for the desktop: %v", err)
	}

	v := &proto.ViewerGetResponse{}
	for _, s := range viewer.Spice {
		v.Spice = append(v.Spice, &proto.ViewerGetResponse_Spice{
			Pwd:     s.Pwd,
			Port:    int32(s.Port),
			TlsPort: int32(s.TLSPort),
		})
	}

	for _, vnc := range viewer.VNC {
		v.Vnc = append(v.Vnc, &proto.ViewerGetResponse_Vnc{
			Pwd:           vnc.Pwd,
			Port:          int32(vnc.Port),
			WebsocketPort: int32(vnc.WebsocketPort),
		})
	}

	return v, nil
}
