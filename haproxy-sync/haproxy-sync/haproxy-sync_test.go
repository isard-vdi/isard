package haproxysync_test

import (
	"errors"
	"os"
	"path/filepath"
	"testing"

	"gitlab.com/isard/isardvdi/haproxy-sync/cfg"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy-sync"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestCheck(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareHAProxy func(*haproxy.MockHaproxy, string)
		ExpectedErrs   []string
	}{
		"should work as expected": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowPID").Return(100, nil).Once()
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@subdomains", ".example").Return(nil).Once()
				m.On("ShowMap", "virt@individual").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@individual", "test.com").Return(nil).Once()
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil).Once()
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddMap", "virt@domains", "provided.com").Return(nil).Once()

				m.On("ShowPID").Return(100, nil).Once()
			},
			ExpectedErrs: []string{""},
		},
		"should restore the state if HAProxy was reloaded without haproxy-reload": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowPID").Return(100, nil).Once()
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@subdomains", ".example").Return(nil).Once()
				m.On("ShowMap", "virt@individual").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@individual", "test.com").Return(nil).Once()
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil).Once()
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddMap", "virt@domains", "provided.com").Return(nil).Once()

				m.On("ShowPID").Return(200, nil).Once()
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@subdomains", ".example").Return(nil).Once()
				m.On("ShowMap", "virt@individual").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@individual", "test.com").Return(nil).Once()
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil).Once()
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddMap", "virt@domains", "provided.com").Return(nil).Once()

				m.On("ShowPID").Return(200, nil).Once()
			},
			ExpectedErrs: []string{"", ""},
		},
		"should retry the whole state if the bastion maps fail to restore": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowPID").Return(100, nil).Once()
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@subdomains", ".example").Return(nil).Once()
				m.On("ShowMap", "virt@individual").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@individual", "test.com").Return(nil).Once()
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil).Once()
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddMap", "virt@domains", "provided.com").Return(nil).Once()

				m.On("ShowPID").Return(200, nil).Once()
				m.On("ShowMap", "virt@subdomains").Return(nil, errors.New("connection refused")).Once()

				m.On("ShowPID").Return(200, nil).Once()
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@subdomains", ".example").Return(nil).Once()
				m.On("ShowMap", "virt@individual").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@individual", "test.com").Return(nil).Once()
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil).Once()
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddMap", "virt@domains", "provided.com").Return(nil).Once()
			},
			ExpectedErrs: []string{
				"restore the bastion maps: get current subdomains from HAProxy: connection refused",
				"",
			},
		},
		"should retry the whole state if a domain fails to restore": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowPID").Return(100, nil).Once()
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@subdomains", ".example").Return(nil).Once()
				m.On("ShowMap", "virt@individual").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@individual", "test.com").Return(nil).Once()
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil).Once()
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddMap", "virt@domains", "provided.com").Return(nil).Once()

				m.On("ShowPID").Return(200, nil).Once()
				m.On("ShowMap", "virt@subdomains").Return([]string{".example"}, nil).Once()
				m.On("ShowMap", "virt@individual").Return([]string{"test.com"}, nil).Once()
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(errors.New("connection refused")).Once()

				m.On("ShowPID").Return(200, nil).Once()
				m.On("ShowMap", "virt@subdomains").Return([]string{".example"}, nil).Once()
				m.On("ShowMap", "virt@individual").Return([]string{"test.com"}, nil).Once()
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil).Once()
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddMap", "virt@domains", "provided.com").Return(nil).Once()
			},
			ExpectedErrs: []string{
				"restore the domains: domain 'provided.com': create ssl cert storage: connection refused",
				"",
			},
		},
		"should return an error if the worker PID can't be read": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowPID").Return(100, nil).Once()
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@subdomains", ".example").Return(nil).Once()
				m.On("ShowMap", "virt@individual").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@individual", "test.com").Return(nil).Once()
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil).Once()
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddMap", "virt@domains", "provided.com").Return(nil).Once()

				m.On("ShowPID").Return(0, errors.New("connection refused")).Once()
			},
			ExpectedErrs: []string{"get HAProxy worker PID: connection refused"},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			certsPath := t.TempDir()

			haproxyMock := &haproxy.MockHaproxy{}
			tc.PrepareHAProxy(haproxyMock, certsPath)

			haproxyCfg := cfg.HAProxy{
				Domains: cfg.HAProxyDomains{
					DomainsMap:  "virt@domains",
					CrtListPath: "/certs/crt-list.cfg",
					CertsPath:   certsPath,
					BaseDomain:  testBaseDomain,
				},
				Bastion: cfg.HAProxyBastion{
					SubdomainsMap:        "virt@subdomains",
					IndividualDomainsMap: "virt@individual",
				},
			}

			svc := haproxysync.Init(log.New("test", "debug"), haproxyCfg, haproxyMock, nil)

			// The first check learns the worker the state is synced into.
			require.NoError(t, svc.Check(t.Context()))

			bastion := haproxysync.BastionSyncMaps{
				Subdomains:        []string{"example"},
				IndividualDomains: []string{"test.com"},
			}
			_, err := svc.BastionSyncMaps(t.Context(), bastion)
			require.NoError(t, err)

			domains := []haproxysync.DomainSyncDomain{{Name: "provided.com", Certificate: testPEMData}}
			_, err = svc.DomainSync(t.Context(), domains)
			require.NoError(t, err)

			for _, expected := range tc.ExpectedErrs {
				err := svc.Check(t.Context())

				if expected != "" {
					assert.EqualError(err, expected)
				} else {
					assert.NoError(err)
				}
			}

			haproxyMock.AssertExpectations(t)
		})
	}
}

func TestRestore(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	cases := map[string]struct {
		Bastion        *haproxysync.BastionSyncMaps
		Domains        []haproxysync.DomainSyncDomain
		RemoveCert     bool
		PrepareHAProxy func(*haproxy.MockHaproxy, string)
		ExpectedErr    string
	}{
		"should work as expected": {
			Bastion: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{"example"},
				IndividualDomains: []string{"test.com"},
			},
			Domains: []haproxysync.DomainSyncDomain{{Name: "provided.com", Certificate: testPEMData}},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@subdomains", ".example").Return(nil).Once()
				m.On("ShowMap", "virt@individual").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@individual", "test.com").Return(nil).Once()
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil).Once()
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddMap", "virt@domains", "provided.com").Return(nil).Once()

				m.On("ShowPID").Return(200, nil).Once()
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@subdomains", ".example").Return(nil).Once()
				m.On("ShowMap", "virt@individual").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@individual", "test.com").Return(nil).Once()
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil).Once()
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddMap", "virt@domains", "provided.com").Return(nil).Once()
			},
		},
		"should only add what the worker is missing": {
			Bastion: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{"example"},
				IndividualDomains: []string{"test.com"},
			},
			Domains: []haproxysync.DomainSyncDomain{{Name: "provided.com", Certificate: testPEMData}},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@subdomains", ".example").Return(nil).Once()
				m.On("ShowMap", "virt@individual").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@individual", "test.com").Return(nil).Once()
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil).Once()
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddMap", "virt@domains", "provided.com").Return(nil).Once()

				m.On("ShowPID").Return(200, nil).Once()
				m.On("ShowMap", "virt@subdomains").Return([]string{".example"}, nil).Once()
				m.On("ShowMap", "virt@individual").Return([]string{"test.com"}, nil).Once()
				m.On("ShowMap", "virt@domains").Return([]string{"provided.com"}, nil).Once()
			},
		},
		"should remove what the state doesn't have": {
			Bastion: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{"example"},
				IndividualDomains: []string{"test.com"},
			},
			Domains: []haproxysync.DomainSyncDomain{{Name: "provided.com", Certificate: testPEMData}},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@subdomains", ".example").Return(nil).Once()
				m.On("ShowMap", "virt@individual").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@individual", "test.com").Return(nil).Once()
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil).Once()
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddMap", "virt@domains", "provided.com").Return(nil).Once()

				m.On("ShowPID").Return(200, nil).Once()
				m.On("ShowMap", "virt@subdomains").Return([]string{".example", ".other"}, nil).Once()
				m.On("DelMap", "virt@subdomains", ".other").Return(nil).Once()
				m.On("ShowMap", "virt@individual").Return([]string{"test.com"}, nil).Once()
				m.On("ShowMap", "virt@domains").Return([]string{"provided.com"}, nil).Once()
			},
		},
		"should not touch the worker without any state": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {
				m.On("ShowPID").Return(200, nil).Once()
			},
		},
		"should not touch the bastion maps if they were never synced": {
			Domains: []haproxysync.DomainSyncDomain{{Name: "provided.com", Certificate: testPEMData}},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil).Once()
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddMap", "virt@domains", "provided.com").Return(nil).Once()

				m.On("ShowPID").Return(200, nil).Once()
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil).Once()
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddMap", "virt@domains", "provided.com").Return(nil).Once()
			},
		},
		"should not touch the domains if they were never synced": {
			Bastion: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{"example"},
				IndividualDomains: []string{"test.com"},
			},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@subdomains", ".example").Return(nil).Once()
				m.On("ShowMap", "virt@individual").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@individual", "test.com").Return(nil).Once()

				m.On("ShowPID").Return(200, nil).Once()
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@subdomains", ".example").Return(nil).Once()
				m.On("ShowMap", "virt@individual").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@individual", "test.com").Return(nil).Once()
			},
		},
		"should return an error if the worker PID can't be read": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {
				m.On("ShowPID").Return(0, errors.New("connection refused")).Once()
			},
			ExpectedErr: "get HAProxy worker PID: connection refused",
		},
		"should return an error if the bastion maps can't be restored": {
			Bastion: &haproxysync.BastionSyncMaps{
				Subdomains:        []string{"example"},
				IndividualDomains: []string{"test.com"},
			},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@subdomains", ".example").Return(nil).Once()
				m.On("ShowMap", "virt@individual").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@individual", "test.com").Return(nil).Once()

				m.On("ShowPID").Return(200, nil).Once()
				m.On("ShowMap", "virt@subdomains").Return([]string{}, nil).Once()
				m.On("AddMap", "virt@subdomains", ".example").Return(errors.New("connection refused")).Once()
			},
			ExpectedErr: "restore the bastion maps: add subdomain to HAProxy: connection refused",
		},
		"should return an error if a certificate is not on disk anymore": {
			Domains:    []haproxysync.DomainSyncDomain{{Name: "provided.com", Certificate: testPEMData}},
			RemoveCert: true,
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil).Once()
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddMap", "virt@domains", "provided.com").Return(nil).Once()

				m.On("ShowPID").Return(200, nil).Once()
			},
			ExpectedErr: "restore the domains: read certificate file for domain 'provided.com': open ",
		},
		"should return an error if the domains can't be synced": {
			Domains: []haproxysync.DomainSyncDomain{{Name: "provided.com", Certificate: testPEMData}},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil).Once()
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddMap", "virt@domains", "provided.com").Return(nil).Once()

				m.On("ShowPID").Return(200, nil).Once()
				m.On("ShowMap", "virt@domains").Return(nil, errors.New("connection refused")).Once()
			},
			ExpectedErr: "restore the domains: get current domains from HAProxy: connection refused",
		},
		"should return an error if a domain can't be restored": {
			Domains: []haproxysync.DomainSyncDomain{{Name: "provided.com", Certificate: testPEMData}},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil).Once()
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil).Once()
				m.On("AddMap", "virt@domains", "provided.com").Return(nil).Once()

				m.On("ShowPID").Return(200, nil).Once()
				m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(errors.New("connection refused")).Once()
			},
			ExpectedErr: "restore the domains: domain 'provided.com': create ssl cert storage: connection refused",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			certsPath := t.TempDir()

			haproxyMock := &haproxy.MockHaproxy{}
			tc.PrepareHAProxy(haproxyMock, certsPath)

			haproxyCfg := cfg.HAProxy{
				Domains: cfg.HAProxyDomains{
					DomainsMap:  "virt@domains",
					CrtListPath: "/certs/crt-list.cfg",
					CertsPath:   certsPath,
					BaseDomain:  testBaseDomain,
				},
				Bastion: cfg.HAProxyBastion{
					SubdomainsMap:        "virt@subdomains",
					IndividualDomainsMap: "virt@individual",
				},
			}

			svc := haproxysync.Init(log.New("test", "debug"), haproxyCfg, haproxyMock, nil)

			if tc.Bastion != nil {
				_, err := svc.BastionSyncMaps(t.Context(), *tc.Bastion)
				require.NoError(t, err)
			}

			if tc.Domains != nil {
				_, err := svc.DomainSync(t.Context(), tc.Domains)
				require.NoError(t, err)
			}

			if tc.RemoveCert {
				require.NoError(t, os.Remove(filepath.Join(certsPath, "provided.com.pem")))
			}

			err := svc.Restore(t.Context())

			if tc.ExpectedErr != "" {
				assert.ErrorContains(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			haproxyMock.AssertExpectations(t)
		})
	}
}
