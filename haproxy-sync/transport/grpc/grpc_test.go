package grpc_test

import (
	"context"
	"errors"
	"fmt"
	"os"
	"testing"

	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy-sync"
	"gitlab.com/isard/isardvdi/haproxy-sync/transport/grpc"
	"gitlab.com/isard/isardvdi/pkg/cfg"
	haproxysyncv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/haproxy_sync/v1"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestBastionAddSubdomain(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareService func(*haproxysync.MockHaproxysync)
		Req            *haproxysyncv1.BastionAddSubdomainRequest
		ExpectedRsp    *haproxysyncv1.BastionAddSubdomainResponse
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("BastionAddSubdomain", mock.AnythingOfType("context.backgroundCtx"), "example").
					Return(nil)
			},
			Req: &haproxysyncv1.BastionAddSubdomainRequest{
				Domain: "example",
			},
			ExpectedRsp: &haproxysyncv1.BastionAddSubdomainResponse{},
		},
		"should return an InvalidArgument status if subdomain is missing": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("BastionAddSubdomain", mock.AnythingOfType("context.backgroundCtx"), "").
					Return(haproxysync.ErrMissingSubdomain)
			},
			Req: &haproxysyncv1.BastionAddSubdomainRequest{
				Domain: "",
			},
			ExpectedErr: status.Error(codes.InvalidArgument, haproxysync.ErrMissingSubdomain.Error()).Error(),
		},
		"should return an Internal status if an unexpected error occurs": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("BastionAddSubdomain", mock.AnythingOfType("context.backgroundCtx"), "fail").
					Return(errors.New("unexpected error"))
			},
			Req: &haproxysyncv1.BastionAddSubdomainRequest{
				Domain: "fail",
			},
			ExpectedErr: status.Error(codes.Internal, fmt.Errorf("add subdomain: %w", errors.New("unexpected error")).Error()).Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			serviceMock := &haproxysync.MockHaproxysync{}
			tc.PrepareService(serviceMock)

			srv := grpc.NewHAProxySyncServer(&log, nil, cfg.GRPC{}, serviceMock)

			rsp, err := srv.BastionAddSubdomain(context.Background(), tc.Req)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedRsp, rsp)

			serviceMock.AssertExpectations(t)
		})
	}
}

func TestBastionDeleteSubdomain(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareService func(*haproxysync.MockHaproxysync)
		Req            *haproxysyncv1.BastionDeleteSubdomainRequest
		ExpectedRsp    *haproxysyncv1.BastionDeleteSubdomainResponse
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("BastionDeleteSubdomain", mock.AnythingOfType("context.backgroundCtx"), "example").
					Return(nil)
			},
			Req: &haproxysyncv1.BastionDeleteSubdomainRequest{
				Domain: "example",
			},
			ExpectedRsp: &haproxysyncv1.BastionDeleteSubdomainResponse{},
		},
		"should return an InvalidArgument status if subdomain is missing": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("BastionDeleteSubdomain", mock.AnythingOfType("context.backgroundCtx"), "").
					Return(haproxysync.ErrMissingSubdomain)
			},
			Req: &haproxysyncv1.BastionDeleteSubdomainRequest{
				Domain: "",
			},
			ExpectedErr: status.Error(codes.InvalidArgument, haproxysync.ErrMissingSubdomain.Error()).Error(),
		},
		"should return an Internal status if an unexpected error occurs": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("BastionDeleteSubdomain", mock.AnythingOfType("context.backgroundCtx"), "fail").
					Return(errors.New("unexpected error"))
			},
			Req: &haproxysyncv1.BastionDeleteSubdomainRequest{
				Domain: "fail",
			},
			ExpectedErr: status.Error(codes.Internal, fmt.Errorf("delete subdomain: %w", errors.New("unexpected error")).Error()).Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			serviceMock := &haproxysync.MockHaproxysync{}
			tc.PrepareService(serviceMock)

			srv := grpc.NewHAProxySyncServer(&log, nil, cfg.GRPC{}, serviceMock)

			rsp, err := srv.BastionDeleteSubdomain(context.Background(), tc.Req)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedRsp, rsp)

			serviceMock.AssertExpectations(t)
		})
	}
}

func TestBastionAddIndividualDomain(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareService func(*haproxysync.MockHaproxysync)
		Req            *haproxysyncv1.BastionAddIndividualDomainRequest
		ExpectedRsp    *haproxysyncv1.BastionAddIndividualDomainResponse
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("BastionAddIndividualDomain", mock.AnythingOfType("context.backgroundCtx"), "example.com").
					Return(nil)
			},
			Req: &haproxysyncv1.BastionAddIndividualDomainRequest{
				Domain: "example.com",
			},
			ExpectedRsp: &haproxysyncv1.BastionAddIndividualDomainResponse{},
		},
		"should return an InvalidArgument status if domain is missing": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("BastionAddIndividualDomain", mock.AnythingOfType("context.backgroundCtx"), "").
					Return(haproxysync.ErrMissingDomain)
			},
			Req: &haproxysyncv1.BastionAddIndividualDomainRequest{
				Domain: "",
			},
			ExpectedErr: status.Error(codes.InvalidArgument, haproxysync.ErrMissingDomain.Error()).Error(),
		},
		"should return an Internal status if an unexpected error occurs": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("BastionAddIndividualDomain", mock.AnythingOfType("context.backgroundCtx"), "fail.com").
					Return(errors.New("unexpected error"))
			},
			Req: &haproxysyncv1.BastionAddIndividualDomainRequest{
				Domain: "fail.com",
			},
			ExpectedErr: status.Error(codes.Internal, fmt.Errorf("add individual domain: %w", errors.New("unexpected error")).Error()).Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			serviceMock := &haproxysync.MockHaproxysync{}
			tc.PrepareService(serviceMock)

			srv := grpc.NewHAProxySyncServer(&log, nil, cfg.GRPC{}, serviceMock)

			rsp, err := srv.BastionAddIndividualDomain(context.Background(), tc.Req)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedRsp, rsp)

			serviceMock.AssertExpectations(t)
		})
	}
}

func TestBastionDeleteIndividualDomain(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareService func(*haproxysync.MockHaproxysync)
		Req            *haproxysyncv1.BastionDeleteIndividualDomainRequest
		ExpectedRsp    *haproxysyncv1.BastionDeleteIndividualDomainResponse
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("BastionDeleteIndividualDomain", mock.AnythingOfType("context.backgroundCtx"), "example.com").
					Return(nil)
			},
			Req: &haproxysyncv1.BastionDeleteIndividualDomainRequest{
				Domain: "example.com",
			},
			ExpectedRsp: &haproxysyncv1.BastionDeleteIndividualDomainResponse{},
		},
		"should return an InvalidArgument status if domain is missing": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("BastionDeleteIndividualDomain", mock.AnythingOfType("context.backgroundCtx"), "").
					Return(haproxysync.ErrMissingDomain)
			},
			Req: &haproxysyncv1.BastionDeleteIndividualDomainRequest{
				Domain: "",
			},
			ExpectedErr: status.Error(codes.InvalidArgument, haproxysync.ErrMissingDomain.Error()).Error(),
		},
		"should return an Internal status if an unexpected error occurs": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("BastionDeleteIndividualDomain", mock.AnythingOfType("context.backgroundCtx"), "fail.com").
					Return(errors.New("unexpected error"))
			},
			Req: &haproxysyncv1.BastionDeleteIndividualDomainRequest{
				Domain: "fail.com",
			},
			ExpectedErr: status.Error(codes.Internal, fmt.Errorf("delete individual domain: %w", errors.New("unexpected error")).Error()).Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			serviceMock := &haproxysync.MockHaproxysync{}
			tc.PrepareService(serviceMock)

			srv := grpc.NewHAProxySyncServer(&log, nil, cfg.GRPC{}, serviceMock)

			rsp, err := srv.BastionDeleteIndividualDomain(context.Background(), tc.Req)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedRsp, rsp)

			serviceMock.AssertExpectations(t)
		})
	}
}

func TestBastionSyncMaps(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareService func(*haproxysync.MockHaproxysync)
		Req            *haproxysyncv1.BastionSyncMapsRequest
		ExpectedRsp    *haproxysyncv1.BastionSyncMapsResponse
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("BastionSyncMaps", mock.AnythingOfType("context.backgroundCtx"), haproxysync.BastionSyncMaps{
					Subdomains:        []string{"example", "test"},
					IndividualDomains: []string{"example.com", "test.org"},
				}).Return(haproxysync.BastionSyncMapsResult{
					SubdomainsAdded:          2,
					SubdomainsRemoved:        1,
					IndividualDomainsAdded:   2,
					IndividualDomainsRemoved: 0,
				}, nil)
			},
			Req: &haproxysyncv1.BastionSyncMapsRequest{
				Subdomains:        []string{"example", "test"},
				IndividualDomains: []string{"example.com", "test.org"},
			},
			ExpectedRsp: &haproxysyncv1.BastionSyncMapsResponse{
				SubdomainsAdded:   2,
				SubdomainsRemoved: 1,
				IndividualAdded:   2,
				IndividualRemoved: 0,
			},
		},
		"should work with empty maps": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("BastionSyncMaps", mock.AnythingOfType("context.backgroundCtx"), haproxysync.BastionSyncMaps{
					Subdomains:        []string{},
					IndividualDomains: []string{},
				}).Return(haproxysync.BastionSyncMapsResult{
					SubdomainsAdded:          0,
					SubdomainsRemoved:        0,
					IndividualDomainsAdded:   0,
					IndividualDomainsRemoved: 0,
				}, nil)
			},
			Req: &haproxysyncv1.BastionSyncMapsRequest{
				Subdomains:        []string{},
				IndividualDomains: []string{},
			},
			ExpectedRsp: &haproxysyncv1.BastionSyncMapsResponse{
				SubdomainsAdded:   0,
				SubdomainsRemoved: 0,
				IndividualAdded:   0,
				IndividualRemoved: 0,
			},
		},
		"should return an Internal status if an unexpected error occurs": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("BastionSyncMaps", mock.AnythingOfType("context.backgroundCtx"), haproxysync.BastionSyncMaps{
					Subdomains:        []string{"fail"},
					IndividualDomains: []string{},
				}).Return(haproxysync.BastionSyncMapsResult{}, errors.New("unexpected error"))
			},
			Req: &haproxysyncv1.BastionSyncMapsRequest{
				Subdomains:        []string{"fail"},
				IndividualDomains: []string{},
			},
			ExpectedErr: status.Error(codes.Internal, fmt.Errorf("sync maps: %w", errors.New("unexpected error")).Error()).Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			serviceMock := &haproxysync.MockHaproxysync{}
			tc.PrepareService(serviceMock)

			srv := grpc.NewHAProxySyncServer(&log, nil, cfg.GRPC{}, serviceMock)

			rsp, err := srv.BastionSyncMaps(context.Background(), tc.Req)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedRsp, rsp)

			serviceMock.AssertExpectations(t)
		})
	}
}

func TestBastionGetCurrentMaps(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareService func(*haproxysync.MockHaproxysync)
		Req            *haproxysyncv1.BastionGetCurrentMapsRequest
		ExpectedRsp    *haproxysyncv1.BastionGetCurrentMapsResponse
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("BastionGetCurrentMaps", mock.AnythingOfType("context.backgroundCtx")).
					Return(haproxysync.BastionCurrentMaps{
						Subdomains:        []string{"example", "test"},
						IndividualDomains: []string{"example.com"},
					}, nil)
			},
			Req: &haproxysyncv1.BastionGetCurrentMapsRequest{},
			ExpectedRsp: &haproxysyncv1.BastionGetCurrentMapsResponse{
				Subdomains:        []string{"example", "test"},
				IndividualDomains: []string{"example.com"},
			},
		},
		"should work with empty maps": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("BastionGetCurrentMaps", mock.AnythingOfType("context.backgroundCtx")).
					Return(haproxysync.BastionCurrentMaps{
						Subdomains:        []string{},
						IndividualDomains: []string{},
					}, nil)
			},
			Req: &haproxysyncv1.BastionGetCurrentMapsRequest{},
			ExpectedRsp: &haproxysyncv1.BastionGetCurrentMapsResponse{
				Subdomains:        []string{},
				IndividualDomains: []string{},
			},
		},
		"should return an Internal status if an unexpected error occurs": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("BastionGetCurrentMaps", mock.AnythingOfType("context.backgroundCtx")).
					Return(haproxysync.BastionCurrentMaps{}, errors.New("unexpected error"))
			},
			Req:         &haproxysyncv1.BastionGetCurrentMapsRequest{},
			ExpectedErr: status.Error(codes.Internal, fmt.Errorf("get current maps: %w", errors.New("unexpected error")).Error()).Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			serviceMock := &haproxysync.MockHaproxysync{}
			tc.PrepareService(serviceMock)

			srv := grpc.NewHAProxySyncServer(&log, nil, cfg.GRPC{}, serviceMock)

			rsp, err := srv.BastionGetCurrentMaps(context.Background(), tc.Req)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedRsp, rsp)

			serviceMock.AssertExpectations(t)
		})
	}
}

func TestCheck(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareService func(*haproxysync.MockHaproxysync)
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("Check", mock.AnythingOfType("context.backgroundCtx")).
					Return(nil)
			},
		},
		"should return an error if the service check fails": {
			PrepareService: func(m *haproxysync.MockHaproxysync) {
				m.On("Check", mock.AnythingOfType("context.backgroundCtx")).
					Return(errors.New("haproxy connection failed"))
			},
			ExpectedErr: "check haproxy-sync service: haproxy connection failed",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			serviceMock := &haproxysync.MockHaproxysync{}
			tc.PrepareService(serviceMock)

			srv := grpc.NewHAProxySyncServer(&log, nil, cfg.GRPC{}, serviceMock)

			err := srv.Check(context.Background())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			serviceMock.AssertExpectations(t)
		})
	}
}
