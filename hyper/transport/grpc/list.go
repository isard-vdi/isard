package grpc

import (
	"context"

	"gitlab.com/isard/isardvdi/pkg/proto/hyper"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// DesktopList returns a list of the desktops running in the hypervisor
func (h *HyperServer) DesktopList(ctx context.Context, req *hyper.DesktopListRequest) (*hyper.DesktopListResponse, error) {
	desktops, err := h.Hyper.List()
	if err != nil {
		return nil, status.Error(codes.Unknown, err.Error())
	}

	rsp := &hyper.DesktopListResponse{}
	for _, desktop := range desktops {
		// TODO: Improve error handling
		name, err := desktop.GetName()
		if err == nil {
			rsp.Ids = append(rsp.Ids, name)
		}
	}

	return rsp, nil
}
