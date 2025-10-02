package grpc

import (
	"context"
	"fmt"
	"sync"

	haproxyv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/haproxy/v1"
	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/haproxy-bastion-sync/haproxy"

	"github.com/rs/zerolog"
	gRPC "google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

// HaproxyBastionServer implements the gRPC server for HAProxy bastion management
type HaproxyBastionServer struct {
	syncer *haproxy.Syncer
	store  *haproxy.MapStore
	addr   string
	log    *zerolog.Logger
	wg     *sync.WaitGroup

	haproxyv1.UnimplementedHaproxyBastionServiceServer
}

// NewHaproxyBastionServer creates a new HAProxy bastion gRPC server
func NewHaproxyBastionServer(syncer *haproxy.Syncer, store *haproxy.MapStore, addr string, log *zerolog.Logger, wg *sync.WaitGroup) *HaproxyBastionServer {
	return &HaproxyBastionServer{
		syncer: syncer,
		store:  store,
		addr:   addr,
		log:    log,
		wg:     wg,
	}
}

// Serve starts the gRPC server
func (s *HaproxyBastionServer) Serve(ctx context.Context) {
	grpc.Serve(ctx, s.log, s.wg, func(srv *gRPC.Server) {
		haproxyv1.RegisterHaproxyBastionServiceServer(srv, s)
	}, s.addr)
}

// AddSubdomain adds a subdomain to the subdomains map
func (s *HaproxyBastionServer) AddSubdomain(ctx context.Context, req *haproxyv1.AddSubdomainRequest) (*haproxyv1.AddSubdomainResponse, error) {
	domain := req.GetDomain()
	if domain == "" {
		return nil, status.Error(codes.InvalidArgument, "domain cannot be empty")
	}

	if err := s.syncer.AddSubdomain(domain); err != nil {
		s.log.Error().Err(err).Str("domain", domain).Msg("failed to add subdomain")
		return nil, status.Error(codes.Internal, fmt.Sprintf("add subdomain: %v", err))
	}

	return &haproxyv1.AddSubdomainResponse{}, nil
}

// DeleteSubdomain removes a subdomain from the subdomains map
func (s *HaproxyBastionServer) DeleteSubdomain(ctx context.Context, req *haproxyv1.DeleteSubdomainRequest) (*haproxyv1.DeleteSubdomainResponse, error) {
	domain := req.GetDomain()
	if domain == "" {
		return nil, status.Error(codes.InvalidArgument, "domain cannot be empty")
	}

	if err := s.syncer.DeleteSubdomain(domain); err != nil {
		s.log.Error().Err(err).Str("domain", domain).Msg("failed to delete subdomain")
		return nil, status.Error(codes.Internal, fmt.Sprintf("delete subdomain: %v", err))
	}

	return &haproxyv1.DeleteSubdomainResponse{}, nil
}

// AddIndividualDomain adds an individual domain to the individual map
func (s *HaproxyBastionServer) AddIndividualDomain(ctx context.Context, req *haproxyv1.AddIndividualDomainRequest) (*haproxyv1.AddIndividualDomainResponse, error) {
	domain := req.GetDomain()
	if domain == "" {
		return nil, status.Error(codes.InvalidArgument, "domain cannot be empty")
	}

	if err := s.syncer.AddIndividualDomain(domain); err != nil {
		s.log.Error().Err(err).Str("domain", domain).Msg("failed to add individual domain")
		return nil, status.Error(codes.Internal, fmt.Sprintf("add individual domain: %v", err))
	}

	return &haproxyv1.AddIndividualDomainResponse{}, nil
}

// DeleteIndividualDomain removes an individual domain from the individual map
func (s *HaproxyBastionServer) DeleteIndividualDomain(ctx context.Context, req *haproxyv1.DeleteIndividualDomainRequest) (*haproxyv1.DeleteIndividualDomainResponse, error) {
	domain := req.GetDomain()
	if domain == "" {
		return nil, status.Error(codes.InvalidArgument, "domain cannot be empty")
	}

	if err := s.syncer.DeleteIndividualDomain(domain); err != nil {
		s.log.Error().Err(err).Str("domain", domain).Msg("failed to delete individual domain")
		return nil, status.Error(codes.Internal, fmt.Sprintf("delete individual domain: %v", err))
	}

	return &haproxyv1.DeleteIndividualDomainResponse{}, nil
}

// SyncMaps performs full synchronization of all maps
func (s *HaproxyBastionServer) SyncMaps(ctx context.Context, req *haproxyv1.SyncMapsRequest) (*haproxyv1.SyncMapsResponse, error) {
	subdomains := req.GetSubdomains()
	individualDomains := req.GetIndividualDomains()

	s.log.Info().
		Int("subdomains", len(subdomains)).
		Int("individual", len(individualDomains)).
		Msg("sync maps requested")

	result, err := s.syncer.SyncAll(subdomains, individualDomains)
	if err != nil {
		s.log.Error().Err(err).Msg("failed to sync maps")
		return nil, status.Error(codes.Internal, fmt.Sprintf("sync maps: %v", err))
	}

	return &haproxyv1.SyncMapsResponse{
		SubdomainsAdded:   result.SubdomainsAdded,
		SubdomainsRemoved: result.SubdomainsRemoved,
		IndividualAdded:   result.IndividualAdded,
		IndividualRemoved: result.IndividualRemoved,
	}, nil
}

// GetCurrentMaps returns the current state of all maps
func (s *HaproxyBastionServer) GetCurrentMaps(ctx context.Context, req *haproxyv1.GetCurrentMapsRequest) (*haproxyv1.GetCurrentMapsResponse, error) {
	subdomains := s.store.GetSubdomains()
	individual := s.store.GetIndividual()

	s.log.Debug().
		Int("subdomains", len(subdomains)).
		Int("individual", len(individual)).
		Msg("get current maps")

	return &haproxyv1.GetCurrentMapsResponse{
		Subdomains:        subdomains,
		IndividualDomains: individual,
	}, nil
}
