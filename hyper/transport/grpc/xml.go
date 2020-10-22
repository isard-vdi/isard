package grpc

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/hyper/pkg/proto"

	"gitlab.com/isard/isardvdi/common/pkg/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"libvirt.org/libvirt-go"
)

// DesktopXMLGet returns the XML definition of a running desktop
func (h *HyperServer) DesktopXMLGet(ctx context.Context, req *proto.DesktopXMLGetRequest) (*proto.DesktopXMLGetResponse, error) {
	if err := grpc.Required(grpc.RequiredParams{
		"id": &req.Id,
	}); err != nil {
		return nil, err
	}

	desktop, err := h.Hyper.Get(req.Id)
	if err != nil {
		var e libvirt.Error
		if errors.As(err, &e) {
			switch e.Code {
			case libvirt.ERR_NO_DOMAIN:
				return nil, status.Error(codes.NotFound, "get desktop: desktop not found")
			}
		}

		return nil, status.Errorf(codes.Unknown, "get desktop: %v", err)
	}
	defer desktop.Free()

	xml, err := h.Hyper.XMLGet(desktop)
	if err != nil {
		return nil, status.Errorf(codes.Unknown, err.Error())
	}

	return &proto.DesktopXMLGetResponse{Xml: xml}, nil
}
