package grpc

import (
	"context"
	"errors"

	"github.com/isard-vdi/isard/common/pkg/grpc"
	"github.com/isard-vdi/isard/hyper/hyper"
	"github.com/isard-vdi/isard/hyper/pkg/proto"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (h *HyperServer) DesktopStop(ctx context.Context, req *proto.DesktopStopRequest) (*proto.DesktopStopResponse, error) {
	if err := grpc.Required(grpc.RequiredParams{
		"id": req.Id,
	}); err != nil {
		return nil, err
	}

	if err := h.hyper.Stop(req.Id); err != nil {
		if errors.Is(err, hyper.ErrDesktopNotStarted) {
			return nil, status.Errorf(codes.FailedPrecondition, "stop desktop: %v", err)
		}

		return nil, status.Errorf(codes.Unknown, "stop desktop: %v", err)
	}

	return &proto.DesktopStopResponse{}, nil
}
