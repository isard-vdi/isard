package grpc

import (
	"context"

	"github.com/isard-vdi/isard/desktop-builder/pkg/proto"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (h *DesktopBuilderServer) GetViewer(ctx context.Context, req *proto.GetViewerRequest) (*proto.GetViewerResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not implemented yet")
}
