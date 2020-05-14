package grpc

import (
	"context"

	"github.com/isard-vdi/isard/hyper/pkg/proto"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (h *HyperServer) DesktopStop(ctx context.Context, req *proto.DesktopStopRequest) (*proto.DesktopStopResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not implemented yet")
}
