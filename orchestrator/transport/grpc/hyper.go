package grpc

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/orchestrator/provider"
	"gitlab.com/isard/isardvdi/pkg/proto/orchestrator"

	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func (o *OrchestratorServer) GetHyper(ctx context.Context, req *orchestrator.GetHyperRequest) (*orchestrator.GetHyperResponse, error) {
	hyper, err := o.Provider.GetHyper(ctx, &provider.GetHyperOpts{
		Persistent: req.Persistent,
		GPU:        req.Gpu,
	})
	if err != nil {
		if errors.Is(err, provider.ErrNoAvailableHyper) {
			return nil, status.Error(codes.Unavailable, err.Error())
		}

		return nil, status.Errorf(codes.Unknown, "get hypervisor from provider: %v", err)
	}

	return &orchestrator.GetHyperResponse{
		Host: hyper,
	}, nil
}
