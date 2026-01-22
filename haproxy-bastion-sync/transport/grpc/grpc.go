package grpc

import (
	"context"
	"errors"
	"fmt"
	"sync"

	haproxybastionsync "gitlab.com/isard/isardvdi/haproxy-bastion-sync/haproxy-bastion-sync"
	"gitlab.com/isard/isardvdi/pkg/cfg"
	haproxyv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/haproxy/v1"
	"gitlab.com/isard/isardvdi/pkg/grpc"

	"github.com/rs/zerolog"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func NewHAProxyBastionSyncServer(log *zerolog.Logger, wg *sync.WaitGroup, cfg cfg.GRPC, haproxybastionsync haproxybastionsync.Interface) *HAProxyBastionSyncServer {
	return &HAProxyBastionSyncServer{
		haproxybastionsync: haproxybastionsync,
		cfg:                cfg,

		log: log,
		wg:  wg,
	}
}

type HAProxyBastionSyncServer struct {
	haproxybastionsync haproxybastionsync.Interface
	cfg                cfg.GRPC

	log *zerolog.Logger
	wg  *sync.WaitGroup

	haproxyv1.UnimplementedHaproxyBastionServiceServer
}

// Serve starts the gRPC server
func (h *HAProxyBastionSyncServer) Serve(ctx context.Context) {
	grpc.Serve(ctx, h.log, h.wg, &haproxyv1.HaproxyBastionService_ServiceDesc, h, h.cfg)
}

func (h *HAProxyBastionSyncServer) Check(ctx context.Context) error {
	if err := h.haproxybastionsync.Check(ctx); err != nil {
		return fmt.Errorf("check haproxy-bastion-sync service: %w", err)
	}

	return nil
}

func (h *HAProxyBastionSyncServer) AddSubdomain(ctx context.Context, req *haproxyv1.AddSubdomainRequest) (*haproxyv1.AddSubdomainResponse, error) {
	if err := h.haproxybastionsync.AddSubdomain(ctx, req.GetDomain()); err != nil {
		if errors.Is(err, haproxybastionsync.ErrMissingSubdomain) {
			return nil, status.Error(codes.InvalidArgument, err.Error())
		}

		return nil, status.Error(codes.Internal, fmt.Errorf("add subdomain: %w", err).Error())
	}

	return &haproxyv1.AddSubdomainResponse{}, nil
}

func (h *HAProxyBastionSyncServer) DeleteSubdomain(ctx context.Context, req *haproxyv1.DeleteSubdomainRequest) (*haproxyv1.DeleteSubdomainResponse, error) {
	if err := h.haproxybastionsync.DeleteSubdomain(ctx, req.GetDomain()); err != nil {
		if errors.Is(err, haproxybastionsync.ErrMissingSubdomain) {
			return nil, status.Error(codes.InvalidArgument, err.Error())
		}

		return nil, status.Error(codes.Internal, fmt.Errorf("delete subdomain: %w", err).Error())
	}

	return &haproxyv1.DeleteSubdomainResponse{}, nil
}

func (h *HAProxyBastionSyncServer) AddIndividualDomain(ctx context.Context, req *haproxyv1.AddIndividualDomainRequest) (*haproxyv1.AddIndividualDomainResponse, error) {
	if err := h.haproxybastionsync.AddIndividualDomain(ctx, req.GetDomain()); err != nil {
		if errors.Is(err, haproxybastionsync.ErrMissingDomain) {
			return nil, status.Error(codes.InvalidArgument, err.Error())
		}

		return nil, status.Error(codes.Internal, fmt.Errorf("add individual domain: %w", err).Error())
	}

	return &haproxyv1.AddIndividualDomainResponse{}, nil
}

func (h *HAProxyBastionSyncServer) DeleteIndividualDomain(ctx context.Context, req *haproxyv1.DeleteIndividualDomainRequest) (*haproxyv1.DeleteIndividualDomainResponse, error) {
	if err := h.haproxybastionsync.DeleteIndividualDomain(ctx, req.GetDomain()); err != nil {
		if errors.Is(err, haproxybastionsync.ErrMissingDomain) {
			return nil, status.Error(codes.InvalidArgument, err.Error())
		}

		return nil, status.Error(codes.Internal, fmt.Errorf("delete individual domain: %w", err).Error())
	}

	return &haproxyv1.DeleteIndividualDomainResponse{}, nil
}

func (h *HAProxyBastionSyncServer) SyncMaps(ctx context.Context, req *haproxyv1.SyncMapsRequest) (*haproxyv1.SyncMapsResponse, error) {
	result, err := h.haproxybastionsync.SyncMaps(ctx, haproxybastionsync.SyncMaps{
		Subdomains:        req.GetSubdomains(),
		IndividualDomains: req.GetIndividualDomains(),
	})
	if err != nil {
		return nil, status.Error(codes.Internal, fmt.Errorf("sync maps: %w", err).Error())
	}

	return &haproxyv1.SyncMapsResponse{
		SubdomainsAdded:   int32(result.SubdomainsAdded),
		SubdomainsRemoved: int32(result.SubdomainsRemoved),
		IndividualAdded:   int32(result.IndividualDomainsAdded),
		IndividualRemoved: int32(result.IndividualDomainsRemoved),
	}, nil
}

func (h *HAProxyBastionSyncServer) GetCurrentMaps(ctx context.Context, req *haproxyv1.GetCurrentMapsRequest) (*haproxyv1.GetCurrentMapsResponse, error) {
	currMaps, err := h.haproxybastionsync.GetCurrentMaps(ctx)
	if err != nil {
		return nil, status.Error(codes.Internal, fmt.Errorf("get current maps: %w", err).Error())
	}

	return &haproxyv1.GetCurrentMapsResponse{
		Subdomains:        currMaps.Subdomains,
		IndividualDomains: currMaps.IndividualDomains,
	}, nil
}
