package grpc_test

import (
	"context"
	"errors"
	"fmt"
	"os"
	"testing"

	"gitlab.com/isard/isardvdi/haproxy-bastion-sync/haproxy-bastion-sync"
	"gitlab.com/isard/isardvdi/haproxy-bastion-sync/transport/grpc"
	"gitlab.com/isard/isardvdi/pkg/cfg"
	haproxyv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/haproxy/v1"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

func TestAddSubdomain(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareService func(*haproxybastionsync.MockHaproxybastionsync)
		Req            *haproxyv1.AddSubdomainRequest
		ExpectedRsp    *haproxyv1.AddSubdomainResponse
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("AddSubdomain", mock.AnythingOfType("context.backgroundCtx"), "example").
					Return(nil)
			},
			Req: &haproxyv1.AddSubdomainRequest{
				Domain: "example",
			},
			ExpectedRsp: &haproxyv1.AddSubdomainResponse{},
		},
		"should return an InvalidArgument status if subdomain is missing": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("AddSubdomain", mock.AnythingOfType("context.backgroundCtx"), "").
					Return(haproxybastionsync.ErrMissingSubdomain)
			},
			Req: &haproxyv1.AddSubdomainRequest{
				Domain: "",
			},
			ExpectedErr: status.Error(codes.InvalidArgument, haproxybastionsync.ErrMissingSubdomain.Error()).Error(),
		},
		"should return an Internal status if an unexpected error occurs": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("AddSubdomain", mock.AnythingOfType("context.backgroundCtx"), "fail").
					Return(errors.New("unexpected error"))
			},
			Req: &haproxyv1.AddSubdomainRequest{
				Domain: "fail",
			},
			ExpectedErr: status.Error(codes.Internal, fmt.Errorf("add subdomain: %w", errors.New("unexpected error")).Error()).Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			serviceMock := &haproxybastionsync.MockHaproxybastionsync{}
			tc.PrepareService(serviceMock)

			srv := grpc.NewHAProxyBastionSyncServer(&log, nil, cfg.GRPC{}, serviceMock)

			rsp, err := srv.AddSubdomain(context.Background(), tc.Req)

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

func TestDeleteSubdomain(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareService func(*haproxybastionsync.MockHaproxybastionsync)
		Req            *haproxyv1.DeleteSubdomainRequest
		ExpectedRsp    *haproxyv1.DeleteSubdomainResponse
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("DeleteSubdomain", mock.AnythingOfType("context.backgroundCtx"), "example").
					Return(nil)
			},
			Req: &haproxyv1.DeleteSubdomainRequest{
				Domain: "example",
			},
			ExpectedRsp: &haproxyv1.DeleteSubdomainResponse{},
		},
		"should return an InvalidArgument status if subdomain is missing": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("DeleteSubdomain", mock.AnythingOfType("context.backgroundCtx"), "").
					Return(haproxybastionsync.ErrMissingSubdomain)
			},
			Req: &haproxyv1.DeleteSubdomainRequest{
				Domain: "",
			},
			ExpectedErr: status.Error(codes.InvalidArgument, haproxybastionsync.ErrMissingSubdomain.Error()).Error(),
		},
		"should return an Internal status if an unexpected error occurs": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("DeleteSubdomain", mock.AnythingOfType("context.backgroundCtx"), "fail").
					Return(errors.New("unexpected error"))
			},
			Req: &haproxyv1.DeleteSubdomainRequest{
				Domain: "fail",
			},
			ExpectedErr: status.Error(codes.Internal, fmt.Errorf("delete subdomain: %w", errors.New("unexpected error")).Error()).Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			serviceMock := &haproxybastionsync.MockHaproxybastionsync{}
			tc.PrepareService(serviceMock)

			srv := grpc.NewHAProxyBastionSyncServer(&log, nil, cfg.GRPC{}, serviceMock)

			rsp, err := srv.DeleteSubdomain(context.Background(), tc.Req)

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

func TestAddIndividualDomain(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareService func(*haproxybastionsync.MockHaproxybastionsync)
		Req            *haproxyv1.AddIndividualDomainRequest
		ExpectedRsp    *haproxyv1.AddIndividualDomainResponse
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("AddIndividualDomain", mock.AnythingOfType("context.backgroundCtx"), "example.com").
					Return(nil)
			},
			Req: &haproxyv1.AddIndividualDomainRequest{
				Domain: "example.com",
			},
			ExpectedRsp: &haproxyv1.AddIndividualDomainResponse{},
		},
		"should return an InvalidArgument status if domain is missing": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("AddIndividualDomain", mock.AnythingOfType("context.backgroundCtx"), "").
					Return(haproxybastionsync.ErrMissingDomain)
			},
			Req: &haproxyv1.AddIndividualDomainRequest{
				Domain: "",
			},
			ExpectedErr: status.Error(codes.InvalidArgument, haproxybastionsync.ErrMissingDomain.Error()).Error(),
		},
		"should return an Internal status if an unexpected error occurs": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("AddIndividualDomain", mock.AnythingOfType("context.backgroundCtx"), "fail.com").
					Return(errors.New("unexpected error"))
			},
			Req: &haproxyv1.AddIndividualDomainRequest{
				Domain: "fail.com",
			},
			ExpectedErr: status.Error(codes.Internal, fmt.Errorf("add individual domain: %w", errors.New("unexpected error")).Error()).Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			serviceMock := &haproxybastionsync.MockHaproxybastionsync{}
			tc.PrepareService(serviceMock)

			srv := grpc.NewHAProxyBastionSyncServer(&log, nil, cfg.GRPC{}, serviceMock)

			rsp, err := srv.AddIndividualDomain(context.Background(), tc.Req)

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

func TestDeleteIndividualDomain(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareService func(*haproxybastionsync.MockHaproxybastionsync)
		Req            *haproxyv1.DeleteIndividualDomainRequest
		ExpectedRsp    *haproxyv1.DeleteIndividualDomainResponse
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("DeleteIndividualDomain", mock.AnythingOfType("context.backgroundCtx"), "example.com").
					Return(nil)
			},
			Req: &haproxyv1.DeleteIndividualDomainRequest{
				Domain: "example.com",
			},
			ExpectedRsp: &haproxyv1.DeleteIndividualDomainResponse{},
		},
		"should return an InvalidArgument status if domain is missing": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("DeleteIndividualDomain", mock.AnythingOfType("context.backgroundCtx"), "").
					Return(haproxybastionsync.ErrMissingDomain)
			},
			Req: &haproxyv1.DeleteIndividualDomainRequest{
				Domain: "",
			},
			ExpectedErr: status.Error(codes.InvalidArgument, haproxybastionsync.ErrMissingDomain.Error()).Error(),
		},
		"should return an Internal status if an unexpected error occurs": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("DeleteIndividualDomain", mock.AnythingOfType("context.backgroundCtx"), "fail.com").
					Return(errors.New("unexpected error"))
			},
			Req: &haproxyv1.DeleteIndividualDomainRequest{
				Domain: "fail.com",
			},
			ExpectedErr: status.Error(codes.Internal, fmt.Errorf("delete individual domain: %w", errors.New("unexpected error")).Error()).Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			serviceMock := &haproxybastionsync.MockHaproxybastionsync{}
			tc.PrepareService(serviceMock)

			srv := grpc.NewHAProxyBastionSyncServer(&log, nil, cfg.GRPC{}, serviceMock)

			rsp, err := srv.DeleteIndividualDomain(context.Background(), tc.Req)

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

func TestSyncMaps(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareService func(*haproxybastionsync.MockHaproxybastionsync)
		Req            *haproxyv1.SyncMapsRequest
		ExpectedRsp    *haproxyv1.SyncMapsResponse
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("SyncMaps", mock.AnythingOfType("context.backgroundCtx"), haproxybastionsync.SyncMaps{
					Subdomains:        []string{"example", "test"},
					IndividualDomains: []string{"example.com", "test.org"},
				}).Return(haproxybastionsync.SyncMapsResult{
					SubdomainsAdded:          2,
					SubdomainsRemoved:        1,
					IndividualDomainsAdded:   2,
					IndividualDomainsRemoved: 0,
				}, nil)
			},
			Req: &haproxyv1.SyncMapsRequest{
				Subdomains:        []string{"example", "test"},
				IndividualDomains: []string{"example.com", "test.org"},
			},
			ExpectedRsp: &haproxyv1.SyncMapsResponse{
				SubdomainsAdded:   2,
				SubdomainsRemoved: 1,
				IndividualAdded:   2,
				IndividualRemoved: 0,
			},
		},
		"should work with empty maps": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("SyncMaps", mock.AnythingOfType("context.backgroundCtx"), haproxybastionsync.SyncMaps{
					Subdomains:        []string{},
					IndividualDomains: []string{},
				}).Return(haproxybastionsync.SyncMapsResult{
					SubdomainsAdded:          0,
					SubdomainsRemoved:        0,
					IndividualDomainsAdded:   0,
					IndividualDomainsRemoved: 0,
				}, nil)
			},
			Req: &haproxyv1.SyncMapsRequest{
				Subdomains:        []string{},
				IndividualDomains: []string{},
			},
			ExpectedRsp: &haproxyv1.SyncMapsResponse{
				SubdomainsAdded:   0,
				SubdomainsRemoved: 0,
				IndividualAdded:   0,
				IndividualRemoved: 0,
			},
		},
		"should return an Internal status if an unexpected error occurs": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("SyncMaps", mock.AnythingOfType("context.backgroundCtx"), haproxybastionsync.SyncMaps{
					Subdomains:        []string{"fail"},
					IndividualDomains: []string{},
				}).Return(haproxybastionsync.SyncMapsResult{}, errors.New("unexpected error"))
			},
			Req: &haproxyv1.SyncMapsRequest{
				Subdomains:        []string{"fail"},
				IndividualDomains: []string{},
			},
			ExpectedErr: status.Error(codes.Internal, fmt.Errorf("sync maps: %w", errors.New("unexpected error")).Error()).Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			serviceMock := &haproxybastionsync.MockHaproxybastionsync{}
			tc.PrepareService(serviceMock)

			srv := grpc.NewHAProxyBastionSyncServer(&log, nil, cfg.GRPC{}, serviceMock)

			rsp, err := srv.SyncMaps(context.Background(), tc.Req)

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

func TestGetCurrentMaps(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareService func(*haproxybastionsync.MockHaproxybastionsync)
		Req            *haproxyv1.GetCurrentMapsRequest
		ExpectedRsp    *haproxyv1.GetCurrentMapsResponse
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("GetCurrentMaps", mock.AnythingOfType("context.backgroundCtx")).
					Return(haproxybastionsync.CurrentMaps{
						Subdomains:        []string{"example", "test"},
						IndividualDomains: []string{"example.com"},
					}, nil)
			},
			Req: &haproxyv1.GetCurrentMapsRequest{},
			ExpectedRsp: &haproxyv1.GetCurrentMapsResponse{
				Subdomains:        []string{"example", "test"},
				IndividualDomains: []string{"example.com"},
			},
		},
		"should work with empty maps": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("GetCurrentMaps", mock.AnythingOfType("context.backgroundCtx")).
					Return(haproxybastionsync.CurrentMaps{
						Subdomains:        []string{},
						IndividualDomains: []string{},
					}, nil)
			},
			Req: &haproxyv1.GetCurrentMapsRequest{},
			ExpectedRsp: &haproxyv1.GetCurrentMapsResponse{
				Subdomains:        []string{},
				IndividualDomains: []string{},
			},
		},
		"should return an Internal status if an unexpected error occurs": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("GetCurrentMaps", mock.AnythingOfType("context.backgroundCtx")).
					Return(haproxybastionsync.CurrentMaps{}, errors.New("unexpected error"))
			},
			Req:         &haproxyv1.GetCurrentMapsRequest{},
			ExpectedErr: status.Error(codes.Internal, fmt.Errorf("get current maps: %w", errors.New("unexpected error")).Error()).Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			serviceMock := &haproxybastionsync.MockHaproxybastionsync{}
			tc.PrepareService(serviceMock)

			srv := grpc.NewHAProxyBastionSyncServer(&log, nil, cfg.GRPC{}, serviceMock)

			rsp, err := srv.GetCurrentMaps(context.Background(), tc.Req)

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
		PrepareService func(*haproxybastionsync.MockHaproxybastionsync)
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("Check", mock.AnythingOfType("context.backgroundCtx")).
					Return(nil)
			},
		},
		"should return an error if the service check fails": {
			PrepareService: func(m *haproxybastionsync.MockHaproxybastionsync) {
				m.On("Check", mock.AnythingOfType("context.backgroundCtx")).
					Return(errors.New("haproxy connection failed"))
			},
			ExpectedErr: "check haproxy-bastion-sync service: haproxy connection failed",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.New(os.Stdout)

			serviceMock := &haproxybastionsync.MockHaproxybastionsync{}
			tc.PrepareService(serviceMock)

			srv := grpc.NewHAProxyBastionSyncServer(&log, nil, cfg.GRPC{}, serviceMock)

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
