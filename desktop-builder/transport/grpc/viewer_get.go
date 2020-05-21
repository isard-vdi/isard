package grpc

import (
	"context"

	"github.com/isard-vdi/isard/desktop-builder/pkg/proto"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (h *DesktopBuilderServer) ViewerGet(ctx context.Context, req *proto.ViewerGetRequest) (*proto.ViewerGetResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not implemented yet")
}
