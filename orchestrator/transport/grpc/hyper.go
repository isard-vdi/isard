package grpc

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/orchestrator/pkg/proto"
	"gitlab.com/isard/isardvdi/orchestrator/provider"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (o *OrchestratorServer) GetHyper(ctx context.Context, req *proto.GetHyperRequest) (*proto.GetHyperResponse, error) {
	hyper, err := o.Provider.GetHyper(&provider.GetHyperOpts{
		Persistent: req.Persistent,
		GPU:        req.Gpu,
	})
	if err != nil {
		if errors.Is(err, provider.ErrNoAvailableHyper) {
			return nil, status.Error(codes.Unavailable, err.Error())
		}

		return nil, status.Errorf(codes.Unknown, "get hypervisor from provider: %v", err)
	}

	return &proto.GetHyperResponse{
		Host: hyper,
	}, nil
}
