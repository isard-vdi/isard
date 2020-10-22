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

// DesktopResume resumes a suspended desktop in the hypervisor
func (h *HyperServer) DesktopResume(ctx context.Context, req *proto.DesktopResumeRequest) (*proto.DesktopResumeResponse, error) {
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
				return nil, status.Error(codes.NotFound, "desktop not found")
			}
		}

		return nil, status.Errorf(codes.Unknown, "get desktop: %v", err)
	}
	defer desktop.Free()

	if err := h.Hyper.Resume(desktop); err != nil {
		return nil, status.Error(codes.Unknown, err.Error())
	}

	return &proto.DesktopResumeResponse{}, nil
}
