package grpc

import (
	"context"

	"github.com/isard-vdi/isard/hyper/pkg/proto"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (h *HyperServer) DesktopList(ctx context.Context, req *proto.DesktopListRequest) (*proto.DesktopListResponse, error) {
	d, err := h.hyper.List()
	if err != nil {
		return nil, status.Errorf(codes.Unknown, "list desktops: %v", err)
	}

	rsp := &proto.DesktopListResponse{}
	for _, desktop := range d {
		id, err := desktop.GetName()
		if err == nil {
			rsp.Ids = append(rsp.Ids, id)
		}
	}

	return rsp, nil
}
