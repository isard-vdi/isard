package grpc

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/hyper/hyper"
	"gitlab.com/isard/isardvdi/pkg/grpc"
	proto "gitlab.com/isard/isardvdi/pkg/proto/hyper"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"libvirt.org/libvirt-go"
)

// DesktopStart starts a desktop based in the XML definition
func (h *HyperServer) DesktopStart(ctx context.Context, req *proto.DesktopStartRequest) (*proto.DesktopStartResponse, error) {
	if err := grpc.Required(grpc.RequiredParams{
		"xml": &req.Xml,
	}); err != nil {
		return nil, err
	}

	desktop, err := h.Hyper.Start(req.Xml, &hyper.StartOptions{})
	if err != nil {
		var e libvirt.Error
		if errors.As(err, &e) {
			switch e.Code {
			case libvirt.ERR_XML_ERROR, libvirt.ERR_XML_DETAIL:
				return nil, status.Errorf(codes.InvalidArgument, "invalid XML: %s", e.Message)
			}
		}

		return nil, status.Error(codes.Unknown, err.Error())
	}
	defer desktop.Free()

	xml, err := h.Hyper.XMLGet(desktop)
	if err != nil {
		return nil, status.Errorf(codes.Unknown, "get desktop XML: %v", err)
	}

	return &proto.DesktopStartResponse{
		Xml: xml,
	}, nil
}
