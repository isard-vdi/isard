package grpc

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/proto/hyper"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
	"libvirt.org/libvirt-go"
)

// DesktopMigrate live migrates a running desktop to another hypervisor
func (h *HyperServer) DesktopMigrate(ctx context.Context, req *hyper.DesktopMigrateRequest) (*hyper.DesktopMigrateResponse, error) {
	if err := grpc.Required(grpc.RequiredParams{
		"id":    &req.Id,
		"hyper": &req.Hyper,
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

	if err := h.Hyper.Migrate(desktop, req.Hyper); err != nil {
		return nil, status.Error(codes.Unknown, err.Error())
	}

	return &hyper.DesktopMigrateResponse{}, nil
}
