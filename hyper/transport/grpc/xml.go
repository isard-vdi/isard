package grpc

import (
	"context"

	"github.com/isard-vdi/isard/common/pkg/grpc"
	"github.com/isard-vdi/isard/hyper/pkg/proto"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (h *HyperServer) DesktopXMLGet(ctx context.Context, req *proto.DesktopXMLGetRequest) (*proto.DesktopXMLGetResponse, error) {
	if err := grpc.Required(grpc.RequiredParams{
		"id": req.Id,
	}); err != nil {
		return nil, err
	}

	xml, err := h.hyper.XMLGet(req.Id)
	if err != nil {
		return nil, status.Errorf(codes.Unknown, "get XML: %v", err)
	}

	return &proto.DesktopXMLGetResponse{Xml: xml}, nil
}
