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
func (h *HyperServer) DesktopState(ctx context.Context, req *proto.DesktopStateRequest) (*proto.DesktopStateResponse, error) {
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

	state, _, err := desktop.GetState()
	if err != nil {
		return nil, status.Errorf(codes.Unknown, "get desktop state: %v", err)
	}
	return &proto.DesktopStateResponse{
		State: StateMap(state),
	}, nil
}

func StateMap(state libvirt.DomainState) proto.DesktopStateResponse_DesktopState {
	switch state {
	case libvirt.DOMAIN_NOSTATE:
		return proto.DesktopStateResponse_DESKTOP_STATE_NOSTATE
	case libvirt.DOMAIN_RUNNING:
		return proto.DesktopStateResponse_DESKTOP_STATE_STARTED
	case libvirt.DOMAIN_BLOCKED:
		return proto.DesktopStateResponse_DESKTOP_STATE_BLOCKED
	case libvirt.DOMAIN_PAUSED:
		return proto.DesktopStateResponse_DESKTOP_STATE_PAUSED
	case libvirt.DOMAIN_SHUTDOWN:
		return proto.DesktopStateResponse_DESKTOP_STATE_STOPPING
	case libvirt.DOMAIN_SHUTOFF:
		return proto.DesktopStateResponse_DESKTOP_STATE_STOPPED
	case libvirt.DOMAIN_CRASHED:
		return proto.DesktopStateResponse_DESKTOP_STATE_CRASHED
	case libvirt.DOMAIN_PMSUSPENDED:
		return proto.DesktopStateResponse_DESKTOP_STATE_SUSPENDED
	}
	return proto.DesktopStateResponse_DESKTOP_STATE_UNKNOWN
}
