package grpc

import (
	"context"
	"errors"
	"fmt"
	"sync"

	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy-sync"
	"gitlab.com/isard/isardvdi/pkg/cfg"
	haproxysyncv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/haproxy_sync/v1"
	"gitlab.com/isard/isardvdi/pkg/grpc"

	"github.com/rs/zerolog"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func NewHAProxySyncServer(log *zerolog.Logger, wg *sync.WaitGroup, cfg cfg.GRPC, haproxysync haproxysync.Interface) *HAProxySyncServer {
	return &HAProxySyncServer{
		haproxysync: haproxysync,
		cfg:         cfg,

		log: log,
		wg:  wg,
	}
}

type HAProxySyncServer struct {
	haproxysync haproxysync.Interface
	cfg         cfg.GRPC

	log *zerolog.Logger
	wg  *sync.WaitGroup

	haproxysyncv1.UnimplementedHaproxySyncServiceServer
}

// Serve starts the gRPC server
func (h *HAProxySyncServer) Serve(ctx context.Context) {
	grpc.Serve(ctx, h.log, h.wg, &haproxysyncv1.HaproxySyncService_ServiceDesc, h, h.cfg)
}

func (h *HAProxySyncServer) Check(ctx context.Context) error {
	if err := h.haproxysync.Check(ctx); err != nil {
		return fmt.Errorf("check haproxy-sync service: %w", err)
	}

	return nil
}

func (h *HAProxySyncServer) BastionAddSubdomain(ctx context.Context, req *haproxysyncv1.BastionAddSubdomainRequest) (*haproxysyncv1.BastionAddSubdomainResponse, error) {
	if err := h.haproxysync.BastionAddSubdomain(ctx, req.GetDomain()); err != nil {
		if errors.Is(err, haproxysync.ErrMissingSubdomain) {
			return nil, status.Error(codes.InvalidArgument, err.Error())
		}

		return nil, status.Error(codes.Internal, fmt.Errorf("add subdomain: %w", err).Error())
	}

	return &haproxysyncv1.BastionAddSubdomainResponse{}, nil
}

func (h *HAProxySyncServer) BastionDeleteSubdomain(ctx context.Context, req *haproxysyncv1.BastionDeleteSubdomainRequest) (*haproxysyncv1.BastionDeleteSubdomainResponse, error) {
	if err := h.haproxysync.BastionDeleteSubdomain(ctx, req.GetDomain()); err != nil {
		if errors.Is(err, haproxysync.ErrMissingSubdomain) {
			return nil, status.Error(codes.InvalidArgument, err.Error())
		}

		return nil, status.Error(codes.Internal, fmt.Errorf("delete subdomain: %w", err).Error())
	}

	return &haproxysyncv1.BastionDeleteSubdomainResponse{}, nil
}

func (h *HAProxySyncServer) BastionAddIndividualDomain(ctx context.Context, req *haproxysyncv1.BastionAddIndividualDomainRequest) (*haproxysyncv1.BastionAddIndividualDomainResponse, error) {
	if err := h.haproxysync.BastionAddIndividualDomain(ctx, req.GetDomain()); err != nil {
		if errors.Is(err, haproxysync.ErrMissingDomain) {
			return nil, status.Error(codes.InvalidArgument, err.Error())
		}

		return nil, status.Error(codes.Internal, fmt.Errorf("add individual domain: %w", err).Error())
	}

	return &haproxysyncv1.BastionAddIndividualDomainResponse{}, nil
}

func (h *HAProxySyncServer) BastionDeleteIndividualDomain(ctx context.Context, req *haproxysyncv1.BastionDeleteIndividualDomainRequest) (*haproxysyncv1.BastionDeleteIndividualDomainResponse, error) {
	if err := h.haproxysync.BastionDeleteIndividualDomain(ctx, req.GetDomain()); err != nil {
		if errors.Is(err, haproxysync.ErrMissingDomain) {
			return nil, status.Error(codes.InvalidArgument, err.Error())
		}

		return nil, status.Error(codes.Internal, fmt.Errorf("delete individual domain: %w", err).Error())
	}

	return &haproxysyncv1.BastionDeleteIndividualDomainResponse{}, nil
}

func (h *HAProxySyncServer) BastionSyncMaps(ctx context.Context, req *haproxysyncv1.BastionSyncMapsRequest) (*haproxysyncv1.BastionSyncMapsResponse, error) {
	result, err := h.haproxysync.BastionSyncMaps(ctx, haproxysync.BastionSyncMaps{
		Subdomains:        req.GetSubdomains(),
		IndividualDomains: req.GetIndividualDomains(),
	})
	if err != nil {
		return nil, status.Error(codes.Internal, fmt.Errorf("sync maps: %w", err).Error())
	}

	return &haproxysyncv1.BastionSyncMapsResponse{
		SubdomainsAdded:   int32(result.SubdomainsAdded),
		SubdomainsRemoved: int32(result.SubdomainsRemoved),
		IndividualAdded:   int32(result.IndividualDomainsAdded),
		IndividualRemoved: int32(result.IndividualDomainsRemoved),
	}, nil
}

func (h *HAProxySyncServer) BastionGetCurrentMaps(ctx context.Context, req *haproxysyncv1.BastionGetCurrentMapsRequest) (*haproxysyncv1.BastionGetCurrentMapsResponse, error) {
	currMaps, err := h.haproxysync.BastionGetCurrentMaps(ctx)
	if err != nil {
		return nil, status.Error(codes.Internal, fmt.Errorf("get current maps: %w", err).Error())
	}

	return &haproxysyncv1.BastionGetCurrentMapsResponse{
		Subdomains:        currMaps.Subdomains,
		IndividualDomains: currMaps.IndividualDomains,
	}, nil
}
