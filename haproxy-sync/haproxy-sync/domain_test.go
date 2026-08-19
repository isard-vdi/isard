package haproxysync_test

import (
	"errors"
	"os"
	"path/filepath"
	"strings"
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

// testBaseDomain is the deployment's own domain.
const testBaseDomain = "portal.example.com"

func TestDomainSync(t *testing.T) {
	t.Parallel()

	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareCerts          func(string)
		PrepareHAProxy        func(*haproxy.MockHaproxy, string)
		PrepareACME           func(*acme.MockAcme)
		Domains               []haproxysync.DomainSyncDomain
		ExpectedResult        haproxysync.DomainSyncResult
		ExpectedFailedDomains []haproxysync.DomainSyncError
		ExpectedErr           string
	}{
		"should work as expected with empty maps": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
			},
			PrepareACME: func(m *acme.MockAcme) {},
			Domains:     []haproxysync.DomainSyncDomain{},
			ExpectedResult: haproxysync.DomainSyncResult{
				DomainsAdded:   0,
				DomainsRemoved: 0,
				CertsIssued:    0,
				CertsRemoved:   0,
			},
		},
		"should add missing domains via ACME": {
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
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "example.com"},
				{Name: "test.org"},
			},
			ExpectedResult: haproxysync.DomainSyncResult{
				DomainsAdded:   2,
				DomainsRemoved: 0,
				CertsIssued:    2,
				CertsRemoved:   0,
			},
		},
		"should add domain with provided certificate": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil)
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil)
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil)
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil)
				m.On("AddMap", "virt@domains", "provided.com").Return(nil)
			},
			PrepareACME: func(m *acme.MockAcme) {},
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "provided.com", Certificate: testPEMData},
			},
			ExpectedResult: haproxysync.DomainSyncResult{
				DomainsAdded:   1,
				DomainsRemoved: 0,
				CertsIssued:    0,
				CertsRemoved:   0,
			},
		},
		"should handle mix of ACME and provided certificates": {
			PrepareCerts: func(certsPath string) {
				require.NoError(os.WriteFile(filepath.Join(certsPath, "acme.com.pem"), testPEMData, 0644))
			},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
				// ACME domain
				m.On("NewSslCert", filepath.Join(certsPath, "acme.com.pem")).Return(nil)
				m.On("SetSslCert", filepath.Join(certsPath, "acme.com.pem"), testPEMData).Return(nil)
				m.On("CommitSslCert", filepath.Join(certsPath, "acme.com.pem")).Return(nil)
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "acme.com.pem")).Return(nil)
				m.On("AddMap", "virt@domains", "acme.com").Return(nil)
				// Provided domain
				m.On("NewSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil)
				m.On("SetSslCert", filepath.Join(certsPath, "provided.com.pem"), testPEMData).Return(nil)
				m.On("CommitSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil)
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil)
				m.On("AddMap", "virt@domains", "provided.com").Return(nil)
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "acme.com", "acme.com.pem").Return(nil)
			},
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "acme.com"},
				{Name: "provided.com", Certificate: testPEMData},
			},
			ExpectedResult: haproxysync.DomainSyncResult{
				DomainsAdded:   2,
				DomainsRemoved: 0,
				CertsIssued:    1,
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
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "example.com"},
			},
			ExpectedResult: haproxysync.DomainSyncResult{
				DomainsAdded:   0,
				DomainsRemoved: 1,
				CertsIssued:    0,
				CertsRemoved:   1,
			},
		},
		"should remove provided domain with tolerant ACME removal": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{"provided.com"}, nil)
				m.On("DelMap", "virt@domains", "provided.com").Return(nil)
				m.On("DelSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "provided.com.pem")).Return(nil)
				m.On("DelSslCert", filepath.Join(certsPath, "provided.com.pem")).Return(nil)
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("RemoveCert", mock.AnythingOfType("*context.cancelCtx"), "provided.com", "provided.com.pem").Return(nil)
			},
			Domains: []haproxysync.DomainSyncDomain{},
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
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "existing.com"},
				{Name: "new.com"},
			},
			ExpectedResult: haproxysync.DomainSyncResult{
				DomainsAdded:   1,
				DomainsRemoved: 1,
				CertsIssued:    1,
				CertsRemoved:   1,
			},
		},
		"should succeed on retry when cert slot already exists": {
			PrepareCerts: func(certsPath string) {
				require.NoError(os.WriteFile(filepath.Join(certsPath, "example.com.pem"), testPEMData, 0644))
			},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
				m.On("NewSslCert", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("SetSslCert", filepath.Join(certsPath, "example.com.pem"), testPEMData).Return(nil)
				m.On("CommitSslCert", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("AddMap", "virt@domains", "example.com").Return(nil)
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "example.com", "example.com.pem").Return(nil)
			},
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "example.com"},
			},
			ExpectedResult: haproxysync.DomainSyncResult{
				DomainsAdded:   1,
				DomainsRemoved: 0,
				CertsIssued:    1,
				CertsRemoved:   0,
			},
		},
		"should return an error if getting domains fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, errors.New("socket error"))
			},
			PrepareACME: func(m *acme.MockAcme) {},
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "example.com"},
			},
			ExpectedErr: "get current domains from HAProxy: socket error",
		},
		"should report failed domain when cert issuance fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "example.com", "example.com.pem").Return(errors.New("acme error"))
			},
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "example.com"},
			},
			ExpectedFailedDomains: []haproxysync.DomainSyncError{
				{Domain: "example.com", Error: "issue certificate: acme error"},
			},
		},
		"should report failed domain when reading certificate file fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "example.com", "example.com.pem").Return(nil)
			},
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "example.com"},
			},
			ExpectedFailedDomains: []haproxysync.DomainSyncError{
				{Domain: "example.com"},
			},
		},
		"should report failed domain when creating ssl cert storage fails": {
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
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "example.com"},
			},
			ExpectedFailedDomains: []haproxysync.DomainSyncError{
				{Domain: "example.com", Error: "create ssl cert storage: new cert error"},
			},
		},
		"should report failed domain when setting ssl cert content fails": {
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
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "example.com"},
			},
			ExpectedFailedDomains: []haproxysync.DomainSyncError{
				{Domain: "example.com", Error: "set ssl cert content: set cert error"},
			},
		},
		"should report failed domain when committing ssl cert fails": {
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
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "example.com"},
			},
			ExpectedFailedDomains: []haproxysync.DomainSyncError{
				{Domain: "example.com", Error: "commit ssl cert: commit error"},
			},
		},
		"should report failed domain when adding ssl crt-list fails": {
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
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "example.com"},
			},
			ExpectedFailedDomains: []haproxysync.DomainSyncError{
				{Domain: "example.com", Error: "add ssl crt-list: crt-list error"},
			},
		},
		"should report failed domain when adding domain to map fails": {
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
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "example.com"},
			},
			ExpectedFailedDomains: []haproxysync.DomainSyncError{
				{Domain: "example.com", Error: "add domain to map: add failed"},
			},
		},
		"should continue when one domain fails and succeed on others": {
			PrepareCerts: func(certsPath string) {
				require.NoError(os.WriteFile(filepath.Join(certsPath, "good.com.pem"), testPEMData, 0644))
			},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
				m.On("NewSslCert", filepath.Join(certsPath, "good.com.pem")).Return(nil)
				m.On("SetSslCert", filepath.Join(certsPath, "good.com.pem"), testPEMData).Return(nil)
				m.On("CommitSslCert", filepath.Join(certsPath, "good.com.pem")).Return(nil)
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "good.com.pem")).Return(nil)
				m.On("AddMap", "virt@domains", "good.com").Return(nil)
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "bad.com", "bad.com.pem").Return(errors.New("acme rate limit"))
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "good.com", "good.com.pem").Return(nil)
			},
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "bad.com"},
				{Name: "good.com"},
			},
			ExpectedResult: haproxysync.DomainSyncResult{
				DomainsAdded:   1,
				DomainsRemoved: 0,
				CertsIssued:    1,
				CertsRemoved:   0,
			},
			ExpectedFailedDomains: []haproxysync.DomainSyncError{
				{Domain: "bad.com", Error: "issue certificate: acme rate limit"},
			},
		},
		"should report all failures when all domains fail": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "fail1.com", "fail1.com.pem").Return(errors.New("error 1"))
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "fail2.com", "fail2.com.pem").Return(errors.New("error 2"))
			},
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "fail1.com"},
				{Name: "fail2.com"},
			},
			ExpectedResult: haproxysync.DomainSyncResult{
				DomainsAdded:   0,
				DomainsRemoved: 0,
				CertsIssued:    0,
				CertsRemoved:   0,
			},
			ExpectedFailedDomains: []haproxysync.DomainSyncError{
				{Domain: "fail1.com", Error: "issue certificate: error 1"},
				{Domain: "fail2.com", Error: "issue certificate: error 2"},
			},
		},
		"should return an error if deleting domain fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {
				m.On("ShowMap", "virt@domains").Return([]string{"old.com"}, nil)
				m.On("DelMap", "virt@domains", "old.com").Return(errors.New("delete failed"))
			},
			PrepareACME: func(m *acme.MockAcme) {},
			Domains:     []haproxysync.DomainSyncDomain{},
			ExpectedErr: "delete domain from HAProxy: delete failed",
		},
		"should return an error if deleting ssl crt-list fails": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{"old.com"}, nil)
				m.On("DelMap", "virt@domains", "old.com").Return(nil)
				m.On("DelSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "old.com.pem")).Return(errors.New("crt-list error"))
			},
			PrepareACME: func(m *acme.MockAcme) {},
			Domains:     []haproxysync.DomainSyncDomain{},
			ExpectedErr: "delete ssl crt-list for domain 'old.com': crt-list error",
		},
		"should refuse the deployment's own domain and keep syncing the rest": {
			PrepareCerts: func(certsPath string) {
				require.NoError(os.WriteFile(filepath.Join(certsPath, "example.com.pem"), testPEMData, 0644))
			},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
				m.On("NewSslCert", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("SetSslCert", filepath.Join(certsPath, "example.com.pem"), testPEMData).Return(nil)
				m.On("CommitSslCert", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("AddMap", "virt@domains", "example.com").Return(nil)
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "example.com", "example.com.pem").Return(nil)
			},
			Domains: []haproxysync.DomainSyncDomain{
				{Name: testBaseDomain},
				{Name: "example.com"},
			},
			ExpectedResult: haproxysync.DomainSyncResult{
				DomainsAdded:   1,
				DomainsRemoved: 0,
				CertsIssued:    1,
				CertsRemoved:   0,
			},
			ExpectedFailedDomains: []haproxysync.DomainSyncError{
				{Domain: testBaseDomain, Error: "deployment's own domain"},
			},
		},
		"should refuse the deployment's own domain whatever its case": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {
				m.On("ShowMap", "virt@domains").Return([]string{}, nil)
			},
			PrepareACME: func(m *acme.MockAcme) {},
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "PORTAL.Example.COM", Certificate: testPEMData},
			},
			ExpectedResult: haproxysync.DomainSyncResult{},
			ExpectedFailedDomains: []haproxysync.DomainSyncError{
				{Domain: "PORTAL.Example.COM", Error: "deployment's own domain"},
			},
		},
		"should drop a registered base domain without touching its ACME state": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{testBaseDomain}, nil)
				m.On("DelMap", "virt@domains", testBaseDomain).Return(nil)
				m.On("DelSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, testBaseDomain+".pem")).Return(nil)
				m.On("DelSslCert", filepath.Join(certsPath, testBaseDomain+".pem")).Return(nil)
			},
			PrepareACME: func(m *acme.MockAcme) {},
			Domains:     []haproxysync.DomainSyncDomain{},
			ExpectedResult: haproxysync.DomainSyncResult{
				DomainsAdded:   0,
				DomainsRemoved: 1,
				CertsIssued:    0,
				CertsRemoved:   0,
			},
		},
		"should still sync when dropping a registered base domain hits a leftover that is gone": {
			PrepareCerts: func(certsPath string) {
				require.NoError(os.WriteFile(filepath.Join(certsPath, "example.com.pem"), testPEMData, 0644))
			},
			PrepareHAProxy: func(m *haproxy.MockHaproxy, certsPath string) {
				m.On("ShowMap", "virt@domains").Return([]string{testBaseDomain}, nil)
				m.On("DelMap", "virt@domains", testBaseDomain).Return(errors.New("key not found"))
				m.On("DelSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, testBaseDomain+".pem")).
					Return(errors.New("entry not found"))
				m.On("DelSslCert", filepath.Join(certsPath, testBaseDomain+".pem")).
					Return(errors.New("certificate not found"))
				m.On("NewSslCert", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("SetSslCert", filepath.Join(certsPath, "example.com.pem"), testPEMData).Return(nil)
				m.On("CommitSslCert", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("AddSslCrtList", "/certs/crt-list.cfg", filepath.Join(certsPath, "example.com.pem")).Return(nil)
				m.On("AddMap", "virt@domains", "example.com").Return(nil)
			},
			PrepareACME: func(m *acme.MockAcme) {
				m.On("IssueCert", mock.AnythingOfType("*context.cancelCtx"), "example.com", "example.com.pem").Return(nil)
			},
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "example.com"},
			},
			ExpectedResult: haproxysync.DomainSyncResult{
				DomainsAdded:   1,
				DomainsRemoved: 1,
				CertsIssued:    1,
				CertsRemoved:   0,
			},
		},
		"should reject domain with path traversal": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {},
			PrepareACME:    func(m *acme.MockAcme) {},
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "../../../etc/passwd", Certificate: testPEMData},
			},
			ExpectedErr: "invalid domain name",
		},
		"should reject empty domain name": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {},
			PrepareACME:    func(m *acme.MockAcme) {},
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "", Certificate: testPEMData},
			},
			ExpectedErr: "invalid domain name",
		},
		"should reject overly long domain": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {},
			PrepareACME:    func(m *acme.MockAcme) {},
			Domains: []haproxysync.DomainSyncDomain{
				{Name: strings.Repeat("a", 254) + ".com", Certificate: testPEMData},
			},
			ExpectedErr: "invalid domain name",
		},
		"should reject domain with invalid characters": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {},
			PrepareACME:    func(m *acme.MockAcme) {},
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "bad space.example.com", Certificate: testPEMData},
			},
			ExpectedErr: "invalid domain name",
		},
		"should reject wildcard domain": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy, _ string) {},
			PrepareACME:    func(m *acme.MockAcme) {},
			Domains: []haproxysync.DomainSyncDomain{
				{Name: "*.example.com", Certificate: testPEMData},
			},
			ExpectedErr: "invalid domain name",
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
					BaseDomain:  testBaseDomain,
				},
			}

			svc := haproxysync.Init(log.New("test", "debug"), haproxyCfg, haproxyMock, acmeMock)

			result, err := svc.DomainSync(t.Context(), tc.Domains)

			if tc.ExpectedErr != "" {
				assert.ErrorContains(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.ExpectedFailedDomains != nil {
				require.Len(result.FailedDomains, len(tc.ExpectedFailedDomains))
				for i, expected := range tc.ExpectedFailedDomains {
					assert.Equal(expected.Domain, result.FailedDomains[i].Domain)
					if expected.Error != "" {
						assert.Contains(result.FailedDomains[i].Error, expected.Error)
					}
				}
			}

			// Compare result without FailedDomains (already checked above)
			result.FailedDomains = nil
			assert.Equal(tc.ExpectedResult, result)

			haproxyMock.AssertExpectations(t)
			acmeMock.AssertExpectations(t)
		})
	}
}

// newReissueService builds a service whose certs live in a temp dir, plus the
// two mocks, for the re-issue tests below.
func newReissueService(t *testing.T) (*haproxysync.HAproxySync, *haproxy.MockHaproxy, *acme.MockAcme, string) {
	t.Helper()

	certsPath := t.TempDir()
	haproxyMock := &haproxy.MockHaproxy{}
	acmeMock := &acme.MockAcme{}

	svc := haproxysync.Init(log.New("test", "debug"), cfg.HAProxy{
		Domains: cfg.HAProxyDomains{
			DomainsMap:  "virt@domains",
			CrtListPath: "/certs/crt-list.cfg",
			CertsPath:   certsPath,
		},
	}, haproxyMock, acmeMock)

	return svc, haproxyMock, acmeMock, certsPath
}

// TestDomainSyncReissueOnSourceChange pins that a domain already present in
// HAProxy is re-issued when its certificate source changes, instead of being
// skipped because its name is already in the map.
//
// Without this, the per-category branding UI that main already ships is a form
// that does nothing: switching a domain between an ACME certificate and an
// uploaded one is saved to the database, pushed to haproxy-sync, and silently
// ignored, because the only thing DomainSync ever looked at was whether the
// NAME was present.
//
// The re-issue happens in place: the certificate is swapped with SetSslCert +
// CommitSslCert and the domain is NOT re-added to the crt-list or the domain
// map, so the switch takes effect without a reload.
func TestDomainSyncReissueOnSourceChange(t *testing.T) {
	t.Parallel()

	require := require.New(t)
	assert := assert.New(t)

	svc, haproxyMock, acmeMock, certsPath := newReissueService(t)
	certFile := filepath.Join(certsPath, "branding.example.com.pem")
	customPEM := []byte("-----BEGIN CERTIFICATE-----\ncustom\n-----END CERTIFICATE-----\n")

	// Phase 1 adds the domain; the ACME issuance writes the file it then reads.
	haproxyMock.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
	haproxyMock.On("NewSslCert", certFile).Return(nil).Once()
	haproxyMock.On("AddSslCrtList", "/certs/crt-list.cfg", certFile).Return(nil).Once()
	haproxyMock.On("AddMap", "virt@domains", "branding.example.com").Return(nil).Once()
	acmeMock.On("IssueCert", mock.Anything, "branding.example.com", "branding.example.com.pem").
		Run(func(mock.Arguments) {
			require.NoError(os.WriteFile(certFile, testPEMData, 0644))
		}).Return(nil).Once()
	haproxyMock.On("SetSslCert", certFile, testPEMData).Return(nil).Once()
	haproxyMock.On("CommitSslCert", certFile).Return(nil).Once()

	res, err := svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{
		{Name: "branding.example.com"},
	})
	require.NoError(err)
	assert.Equal(1, res.DomainsAdded)
	assert.Equal(1, res.CertsIssued)

	// Phase 2: same name, now carrying an uploaded certificate.
	haproxyMock.On("ShowMap", "virt@domains").Return([]string{"branding.example.com"}, nil).Once()
	haproxyMock.On("SetSslCert", certFile, customPEM).Return(nil).Once()
	haproxyMock.On("CommitSslCert", certFile).Return(nil).Once()

	res, err = svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{
		{Name: "branding.example.com", Certificate: customPEM},
	})
	require.NoError(err)
	assert.Equal(0, res.DomainsAdded, "already present, must not be re-added")
	assert.Equal(0, res.CertsIssued, "an uploaded certificate is not an issuance")

	// Phase 3: back to ACME. The switch must be noticed in this direction too.
	haproxyMock.On("ShowMap", "virt@domains").Return([]string{"branding.example.com"}, nil).Once()
	acmeMock.On("IssueCert", mock.Anything, "branding.example.com", "branding.example.com.pem").
		Run(func(mock.Arguments) {
			require.NoError(os.WriteFile(certFile, testPEMData, 0644))
		}).Return(nil).Once()
	haproxyMock.On("SetSslCert", certFile, testPEMData).Return(nil).Once()
	haproxyMock.On("CommitSslCert", certFile).Return(nil).Once()

	res, err = svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{
		{Name: "branding.example.com"},
	})
	require.NoError(err)
	assert.Equal(0, res.DomainsAdded)
	assert.Equal(1, res.CertsIssued, "switching back to ACME re-issues")

	// Phase 4: nothing changed. A sync that re-issues on every pass would storm
	// the CA, so an unchanged spec must be a no-op.
	haproxyMock.On("ShowMap", "virt@domains").Return([]string{"branding.example.com"}, nil).Once()

	res, err = svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{
		{Name: "branding.example.com"},
	})
	require.NoError(err)
	assert.Equal(0, res.DomainsAdded)
	assert.Equal(0, res.CertsIssued, "an unchanged spec must not re-issue")

	haproxyMock.AssertExpectations(t)
	acmeMock.AssertExpectations(t)
	// NewSslCert / AddSslCrtList / AddMap were each declared .Once(): asserting
	// the expectations above proves the re-issues did not repeat them.
}

// TestDomainSyncAdoptsAlreadyServedDomain pins the startup path: the fingerprint
// cache lives in memory, so after a restart every already-served domain is
// unknown. Re-issuing them all on the first sync would hit the CA once per
// branding domain on every restart, so an unknown-but-present domain is adopted
// as-is instead.
func TestDomainSyncAdoptsAlreadyServedDomain(t *testing.T) {
	t.Parallel()

	require := require.New(t)
	assert := assert.New(t)

	svc, haproxyMock, acmeMock, _ := newReissueService(t)

	haproxyMock.On("ShowMap", "virt@domains").Return([]string{"served.example.com"}, nil).Once()

	res, err := svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{
		{Name: "served.example.com"},
	})
	require.NoError(err)
	assert.Equal(0, res.DomainsAdded)
	assert.Equal(0, res.CertsIssued, "adoption must not issue")

	// Adoption records the spec, so a later change is still caught.
	certFile := filepath.Join(svc.Domains.CertsPath, "served.example.com.pem")
	customPEM := []byte("-----BEGIN CERTIFICATE-----\nafter\n-----END CERTIFICATE-----\n")
	haproxyMock.On("ShowMap", "virt@domains").Return([]string{"served.example.com"}, nil).Once()
	haproxyMock.On("SetSslCert", certFile, customPEM).Return(nil).Once()
	haproxyMock.On("CommitSslCert", certFile).Return(nil).Once()

	res, err = svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{
		{Name: "served.example.com", Certificate: customPEM},
	})
	require.NoError(err)
	assert.Equal(0, res.DomainsAdded)

	haproxyMock.AssertExpectations(t)
	acmeMock.AssertExpectations(t)
}

// TestDomainSyncReAddsARemovedDomainInFull pins that a domain removed and then
// wanted again goes through the whole add path -- new cert storage, crt-list
// and map entry -- rather than being mistaken for one already in place.
//
// The companion assertion, that the remembered fingerprint is actually dropped,
// is in domain_internal_test.go: the map is unexported and this path overwrites
// the entry either way, so from out here the two are indistinguishable.
func TestDomainSyncReAddsARemovedDomainInFull(t *testing.T) {
	t.Parallel()

	require := require.New(t)
	assert := assert.New(t)

	svc, haproxyMock, acmeMock, certsPath := newReissueService(t)
	certFile := filepath.Join(certsPath, "gone.example.com.pem")

	// Present and remembered.
	haproxyMock.On("ShowMap", "virt@domains").Return([]string{"gone.example.com"}, nil).Once()
	_, err := svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{
		{Name: "gone.example.com"},
	})
	require.NoError(err)

	// Removed.
	haproxyMock.On("ShowMap", "virt@domains").Return([]string{"gone.example.com"}, nil).Once()
	haproxyMock.On("DelMap", "virt@domains", "gone.example.com").Return(nil).Once()
	haproxyMock.On("DelSslCrtList", "/certs/crt-list.cfg", certFile).Return(nil).Once()
	haproxyMock.On("DelSslCert", certFile).Return(nil).Once()
	acmeMock.On("RemoveCert", mock.Anything, "gone.example.com", "gone.example.com.pem").Return(nil).Once()

	res, err := svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{})
	require.NoError(err)
	assert.Equal(1, res.DomainsRemoved)

	// Re-added: a full add, not an adoption of a stale fingerprint.
	haproxyMock.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
	haproxyMock.On("NewSslCert", certFile).Return(nil).Once()
	haproxyMock.On("AddSslCrtList", "/certs/crt-list.cfg", certFile).Return(nil).Once()
	haproxyMock.On("AddMap", "virt@domains", "gone.example.com").Return(nil).Once()
	acmeMock.On("IssueCert", mock.Anything, "gone.example.com", "gone.example.com.pem").
		Run(func(mock.Arguments) {
			require.NoError(os.WriteFile(certFile, testPEMData, 0644))
		}).Return(nil).Once()
	haproxyMock.On("SetSslCert", certFile, testPEMData).Return(nil).Once()
	haproxyMock.On("CommitSslCert", certFile).Return(nil).Once()

	res, err = svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{
		{Name: "gone.example.com"},
	})
	require.NoError(err)
	assert.Equal(1, res.DomainsAdded)
	assert.Equal(1, res.CertsIssued)

	haproxyMock.AssertExpectations(t)
	acmeMock.AssertExpectations(t)
}

// TestDomainSyncReportsFailedReissue pins that a re-issue that fails is
// reported per-domain and does not abort the whole sync.
func TestDomainSyncReportsFailedReissue(t *testing.T) {
	t.Parallel()

	require := require.New(t)
	assert := assert.New(t)

	svc, haproxyMock, acmeMock, certsPath := newReissueService(t)
	certFile := filepath.Join(certsPath, "flaky.example.com.pem")

	haproxyMock.On("ShowMap", "virt@domains").Return([]string{"flaky.example.com"}, nil).Once()
	_, err := svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{
		{Name: "flaky.example.com"},
	})
	require.NoError(err)

	haproxyMock.On("ShowMap", "virt@domains").Return([]string{"flaky.example.com"}, nil).Once()
	haproxyMock.On("SetSslCert", certFile, mock.Anything).Return(errors.New("socket is gone")).Once()

	res, err := svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{
		{Name: "flaky.example.com", Certificate: testPEMData},
	})
	require.NoError(err, "a failed re-issue must not fail the whole sync")
	require.Len(res.FailedDomains, 1)
	assert.Equal("flaky.example.com", res.FailedDomains[0].Domain)
	assert.Contains(res.FailedDomains[0].Error, "socket is gone")

	// The failed fingerprint must not be recorded, or the next sync would think
	// the domain is already up to date and never retry.
	haproxyMock.On("ShowMap", "virt@domains").Return([]string{"flaky.example.com"}, nil).Once()
	haproxyMock.On("SetSslCert", certFile, testPEMData).Return(nil).Once()
	haproxyMock.On("CommitSslCert", certFile).Return(nil).Once()

	res, err = svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{
		{Name: "flaky.example.com", Certificate: testPEMData},
	})
	require.NoError(err)
	assert.Empty(res.FailedDomains, "the retry must succeed")

	haproxyMock.AssertExpectations(t)
	acmeMock.AssertExpectations(t)
}
