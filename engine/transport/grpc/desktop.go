package grpc

import (
	"context"

	"github.com/isard-vdi/isard/engine/pkg/proto"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// DesktopStop stops a desktop
func (e *EngineServer) DesktopStop(ctx context.Context, req *proto.DesktopStopRequest) (*proto.DesktopStopResponse, error) {
	return nil, status.Error(codes.Unimplemented, "not implemented yet")
}
