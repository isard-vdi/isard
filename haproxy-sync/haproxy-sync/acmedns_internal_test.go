package haproxysync

import (
	"errors"
	"os"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"

	"gitlab.com/isard/isardvdi/haproxy-sync/acme"
	"gitlab.com/isard/isardvdi/haproxy-sync/cfg"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy"
	"gitlab.com/isard/isardvdi/pkg/log"
)

// The fingerprint decides whether a domain HAProxy is already serving gets its
// certificate re-issued. Two questions matter here and they pull in opposite
// directions.
//
// Changing how a domain is certified MUST re-issue. An operator moving a
// domain from HTTP-01 to acme-dns is almost always doing it because HTTP-01
// cannot work for that name, so there is no usable certificate to keep; if the
// fingerprint did not move, the domain would go on being served by whatever is
// on disk and the change would appear to do nothing.
//
// Rotating the password MUST NOT re-issue. The password authenticates us to
// acme-dns; it says nothing about what certificate the domain is asking for.
// Re-issuing on a credential rotation spends certificate-authority rate limit
// for a certificate identical to the one already installed, and rate limit is
// the resource that runs out quietly and takes a week to come back.
//
// So the fingerprint covers which acme-dns account answers the challenge --
// server, user and subdomain -- and not the secret used to reach it. That also
// keeps a hash of the password from sitting in process memory keyed by domain,
// which is what the reference implementation did.

func testDNSDomain() DomainSyncDomain {
	return DomainSyncDomain{
		Name:             "vdi.example.com",
		ACMEDNSBaseURL:   "https://auth.example.com",
		ACMEDNSUsername:  "eabcdb41-d89f-4580-826f-3e62e9755ef2",
		ACMEDNSPassword:  "not-a-real-password-for-tests-0123456789",
		ACMEDNSSubdomain: "d420c923-bbd7-4056-ab64-c3ca54c9b3cf",
	}
}

func TestFingerprintDistinguishesTheChallenge(t *testing.T) {
	t.Parallel()

	http01 := domainFingerprint(DomainSyncDomain{Name: "vdi.example.com"})
	dns01 := domainFingerprint(testDNSDomain())

	assert.NotEqual(t, http01, dns01,
		"moving a domain to acme-dns must re-issue: HTTP-01 could not certify it")
}

func TestFingerprintIgnoresThePassword(t *testing.T) {
	t.Parallel()

	before := domainFingerprint(testDNSDomain())

	rotated := testDNSDomain()
	rotated.ACMEDNSPassword = "a-completely-different-password-value-42"

	assert.Equal(t, before, domainFingerprint(rotated),
		"a rotated password is the same certificate; re-issuing spends rate limit for nothing")
}

func TestFingerprintFollowsTheAccount(t *testing.T) {
	t.Parallel()

	base := domainFingerprint(testDNSDomain())

	for _, tc := range []struct {
		name   string
		change func(*DomainSyncDomain)
	}{
		{"a different acme-dns server", func(d *DomainSyncDomain) { d.ACMEDNSBaseURL = "https://other.example.com" }},
		{"a different account", func(d *DomainSyncDomain) { d.ACMEDNSUsername = "00000000-0000-0000-0000-000000000000" }},
		{"a different subdomain", func(d *DomainSyncDomain) { d.ACMEDNSSubdomain = "ffffffff-ffff-ffff-ffff-ffffffffffff" }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			d := testDNSDomain()
			tc.change(&d)
			assert.NotEqual(t, base, domainFingerprint(d),
				"the challenge is answered somewhere else now, so the delegation may not reach it")
		})
	}
}

func TestAnUploadedCertificateStillWins(t *testing.T) {
	t.Parallel()

	// An operator who uploads a PEM has said what they want served. Issuing
	// over acme-dns instead would replace it behind their back.
	d := testDNSDomain()
	d.Certificate = []byte("-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----\n")

	assert.Contains(t, domainFingerprint(d), "custom:")
}

func TestIsACMEDNSNeedsAllFour(t *testing.T) {
	t.Parallel()

	assert.True(t, testDNSDomain().IsACMEDNS())
	assert.False(t, DomainSyncDomain{Name: "vdi.example.com"}.IsACMEDNS())

	for _, tc := range []struct {
		name  string
		blank func(*DomainSyncDomain)
	}{
		{"base url", func(d *DomainSyncDomain) { d.ACMEDNSBaseURL = "" }},
		{"username", func(d *DomainSyncDomain) { d.ACMEDNSUsername = "" }},
		{"password", func(d *DomainSyncDomain) { d.ACMEDNSPassword = "" }},
		{"subdomain", func(d *DomainSyncDomain) { d.ACMEDNSSubdomain = "" }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			d := testDNSDomain()
			tc.blank(&d)
			assert.False(t, d.IsACMEDNS())
		})
	}
}

func TestPartialCredentialsAreNotHTTP01(t *testing.T) {
	t.Parallel()

	// Three of four is not "no acme-dns configured", it is a configuration
	// that cannot work. Falling back to HTTP-01 there would attempt the one
	// challenge the operator moved away from, and report its failure -- which
	// says nothing about the credential they got wrong.
	d := testDNSDomain()
	d.ACMEDNSSubdomain = ""

	assert.False(t, d.IsACMEDNS())
	assert.True(t, d.hasPartialACMEDNS())

	assert.False(t, DomainSyncDomain{Name: "vdi.example.com"}.hasPartialACMEDNS(),
		"nothing set at all is a plain HTTP-01 domain, not a broken acme-dns one")
	assert.False(t, testDNSDomain().hasPartialACMEDNS())
}

func TestACMEDNSCredentialsAreCarriedThrough(t *testing.T) {
	t.Parallel()

	// The password does not appear in the fingerprint, so this is the only
	// place that pins it reaching the issuance layer at all.
	d := testDNSDomain()
	creds := d.acmeDNSCredentials()

	assert.Equal(t, acme.ACMEDNSCredentials{
		BaseURL:   "https://auth.example.com",
		Username:  "eabcdb41-d89f-4580-826f-3e62e9755ef2",
		Password:  "not-a-real-password-for-tests-0123456789",
		Subdomain: "d420c923-bbd7-4056-ab64-c3ca54c9b3cf",
	}, creds)
	assert.True(t, creds.Complete())
}

// ── Which issuance actually runs ─────────────────────────────────────────

func newTestSync(t *testing.T) (*HAproxySync, *acme.MockAcme, string) {
	t.Helper()

	certsPath := t.TempDir()
	acmeMock := &acme.MockAcme{}
	svc := Init(log.New("test", "debug"), cfg.HAProxy{
		Domains: cfg.HAProxyDomains{
			DomainsMap:  "virt@domains",
			CrtListPath: "/certs/crt-list.cfg",
			CertsPath:   certsPath,
		},
	}, &haproxy.MockHaproxy{}, acmeMock)

	return svc, acmeMock, certsPath
}

func TestMaterializeUsesDNS01WhenTheCredentialsAreThere(t *testing.T) {
	t.Parallel()

	svc, acmeMock, certsPath := newTestSync(t)
	d := testDNSDomain()
	pemName := domainPemName(d.Name)

	acmeMock.On("IssueCertDNS", mock.Anything, d.Name, pemName, d.acmeDNSCredentials()).
		Run(func(args mock.Arguments) {
			require.NoError(t, os.WriteFile(domainCertPath(certsPath, pemName), testPEMData, 0600))
		}).Return(nil).Once()

	pem, err := svc.materializeCert(t.Context(), d)
	require.NoError(t, err)
	assert.Equal(t, testPEMData, pem)

	acmeMock.AssertExpectations(t)
	acmeMock.AssertNotCalled(t, "IssueCert", mock.Anything, mock.Anything, mock.Anything)
}

func TestMaterializeStillUsesHTTP01WithoutCredentials(t *testing.T) {
	t.Parallel()

	svc, acmeMock, certsPath := newTestSync(t)
	d := DomainSyncDomain{Name: "plain.example.com"}
	pemName := domainPemName(d.Name)

	acmeMock.On("IssueCert", mock.Anything, d.Name, pemName).
		Run(func(args mock.Arguments) {
			require.NoError(t, os.WriteFile(domainCertPath(certsPath, pemName), testPEMData, 0600))
		}).Return(nil).Once()

	_, err := svc.materializeCert(t.Context(), d)
	require.NoError(t, err)

	acmeMock.AssertExpectations(t)
	acmeMock.AssertNotCalled(t, "IssueCertDNS", mock.Anything, mock.Anything, mock.Anything, mock.Anything)
}

func TestMaterializeRefusesPartialCredentials(t *testing.T) {
	t.Parallel()

	// Neither issuance runs. Attempting HTTP-01 would report the failure of a
	// challenge the operator deliberately moved away from, and attempting
	// DNS-01 would report one about DNS resolution -- both of them describing
	// something other than the field that is actually missing.
	svc, acmeMock, _ := newTestSync(t)
	d := testDNSDomain()
	d.ACMEDNSUsername = ""

	_, err := svc.materializeCert(t.Context(), d)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "acme-dns")

	acmeMock.AssertNotCalled(t, "IssueCert", mock.Anything, mock.Anything, mock.Anything)
	acmeMock.AssertNotCalled(t, "IssueCertDNS", mock.Anything, mock.Anything, mock.Anything, mock.Anything)
}

func TestMaterializeDoesNotLeakThePasswordInItsError(t *testing.T) {
	t.Parallel()

	svc, acmeMock, _ := newTestSync(t)
	d := testDNSDomain()

	acmeMock.On("IssueCertDNS", mock.Anything, d.Name, domainPemName(d.Name), d.acmeDNSCredentials()).
		Return(errors.New("issue ACME DNS-01 certificate: exit status 1")).Once()

	_, err := svc.materializeCert(t.Context(), d)
	require.Error(t, err)
	assert.NotContains(t, err.Error(), d.ACMEDNSPassword,
		"this error becomes a failed_domains entry and an apiv4 log line")
}

// ── The main domain ──────────────────────────────────────────────────────

func newMainDomainSync(t *testing.T) (*HAproxySync, *acme.MockAcme, *haproxy.MockHaproxy, string) {
	t.Helper()

	certsPath := t.TempDir()
	acmeMock := &acme.MockAcme{}
	haproxyMock := &haproxy.MockHaproxy{}
	svc := Init(log.New("test", "debug"), cfg.HAProxy{
		Domains: cfg.HAProxyDomains{
			DomainsMap:  "virt@domains",
			CrtListPath: "/certs/crt-list.cfg",
			CertsPath:   certsPath,
		},
	}, haproxyMock, acmeMock)

	return svc, acmeMock, haproxyMock, certsPath
}

func testDNSCreds() acme.ACMEDNSCredentials {
	return testDNSDomain().acmeDNSCredentials()
}

func TestIssueMainDomainDNSUsesTheDNSIssuance(t *testing.T) {
	t.Parallel()

	svc, acmeMock, _, _ := newMainDomainSync(t)
	acmeMock.On("IssueMainDomainDNS", mock.Anything, []string{"vdi.example.com"},
		mainDomainPemName, acme.ACMEAccount{Server: "letsencrypt"}, testDNSCreds()).Return(nil).Once()

	require.NoError(t, svc.IssueMainDomainDNS(t.Context(), []string{"vdi.example.com"},
		acme.ACMEAccount{Server: "letsencrypt"}, testDNSCreds()))

	acmeMock.AssertExpectations(t)
	acmeMock.AssertNotCalled(t, "IssueMainDomain", mock.Anything, mock.Anything, mock.Anything, mock.Anything)
}

func TestIssueMainDomainDNSDoesNotPushTheThumbprint(t *testing.T) {
	t.Parallel()

	// The thumbprint is what HAProxy answers a stateless HTTP-01 challenge
	// from. A DNS-01 challenge is answered by acme-dns and never reaches
	// HAProxy, so pushing it here would be a write to the running proxy that
	// nothing in this flow needs.
	svc, acmeMock, haproxyMock, certsPath := newMainDomainSync(t)
	require.NoError(t, os.WriteFile(
		domainCertPath(certsPath, "account-thumbprint"), []byte("a-thumbprint"), 0600))
	svc.Domains.accountThumbprintPath = domainCertPath(certsPath, "account-thumbprint")

	acmeMock.On("IssueMainDomainDNS", mock.Anything, mock.Anything, mock.Anything,
		mock.Anything, mock.Anything).Return(nil).Once()

	require.NoError(t, svc.IssueMainDomainDNS(t.Context(), []string{"vdi.example.com"},
		acme.ACMEAccount{}, testDNSCreds()))

	haproxyMock.AssertNotCalled(t, "SetProcVar", mock.Anything, mock.Anything)
}

func TestIssueMainDomainDNSStillRefusesAShadowedCertificate(t *testing.T) {
	t.Parallel()

	// The same trap as the HTTP-01 path: while the operator-supplied PEM
	// exists it wins in the crt-list, so anything issued here is written,
	// logged as successful and never served. The challenge used to obtain it
	// makes no difference to that.
	svc, acmeMock, _, certsPath := newMainDomainSync(t)
	require.NoError(t, os.WriteFile(
		domainCertPath(certsPath, customPortalPemName), testPEMData, 0600))

	err := svc.IssueMainDomainDNS(t.Context(), []string{"vdi.example.com"},
		acme.ACMEAccount{}, testDNSCreds())

	require.Error(t, err)
	assert.Contains(t, err.Error(), customPortalPemName)
	acmeMock.AssertNotCalled(t, "IssueMainDomainDNS", mock.Anything, mock.Anything,
		mock.Anything, mock.Anything, mock.Anything)
}

func TestIssueMainDomainDNSValidatesTheNames(t *testing.T) {
	t.Parallel()

	svc, acmeMock, _, _ := newMainDomainSync(t)

	err := svc.IssueMainDomainDNS(t.Context(), []string{"*.example.com"},
		acme.ACMEAccount{}, testDNSCreds())

	require.Error(t, err)
	assert.ErrorIs(t, err, ErrInvalidDomain)
	acmeMock.AssertNotCalled(t, "IssueMainDomainDNS", mock.Anything, mock.Anything,
		mock.Anything, mock.Anything, mock.Anything)
}

func TestIssueMainDomainDNSRefusesNoNames(t *testing.T) {
	t.Parallel()

	svc, _, _, _ := newMainDomainSync(t)

	err := svc.IssueMainDomainDNS(t.Context(), nil, acme.ACMEAccount{}, testDNSCreds())
	assert.ErrorIs(t, err, ErrInvalidDomain)
}

func TestIssueMainDomainDNSRefusesIncompleteCredentials(t *testing.T) {
	t.Parallel()

	svc, acmeMock, _, _ := newMainDomainSync(t)
	creds := testDNSCreds()
	creds.Subdomain = ""

	err := svc.IssueMainDomainDNS(t.Context(), []string{"vdi.example.com"},
		acme.ACMEAccount{}, creds)

	require.Error(t, err)
	assert.Contains(t, err.Error(), "acme-dns")
	acmeMock.AssertNotCalled(t, "IssueMainDomainDNS", mock.Anything, mock.Anything,
		mock.Anything, mock.Anything, mock.Anything)
}

func TestIssueMainDomainDNSDoesNotLeakThePassword(t *testing.T) {
	t.Parallel()

	svc, acmeMock, _, _ := newMainDomainSync(t)
	acmeMock.On("IssueMainDomainDNS", mock.Anything, mock.Anything, mock.Anything,
		mock.Anything, mock.Anything).Return(errors.New("exit status 1")).Once()

	err := svc.IssueMainDomainDNS(t.Context(), []string{"vdi.example.com"},
		acme.ACMEAccount{}, testDNSCreds())

	require.Error(t, err)
	assert.NotContains(t, err.Error(), testDNSCreds().Password)
}
