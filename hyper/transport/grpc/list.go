package grpc

import (
	"context"

	"gitlab.com/isard/isardvdi/hyper/pkg/proto"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// DesktopList returns a list of the desktops running in the hypervisor
func (h *HyperServer) DesktopList(ctx context.Context, req *proto.DesktopListRequest) (*proto.DesktopListResponse, error) {
	desktops, err := h.Hyper.List()
	if err != nil {
		return nil, status.Error(codes.Unknown, err.Error())
	}

	rsp := &proto.DesktopListResponse{}
	for _, desktop := range desktops {
		// TODO: Improve error handling
		name, err := desktop.GetName()
		if err == nil {
			rsp.Ids = append(rsp.Ids, name)
		}
	}

	return rsp, nil
}
