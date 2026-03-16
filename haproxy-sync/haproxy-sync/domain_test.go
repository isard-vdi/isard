package haproxysync_test

import (
	"errors"
	"os"
	"path/filepath"
	"testing"

	"gitlab.com/isard/isardvdi/haproxy-sync/acme"
	"gitlab.com/isard/isardvdi/haproxy-sync/cfg"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy"
	haproxysync "gitlab.com/isard/isardvdi/haproxy-sync/haproxy-sync"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
)

var testPEMData = []byte("-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----\n")

func TestDomainSync(t *testing.T) {
	t.Parallel()

	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareCerts   func(string)
		PrepareHAProxy func(*haproxy.MockHaproxy, string)
		PrepareACME    func(*acme.MockAcme)
		Domains        []string
		ExpectedResult haproxysync.DomainSyncResult
		ExpectedErr    string
	}{
		"should work as expected with empty maps": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
			},
			PrepareACME: func(m *acme.MockAcme) {},
			Domains:     []string{},
			ExpectedResult: haproxysync.DomainSyncResult{
				DomainsAdded:   0,
				DomainsRemoved: 0,
				CertsIssued:    0,
				CertsRemoved:   0,
			},
		},
		"should add missing domains": {
			PrepareCerts: func(certsPath string) {
				require.NoError(os.WriteFile(filepath.Join(certsPath, "example.com.pem"), testPEMData, 0644))
				require.NoError(os.WriteFile(filepath.Join(certsPath, "test.org.pem"), testPEMData, 0644))
			},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
				m.On("NewSslCert", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("SetSslCert", filepath.Join(certsPath, "example.com.pem"), testPEMData).Return(nil)
				m.On("CommitSslCert", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("AddMap", "virt@domains", "example.com").Return(nil)
				m.On("NewSslCert", filepath.Join(certsPath, "test.org.pem")).Return(nil)
				m.On("SetSslCert", filepath.Join(certsPath, "test.org.pem"), testPEMData).Return(nil)
				m.On("CommitSslCert", filepath.Join(certsPath, "test.org.pem")).Return(nil)
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "test.org.pem")).Return(nil)
				m.On("AddMap", "virt@domains", "test.org").Return(nil)
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "example.com", "example.com.pem").Return(nil)
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "test.org", "test.org.pem").Return(nil)
			},
			Domains: []string{"example.com", "test.org"},
			ExpectedResult: haproxysync.DomainSyncResult{
				DomainsAdded:   2,
				DomainsRemoved: 0,
				CertsIssued:    2,
				CertsRemoved:   0,
			},
		},
		"should remove extra domains": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{"example.com", "old.com"}, nil)
				m.On("DelMap", "virt@domains", "old.com").Return(nil)
				m.On("DelSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "old.com.pem")).Return(nil)
				m.On("DelSslCert", filepath.Join(certsPath, "old.com.pem")).Return(nil)
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("RemoveCert", mock.AnythingOfType("*context.cancelCtx"), "old.com", "old.com.pem").Return(nil)
			},
			Domains: []string{"example.com"},
			ExpectedResult: haproxysync.DomainSyncResult{
				DomainsAdded:   0,
				DomainsRemoved: 1,
				CertsIssued:    0,
				CertsRemoved:   1,
			},
		},
		"should handle full sync with adds and removes": {
			PrepareCerts: func(certsPath string) {
				require.NoError(os.WriteFile(filepath.Join(certsPath, "new.com.pem"), testPEMData, 0644))
			},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{"existing.com", "old.com"}, nil)
				m.On("NewSslCert", filepath.Join(certsPath, "new.com.pem")).Return(nil)
				m.On("SetSslCert", filepath.Join(certsPath, "new.com.pem"), testPEMData).Return(nil)
				m.On("CommitSslCert", filepath.Join(certsPath, "new.com.pem")).Return(nil)
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "new.com.pem")).Return(nil)
				m.On("AddMap", "virt@domains", "new.com").Return(nil)
				m.On("DelMap", "virt@domains", "old.com").Return(nil)
				m.On("DelSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "old.com.pem")).Return(nil)
				m.On("DelSslCert", filepath.Join(certsPath, "old.com.pem")).Return(nil)
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "new.com", "new.com.pem").Return(nil)
				m.On("RemoveCert", mock.AnythingOfType("*context.cancelCtx"), "old.com", "old.com.pem").Return(nil)
			},
			Domains: []string{"existing.com", "new.com"},
			ExpectedResult: haproxysync.DomainSyncResult{
				DomainsAdded:   1,
				DomainsRemoved: 1,
				CertsIssued:    1,
				CertsRemoved:   1,
			},
		},
		"should return an error if getting domains fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, errors.New("socket error"))
			},
			PrepareACME: func(m *acme.MockAcme) {},
			Domains:     []string{"example.com"},
			ExpectedErr: "get current domains from HAProxy: socket error",
		},
		"should return an error if cert issuance fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "example.com", "example.com.pem").Return(errors.New("acme error"))
			},
			Domains:     []string{"example.com"},
			ExpectedErr: "issue certificate for domain 'example.com': acme error",
		},
		"should return an error if reading the certificate file fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "example.com", "example.com.pem").Return(nil)
			},
			Domains:     []string{"example.com"},
			ExpectedErr: "read certificate file for domain 'example.com':",
		},
		"should return an error if creating the ssl cert storage fails": {
			PrepareCerts: func(certsPath string) {
				require.NoError(os.WriteFile(filepath.Join(certsPath, "example.com.pem"), testPEMData, 0644))
			},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
				m.On("NewSslCert", filepath.Join(certsPath, "example.com.pem")).Return(errors.New("new cert error"))
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "example.com", "example.com.pem").Return(nil)
			},
			Domains:     []string{"example.com"},
			ExpectedErr: "create ssl cert storage for domain 'example.com': new cert error",
		},
		"should return an error if setting the ssl cert content fails": {
			PrepareCerts: func(certsPath string) {
				require.NoError(os.WriteFile(filepath.Join(certsPath, "example.com.pem"), testPEMData, 0644))
			},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
				m.On("NewSslCert", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("SetSslCert", filepath.Join(certsPath, "example.com.pem"), testPEMData).Return(errors.New("set cert error"))
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "example.com", "example.com.pem").Return(nil)
			},
			Domains:     []string{"example.com"},
			ExpectedErr: "set ssl cert content for domain 'example.com': set cert error",
		},
		"should return an error if committing the ssl cert fails": {
			PrepareCerts: func(certsPath string) {
				require.NoError(os.WriteFile(filepath.Join(certsPath, "example.com.pem"), testPEMData, 0644))
			},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
				m.On("NewSslCert", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("SetSslCert", filepath.Join(certsPath, "example.com.pem"), testPEMData).Return(nil)
				m.On("CommitSslCert", filepath.Join(certsPath, "example.com.pem")).Return(errors.New("commit error"))
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "example.com", "example.com.pem").Return(nil)
			},
			Domains:     []string{"example.com"},
			ExpectedErr: "commit ssl cert for domain 'example.com': commit error",
		},
		"should return an error if adding ssl crt-list fails": {
			PrepareCerts: func(certsPath string) {
				require.NoError(os.WriteFile(filepath.Join(certsPath, "example.com.pem"), testPEMData, 0644))
			},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
				m.On("NewSslCert", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("SetSslCert", filepath.Join(certsPath, "example.com.pem"), testPEMData).Return(nil)
				m.On("CommitSslCert", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "example.com.pem")).Return(errors.New("crt-list error"))
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "example.com", "example.com.pem").Return(nil)
			},
			Domains:     []string{"example.com"},
			ExpectedErr: "add ssl crt-list for domain 'example.com': crt-list error",
		},
		"should return an error if adding domain fails": {
			PrepareCerts: func(certsPath string) {
				require.NoError(os.WriteFile(filepath.Join(certsPath, "example.com.pem"), testPEMData, 0644))
			},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
				m.On("NewSslCert", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("SetSslCert", filepath.Join(certsPath, "example.com.pem"), testPEMData).Return(nil)
				m.On("CommitSslCert", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("AddMap", "virt@domains", "example.com").Return(errors.New("add failed"))
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "example.com", "example.com.pem").Return(nil)
			},
			Domains:     []string{"example.com"},
			ExpectedErr: "add domain to HAProxy: add failed",
		},
		"should return an error if deleting domain fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {
				m.On("ShowMap", "virt@domains").Return([]string{"old.com"}, nil)
				m.On("DelMap", "virt@domains", "old.com").Return(errors.New("delete failed"))
			},
			PrepareACME: func(m *acme.MockAcme) {},
			Domains:     []string{},
			ExpectedErr: "delete domain from HAProxy: delete failed",
		},
		"should return an error if deleting ssl crt-list fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{"old.com"}, nil)
				m.On("DelMap", "virt@domains", "old.com").Return(nil)
				m.On("DelSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "old.com.pem")).Return(errors.New("crt-list error"))
			},
			PrepareACME: func(m *acme.MockAcme) {},
			Domains:     []string{},
			ExpectedErr: "delete ssl crt-list for domain 'old.com': crt-list error",
		},
		"should return an error if cert removal fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{"old.com"}, nil)
				m.On("DelMap", "virt@domains", "old.com").Return(nil)
				m.On("DelSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "old.com.pem")).Return(nil)
				m.On("DelSslCert", filepath.Join(certsPath, "old.com.pem")).Return(nil)
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("RemoveCert", mock.AnythingOfType("*context.cancelCtx"), "old.com", "old.com.pem").Return(errors.New("remove error"))
			},
			Domains:     []string{},
			ExpectedErr: "remove certificate for domain 'old.com': remove error",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			certsPath := t.TempDir()
			if tc.PrepareCerts != nil {
				tc.PrepareCerts(certsPath)
			}

			haproxyMock := &haproxy.MockHaproxy{}
			tc.PrepareHAProxy(haproxyMock, certsPath)

			acmeMock := &acme.MockAcme{}
			tc.PrepareACME(acmeMock)

			haproxyCfg := cfg.HAProxy{
				Domains: cfg.HAProxyDomains{
					DomainsMap:  "virt@domains",
					CrtListPath: "/certs/crt-list.cfg",
					CertsPath:   certsPath,
				},
			}

			svc := haproxysync.Init(log.New("test", "debug"), haproxyCfg, haproxyMock, acmeMock)

			result, err := svc.DomainSync(t.Context(), tc.Domains)

			if tc.ExpectedErr != "" {
				assert.ErrorContains(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedResult, result)

			haproxyMock.AssertExpectations(t)
			acmeMock.AssertExpectations(t)
		})
	}
}
