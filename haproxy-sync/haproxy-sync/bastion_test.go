package haproxysync_test

import (
	"context"
	"errors"
	"testing"

	"gitlab.com/isard/isardvdi/haproxy-sync/cfg"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy-sync"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestBastionSyncMaps(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareHAProxy func(*haproxy.MockHaproxy)
		Maps           haproxysync.BastionSyncMaps
		ExpectedResult haproxysync.BastionSyncMapsResult
		ExpectedErr    string
	}{
		"should work as expected with empty maps": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
			},
			Maps: haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{},
			},
			ExpectedResult: haproxysync.BastionSyncMapsResult{
				SubdomainsAdded:          0,
				SubdomainsRemoved:        0,
				IndividualDomainsAdded:   0,
				IndividualDomainsRemoved: 0,
			},
		},
		"should add missing subdomains": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("AddMap", "virt@subdomains", ".example").Return(nil)
				m.On("AddMap", "virt@subdomains", ".test").Return(nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
			},
			Maps: haproxysync.BastionSyncMaps{
				Subdomains:        []string{"example", "test"},
				IndividualDomains: []string{},
			},
			ExpectedResult: haproxysync.BastionSyncMapsResult{
				SubdomainsAdded:          2,
				SubdomainsRemoved:        0,
				IndividualDomainsAdded:   0,
				IndividualDomainsRemoved: 0,
			},
		},
		"should remove extra subdomains": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{".example", ".test", ".old"}, nil)
				m.On("DelMap", "virt@subdomains", ".old").Return(nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
			},
			Maps: haproxysync.BastionSyncMaps{
				Subdomains:        []string{"example", "test"},
				IndividualDomains: []string{},
			},
			ExpectedResult: haproxysync.BastionSyncMapsResult{
				SubdomainsAdded:          0,
				SubdomainsRemoved:        1,
				IndividualDomainsAdded:   0,
				IndividualDomainsRemoved: 0,
			},
		},
		"should add missing individual domains": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
				m.On("AddMap", "virt@individual", "example.com").Return(nil)
				m.On("AddMap", "virt@individual", "test.org").Return(nil)
			},
			Maps: haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{"example.com", "test.org"},
			},
			ExpectedResult: haproxysync.BastionSyncMapsResult{
				SubdomainsAdded:          0,
				SubdomainsRemoved:        0,
				IndividualDomainsAdded:   2,
				IndividualDomainsRemoved: 0,
			},
		},
		"should remove extra individual domains": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{"example.com", "old.com"}, nil)
				m.On("DelMap", "virt@individual", "old.com").Return(nil)
			},
			Maps: haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{"example.com"},
			},
			ExpectedResult: haproxysync.BastionSyncMapsResult{
				SubdomainsAdded:          0,
				SubdomainsRemoved:        0,
				IndividualDomainsAdded:   0,
				IndividualDomainsRemoved: 1,
			},
		},
		"should handle full sync with adds and removes": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{".existing", ".old"}, nil)
				m.On("AddMap", "virt@subdomains", ".new").Return(nil)
				m.On("DelMap", "virt@subdomains", ".old").Return(nil)
				m.On("ShowMap", "virt@individual").Return([]string{"existing.com", "old.com"}, nil)
				m.On("AddMap", "virt@individual", "new.com").Return(nil)
				m.On("DelMap", "virt@individual", "old.com").Return(nil)
			},
			Maps: haproxysync.BastionSyncMaps{
				Subdomains:        []string{"existing", "new"},
				IndividualDomains: []string{"existing.com", "new.com"},
			},
			ExpectedResult: haproxysync.BastionSyncMapsResult{
				SubdomainsAdded:          1,
				SubdomainsRemoved:        1,
				IndividualDomainsAdded:   1,
				IndividualDomainsRemoved: 1,
			},
		},
		"should return an error if getting subdomains fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, errors.New("socket error"))
			},
			Maps: haproxysync.BastionSyncMaps{
				Subdomains:        []string{"example"},
				IndividualDomains: []string{},
			},
			ExpectedErr: "get current subdomains from HAProxy: socket error",
		},
		"should return an error if adding subdomain fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("AddMap", "virt@subdomains", ".example").Return(errors.New("add failed"))
			},
			Maps: haproxysync.BastionSyncMaps{
				Subdomains:        []string{"example"},
				IndividualDomains: []string{},
			},
			ExpectedErr: "add subdomain to HAProxy: add failed",
		},
		"should return an error if deleting subdomain fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{".old"}, nil)
				m.On("DelMap", "virt@subdomains", ".old").Return(errors.New("delete failed"))
			},
			Maps: haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{},
			},
			ExpectedErr: "delete subdomain from HAProxy: delete failed",
		},
		"should return an error if getting individual domains fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, errors.New("socket error"))
			},
			Maps: haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{"example.com"},
			},
			ExpectedErr: "get current individual domains from HAProxy: socket error",
		},
		"should return an error if adding individual domain fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
				m.On("AddMap", "virt@individual", "example.com").Return(errors.New("add failed"))
			},
			Maps: haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{"example.com"},
			},
			ExpectedErr: "add individual domain to HAProxy: add failed",
		},
		"should return an error if deleting individual domain fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{"old.com"}, nil)
				m.On("DelMap", "virt@individual", "old.com").Return(errors.New("delete failed"))
			},
			Maps: haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{},
			},
			ExpectedErr: "delete subdomain from HAProxy: delete failed",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			haproxyMock := &haproxy.MockHaproxy{}
			tc.PrepareHAProxy(haproxyMock)

			cfg := cfg.HAProxy{
				Bastion: cfg.HAProxyBastion{
					SubdomainsMap:        "virt@subdomains",
					IndividualDomainsMap: "virt@individual",
				},
			}

			svc := haproxysync.Init(log.New("test", "debug"), cfg, haproxyMock, nil)

			result, err := svc.BastionSyncMaps(context.Background(), tc.Maps)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedResult, result)

			haproxyMock.AssertExpectations(t)
		})
	}
}

func TestBastionGetCurrentMaps(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareHAProxy func(*haproxy.MockHaproxy)
		SyncFirst      *haproxysync.BastionSyncMaps
		ExpectedResult haproxysync.BastionCurrentMaps
	}{
		"should return empty maps when no sync has been done": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {},
			ExpectedResult: haproxysync.BastionCurrentMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{},
			},
		},
		"should return current maps after sync": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("AddMap", "virt@subdomains", ".example").Return(nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
				m.On("AddMap", "virt@individual", "test.com").Return(nil)
			},
			SyncFirst: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{"example"},
				IndividualDomains: []string{"test.com"},
			},
			ExpectedResult: haproxysync.BastionCurrentMaps{
				Subdomains:        []string{"example"},
				IndividualDomains: []string{"test.com"},
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			haproxyMock := &haproxy.MockHaproxy{}
			tc.PrepareHAProxy(haproxyMock)

			cfg := cfg.HAProxy{
				Bastion: cfg.HAProxyBastion{
					SubdomainsMap:        "virt@subdomains",
					IndividualDomainsMap: "virt@individual",
				},
			}

			svc := haproxysync.Init(log.New("test", "debug"), cfg, haproxyMock, nil)

			if tc.SyncFirst != nil {
				_, err := svc.BastionSyncMaps(context.Background(), *tc.SyncFirst)
				require.NoError(err)
			}

			result, err := svc.BastionGetCurrentMaps(context.Background())

			assert.NoError(err)
			assert.ElementsMatch(tc.ExpectedResult.Subdomains, result.Subdomains)
			assert.ElementsMatch(tc.ExpectedResult.IndividualDomains, result.IndividualDomains)

			haproxyMock.AssertExpectations(t)
		})
	}
}

func TestAddSubdomain(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareHAProxy func(*haproxy.MockHaproxy)
		SyncFirst      *haproxysync.BastionSyncMaps
		Subdomain      string
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
				m.On("AddMap", "virt@subdomains", ".newsubdomain").Return(nil)
			},
			SyncFirst: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{},
			},
			Subdomain: "newsubdomain",
		},
		"should return an error if subdomain is empty": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
			},
			SyncFirst: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{},
			},
			Subdomain:   "",
			ExpectedErr: haproxysync.ErrMissingSubdomain.Error(),
		},
		"should skip if subdomain already exists": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{".existing"}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
			},
			SyncFirst: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{"existing"},
				IndividualDomains: []string{},
			},
			Subdomain: "existing",
		},
		"should return an error if HAProxy fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
				m.On("AddMap", "virt@subdomains", ".fail").Return(errors.New("socket error"))
			},
			SyncFirst: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{},
			},
			Subdomain:   "fail",
			ExpectedErr: "add subdomain to HAProxy: socket error",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			haproxyMock := &haproxy.MockHaproxy{}
			tc.PrepareHAProxy(haproxyMock)

			cfg := cfg.HAProxy{
				Bastion: cfg.HAProxyBastion{
					SubdomainsMap:        "virt@subdomains",
					IndividualDomainsMap: "virt@individual",
				},
			}

			svc := haproxysync.Init(log.New("test", "debug"), cfg, haproxyMock, nil)

			if tc.SyncFirst != nil {
				_, err := svc.BastionSyncMaps(context.Background(), *tc.SyncFirst)
				require.NoError(err)
			}

			err := svc.BastionAddSubdomain(context.Background(), tc.Subdomain)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			haproxyMock.AssertExpectations(t)
		})
	}
}

func TestDeleteSubdomain(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareHAProxy func(*haproxy.MockHaproxy)
		SyncFirst      *haproxysync.BastionSyncMaps
		Subdomain      string
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{".existing"}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
				m.On("DelMap", "virt@subdomains", ".existing").Return(nil)
			},
			SyncFirst: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{"existing"},
				IndividualDomains: []string{},
			},
			Subdomain: "existing",
		},
		"should return an error if subdomain is empty": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
			},
			SyncFirst: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{},
			},
			Subdomain:   "",
			ExpectedErr: haproxysync.ErrMissingSubdomain.Error(),
		},
		"should skip if subdomain does not exist": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
			},
			SyncFirst: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{},
			},
			Subdomain: "nonexistent",
		},
		"should return an error if HAProxy fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{".fail"}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
				m.On("DelMap", "virt@subdomains", ".fail").Return(errors.New("socket error"))
			},
			SyncFirst: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{"fail"},
				IndividualDomains: []string{},
			},
			Subdomain:   "fail",
			ExpectedErr: "delete subdomain from HAProxy: socket error",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			haproxyMock := &haproxy.MockHaproxy{}
			tc.PrepareHAProxy(haproxyMock)

			cfg := cfg.HAProxy{
				Bastion: cfg.HAProxyBastion{
					SubdomainsMap:        "virt@subdomains",
					IndividualDomainsMap: "virt@individual",
				},
			}

			svc := haproxysync.Init(log.New("test", "debug"), cfg, haproxyMock, nil)

			if tc.SyncFirst != nil {
				_, err := svc.BastionSyncMaps(context.Background(), *tc.SyncFirst)
				require.NoError(err)
			}

			err := svc.BastionDeleteSubdomain(context.Background(), tc.Subdomain)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			haproxyMock.AssertExpectations(t)
		})
	}
}

func TestAddIndividualDomain(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareHAProxy func(*haproxy.MockHaproxy)
		SyncFirst      *haproxysync.BastionSyncMaps
		Domain         string
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
				m.On("AddMap", "virt@individual", "newdomain.com").Return(nil)
			},
			SyncFirst: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{},
			},
			Domain: "newdomain.com",
		},
		"should return an error if domain is empty": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
			},
			SyncFirst: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{},
			},
			Domain:      "",
			ExpectedErr: haproxysync.ErrMissingDomain.Error(),
		},
		"should skip if domain already exists": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{"existing.com"}, nil)
			},
			SyncFirst: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{"existing.com"},
			},
			Domain: "existing.com",
		},
		"should return an error if HAProxy fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
				m.On("AddMap", "virt@individual", "fail.com").Return(errors.New("socket error"))
			},
			SyncFirst: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{},
			},
			Domain:      "fail.com",
			ExpectedErr: "add individual domain to HAProxy: socket error",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			haproxyMock := &haproxy.MockHaproxy{}
			tc.PrepareHAProxy(haproxyMock)

			cfg := cfg.HAProxy{
				Bastion: cfg.HAProxyBastion{
					SubdomainsMap:        "virt@subdomains",
					IndividualDomainsMap: "virt@individual",
				},
			}

			svc := haproxysync.Init(log.New("test", "debug"), cfg, haproxyMock, nil)

			if tc.SyncFirst != nil {
				_, err := svc.BastionSyncMaps(context.Background(), *tc.SyncFirst)
				require.NoError(err)
			}

			err := svc.BastionAddIndividualDomain(context.Background(), tc.Domain)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			haproxyMock.AssertExpectations(t)
		})
	}
}

func TestBastionDeleteIndividualDomain(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareHAProxy func(*haproxy.MockHaproxy)
		SyncFirst      *haproxysync.BastionSyncMaps
		Domain         string
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{"existing.com"}, nil)
				m.On("DelMap", "virt@individual", "existing.com").Return(nil)
			},
			SyncFirst: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{"existing.com"},
			},
			Domain: "existing.com",
		},
		"should return an error if domain is empty": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
			},
			SyncFirst: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{},
			},
			Domain:      "",
			ExpectedErr: haproxysync.ErrMissingDomain.Error(),
		},
		"should skip if domain does not exist": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{}, nil)
			},
			SyncFirst: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{},
			},
			Domain: "nonexistent.com",
		},
		"should return an error if HAProxy fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil)
				m.On("ShowMap", "virt@individual").Return([]string{"fail.com"}, nil)
				m.On("DelMap", "virt@individual", "fail.com").Return(errors.New("socket error"))
			},
			SyncFirst: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{},
				IndividualDomains: []string{"fail.com"},
			},
			Domain:      "fail.com",
			ExpectedErr: "delete individual domain from HAProxy: socket error",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			haproxyMock := &haproxy.MockHaproxy{}
			tc.PrepareHAProxy(haproxyMock)

			cfg := cfg.HAProxy{
				Bastion: cfg.HAProxyBastion{
					SubdomainsMap:        "virt@subdomains",
					IndividualDomainsMap: "virt@individual",
				},
			}

			svc := haproxysync.Init(log.New("test", "debug"), cfg, haproxyMock, nil)

			if tc.SyncFirst != nil {
				_, err := svc.BastionSyncMaps(context.Background(), *tc.SyncFirst)
				require.NoError(err)
			}

			err := svc.BastionDeleteIndividualDomain(context.Background(), tc.Domain)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			haproxyMock.AssertExpectations(t)
		})
	}
}
