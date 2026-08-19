package haproxysync

import (
	"errors"
	"os"
	"path/filepath"
	"testing"

	"gitlab.com/isard/isardvdi/haproxy-sync/acme"
	"gitlab.com/isard/isardvdi/haproxy-sync/cfg"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
)

func TestIsBaseDomain(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		BaseDomain string
		Domain     string
		Expected   bool
	}{
		"should match the deployment's own domain": {
			BaseDomain: "portal.example.com",
			Domain:     "portal.example.com",
			Expected:   true,
		},
		"should match whatever the case, as dns names are case insensitive": {
			BaseDomain: "portal.example.com",
			Domain:     "PORTAL.Example.COM",
			Expected:   true,
		},
		"should not match a different domain": {
			BaseDomain: "portal.example.com",
			Domain:     "aula.example.com",
			Expected:   false,
		},
		"should not match anything if the deployment has no domain": {
			BaseDomain: "",
			Domain:     "portal.example.com",
			Expected:   false,
		},
		"should not match an empty domain against an empty base domain": {
			BaseDomain: "",
			Domain:     "",
			Expected:   false,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			h := &HAproxySync{
				Domains: &HAProxySyncDomains{
					BaseDomain: tc.BaseDomain,
				},
			}

			assert.Equal(tc.Expected, h.isBaseDomain(tc.Domain))
		})
	}
}

// TestSpecsAreForgottenOnRemoval pins that removing a domain also drops the
// fingerprint remembered for it, so the map does not grow without bound across
// add/remove cycles for the lifetime of the process.
//
// This lives in an internal test because the map is unexported and, from
// outside, the leak is invisible: re-adding a domain overwrites its entry
// anyway, so a black-box test passes whether or not the removal cleans up.
// testPEMData in domain_test.go belongs to the external test package, so the
// internal suite carries its own copy.
var testPEMData = []byte("-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----\n")

func TestSpecsAreForgottenOnRemoval(t *testing.T) {
	t.Parallel()

	require := require.New(t)
	assert := assert.New(t)

	certsPath := t.TempDir()
	haproxyMock := &haproxy.MockHaproxy{}
	acmeMock := &acme.MockAcme{}

	svc := Init(log.New("test", "debug"), cfg.HAProxy{
		Domains: cfg.HAProxyDomains{
			DomainsMap:  "virt@domains",
			CrtListPath: "/certs/crt-list.cfg",
			CertsPath:   certsPath,
		},
	}, haproxyMock, acmeMock)

	// Adopt an already-served domain: that records its fingerprint.
	haproxyMock.On("ShowMap", "virt@domains").Return([]string{"gone.example.com"}, nil).Once()
	_, err := svc.DomainSync(t.Context(), []DomainSyncDomain{{Name: "gone.example.com"}})
	require.NoError(err)
	require.Contains(svc.Domains.specs, "gone.example.com", "adoption must record the spec")

	// Drop it from the desired set.
	haproxyMock.On("ShowMap", "virt@domains").Return([]string{"gone.example.com"}, nil).Once()
	haproxyMock.On("DelMap", "virt@domains", "gone.example.com").Return(nil).Once()
	haproxyMock.On("DelSslCrtList", "/certs/crt-list.cfg", mock.Anything).Return(nil).Once()
	haproxyMock.On("DelSslCert", mock.Anything).Return(nil).Once()
	acmeMock.On("RemoveCert", mock.Anything, "gone.example.com", "gone.example.com.pem").Return(nil).Once()

	_, err = svc.DomainSync(t.Context(), []DomainSyncDomain{})
	require.NoError(err)

	assert.NotContains(svc.Domains.specs, "gone.example.com",
		"the removed domain must not keep a remembered fingerprint")
	assert.Empty(svc.Domains.specs)

	haproxyMock.AssertExpectations(t)
	acmeMock.AssertExpectations(t)
}

// TestThumbprintIsPushedBeforeEveryAcmeIssuance pins how the HTTP-01 account
// thumbprint reaches a RUNNING HAProxy.
//
// HAProxy reads the value into a process variable from the environment, and the
// environment is read at parse time. A reload re-reads the configuration and
// therefore resets the variable to whatever the environment said when the
// container started -- which, on an install that had no ACME account then, is
// the empty string. Registering an account later would leave HAProxy serving an
// empty thumbprint and every challenge failing, with nothing in any log saying
// so.
//
// Pushing the value before each issuance is what makes that self-correcting:
// whatever happened in between, including a reload, the responder is put back in
// step with the account file immediately before the certificate authority is
// asked to validate.
func TestThumbprintIsPushedBeforeEveryAcmeIssuance(t *testing.T) {
	t.Parallel()

	require := require.New(t)
	assert := assert.New(t)

	certsPath := t.TempDir()
	thumbprint := filepath.Join(t.TempDir(), "account-thumbprint")
	require.NoError(os.WriteFile(thumbprint, []byte("TESTthumbprint_-123\n"), 0644))

	haproxyMock := &haproxy.MockHaproxy{}
	acmeMock := &acme.MockAcme{}
	svc := Init(log.New("test", "debug"), cfg.HAProxy{
		Domains: cfg.HAProxyDomains{
			DomainsMap:  "virt@domains",
			CrtListPath: "/certs/crt-list.cfg",
			CertsPath:   certsPath,
		},
	}, haproxyMock, acmeMock)
	svc.Domains.accountThumbprintPath = thumbprint

	certFile := filepath.Join(certsPath, "a.example.com.pem")

	// The trailing newline of the file must not reach HAProxy.
	haproxyMock.On("SetProcVar", "proc.acme_thumbprint", "TESTthumbprint_-123").
		Return(nil).Times(2)

	haproxyMock.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
	haproxyMock.On("NewSslCert", certFile).Return(nil).Once()
	haproxyMock.On("AddSslCrtList", "/certs/crt-list.cfg", certFile).Return(nil).Once()
	haproxyMock.On("AddMap", "virt@domains", "a.example.com").Return(nil).Once()
	// add + two re-issues
	haproxyMock.On("SetSslCert", certFile, testPEMData).Return(nil).Times(3)
	haproxyMock.On("CommitSslCert", certFile).Return(nil).Times(3)
	acmeMock.On("IssueCert", mock.Anything, "a.example.com", "a.example.com.pem").
		Run(func(mock.Arguments) {
			require.NoError(os.WriteFile(certFile, testPEMData, 0644))
		}).Return(nil).Times(2)

	_, err := svc.DomainSync(t.Context(), []DomainSyncDomain{{Name: "a.example.com"}})
	require.NoError(err)

	// Second pass: the domain is present but its source changed, so it is
	// re-issued -- and the thumbprint must be pushed again, because a reload
	// could have reset it since.
	haproxyMock.On("ShowMap", "virt@domains").Return([]string{"a.example.com"}, nil).Once()
	_, err = svc.DomainSync(t.Context(), []DomainSyncDomain{
		{Name: "a.example.com", Certificate: testPEMData},
	})
	require.NoError(err)
	haproxyMock.On("ShowMap", "virt@domains").Return([]string{"a.example.com"}, nil).Once()
	_, err = svc.DomainSync(t.Context(), []DomainSyncDomain{{Name: "a.example.com"}})
	require.NoError(err)

	haproxyMock.AssertExpectations(t)
	acmeMock.AssertExpectations(t)
	assert.Equal(2, countCalls(haproxyMock, "SetProcVar"),
		"pushed once per ACME issuance, never batched or cached")
}

// TestThumbprintIsNotPushedForAnUploadedCertificate: the value only answers
// HTTP-01 challenges, so materializing a certificate the operator supplied has
// no reason to touch it.
func TestThumbprintIsNotPushedForAnUploadedCertificate(t *testing.T) {
	t.Parallel()

	require := require.New(t)

	certsPath := t.TempDir()
	thumbprint := filepath.Join(t.TempDir(), "account-thumbprint")
	require.NoError(os.WriteFile(thumbprint, []byte("TESTthumbprint\n"), 0644))

	haproxyMock := &haproxy.MockHaproxy{}
	acmeMock := &acme.MockAcme{}
	svc := Init(log.New("test", "debug"), cfg.HAProxy{
		Domains: cfg.HAProxyDomains{
			DomainsMap:  "virt@domains",
			CrtListPath: "/certs/crt-list.cfg",
			CertsPath:   certsPath,
		},
	}, haproxyMock, acmeMock)
	svc.Domains.accountThumbprintPath = thumbprint

	certFile := filepath.Join(certsPath, "custom.example.com.pem")
	haproxyMock.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
	haproxyMock.On("NewSslCert", certFile).Return(nil).Once()
	haproxyMock.On("SetSslCert", certFile, testPEMData).Return(nil).Once()
	haproxyMock.On("CommitSslCert", certFile).Return(nil).Once()
	haproxyMock.On("AddSslCrtList", "/certs/crt-list.cfg", certFile).Return(nil).Once()
	haproxyMock.On("AddMap", "virt@domains", "custom.example.com").Return(nil).Once()

	_, err := svc.DomainSync(t.Context(), []DomainSyncDomain{
		{Name: "custom.example.com", Certificate: testPEMData},
	})
	require.NoError(err)

	haproxyMock.AssertExpectations(t)
	require.Equal(0, countCalls(haproxyMock, "SetProcVar"))
}

// TestThumbprintProblemsDoNotStopIssuance: no account file yet, or a socket
// that refuses the push, must not turn into a failed certificate. The issuance
// may well still succeed, and refusing to try guarantees it cannot.
func TestThumbprintProblemsDoNotStopIssuance(t *testing.T) {
	t.Parallel()

	cases := map[string]struct {
		writeFile bool
		pushErr   error
	}{
		"no account file": {writeFile: false},
		"push is refused": {writeFile: true, pushErr: errors.New("socket says no")},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			require := require.New(t)

			certsPath := t.TempDir()
			thumbprint := filepath.Join(t.TempDir(), "account-thumbprint")
			if tc.writeFile {
				require.NoError(os.WriteFile(thumbprint, []byte("abc"), 0644))
			}

			haproxyMock := &haproxy.MockHaproxy{}
			acmeMock := &acme.MockAcme{}
			svc := Init(log.New("test", "debug"), cfg.HAProxy{
				Domains: cfg.HAProxyDomains{
					DomainsMap:  "virt@domains",
					CrtListPath: "/certs/crt-list.cfg",
					CertsPath:   certsPath,
				},
			}, haproxyMock, acmeMock)
			svc.Domains.accountThumbprintPath = thumbprint

			certFile := filepath.Join(certsPath, "a.example.com.pem")
			if tc.writeFile {
				haproxyMock.On("SetProcVar", "proc.acme_thumbprint", "abc").
					Return(tc.pushErr).Once()
			}
			haproxyMock.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
			haproxyMock.On("NewSslCert", certFile).Return(nil).Once()
			haproxyMock.On("SetSslCert", certFile, testPEMData).Return(nil).Once()
			haproxyMock.On("CommitSslCert", certFile).Return(nil).Once()
			haproxyMock.On("AddSslCrtList", "/certs/crt-list.cfg", certFile).Return(nil).Once()
			haproxyMock.On("AddMap", "virt@domains", "a.example.com").Return(nil).Once()
			acmeMock.On("IssueCert", mock.Anything, "a.example.com", "a.example.com.pem").
				Run(func(mock.Arguments) {
					require.NoError(os.WriteFile(certFile, testPEMData, 0644))
				}).Return(nil).Once()

			res, err := svc.DomainSync(t.Context(), []DomainSyncDomain{{Name: "a.example.com"}})
			require.NoError(err)
			require.Equal(1, res.DomainsAdded)
			require.Empty(res.FailedDomains)

			haproxyMock.AssertExpectations(t)
			acmeMock.AssertExpectations(t)
		})
	}
}

func countCalls(m *haproxy.MockHaproxy, method string) int {
	n := 0
	for _, c := range m.Calls {
		if c.Method == method {
			n++
		}
	}
	return n
}
