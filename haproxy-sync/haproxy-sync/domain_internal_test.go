package haproxysync

import (
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
