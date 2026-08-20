package grpc_test

import (
	"context"
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"

	"gitlab.com/isard/isardvdi/haproxy-sync/acme"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy-sync"
	"gitlab.com/isard/isardvdi/haproxy-sync/transport/grpc"
	"gitlab.com/isard/isardvdi/pkg/cfg"
	haproxysyncv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/haproxy_sync/v1"
	"gitlab.com/isard/isardvdi/pkg/log"
)

// A field wired to the wrong getter does not fail: it succeeds with the values
// shifted, and the deployment tries to authenticate to acme-dns with the
// subdomain as its password. The failure surfaces as a rejected acme-dns
// update, which reads like a credential the operator typed wrong rather than
// like a bug on this side.
//
// Four distinct values, so a swap between any two of them is visible. Reusing
// one string across fields would let a transposition pass.
func TestDomainSyncCarriesTheACMEDNSCredentials(t *testing.T) {
	t.Parallel()

	serviceMock := &haproxysync.MockHaproxysync{}
	serviceMock.On("DomainSync", mock.AnythingOfType("context.backgroundCtx"), []haproxysync.DomainSyncDomain{
		{
			Name:             "branding.example.com",
			ACMEDNSBaseURL:   "https://auth.example.com",
			ACMEDNSUsername:  "the-username",
			ACMEDNSPassword:  "the-password",
			ACMEDNSSubdomain: "the-subdomain",
		},
	}).Return(haproxysync.DomainSyncResult{DomainsAdded: 1}, nil)

	srv := grpc.NewHAProxySyncServer(log.New("test", "debug"), nil, cfg.GRPC{}, serviceMock)

	_, err := srv.DomainSync(context.Background(), &haproxysyncv1.DomainSyncRequest{
		Domains: []*haproxysyncv1.DomainSyncDomain{
			{
				Name:             "branding.example.com",
				AcmeDnsBaseUrl:   "https://auth.example.com",
				AcmeDnsUsername:  "the-username",
				AcmeDnsPassword:  "the-password",
				AcmeDnsSubdomain: "the-subdomain",
			},
		},
	})

	assert.NoError(t, err)
	serviceMock.AssertExpectations(t)
}

// A domain with no acme-dns fields must arrive with them empty rather than
// with anything invented, or every HTTP-01 domain would look like a broken
// acme-dns one to the layer below.
func TestDomainSyncLeavesTheCredentialsEmptyWhenAbsent(t *testing.T) {
	t.Parallel()

	serviceMock := &haproxysync.MockHaproxysync{}
	serviceMock.On("DomainSync", mock.AnythingOfType("context.backgroundCtx"), []haproxysync.DomainSyncDomain{
		{Name: "plain.example.com"},
	}).Return(haproxysync.DomainSyncResult{DomainsAdded: 1}, nil)

	srv := grpc.NewHAProxySyncServer(log.New("test", "debug"), nil, cfg.GRPC{}, serviceMock)

	_, err := srv.DomainSync(context.Background(), &haproxysyncv1.DomainSyncRequest{
		Domains: []*haproxysyncv1.DomainSyncDomain{{Name: "plain.example.com"}},
	})

	assert.NoError(t, err)
	serviceMock.AssertExpectations(t)
}

// Which challenge the main domain uses is decided by what the request carries.
// A deployment that has never configured acme-dns must keep taking exactly the
// path it took before, so this pins both directions rather than only the new
// one.
func TestIssueMainDomainUsesDNS01WhenCredentialsAreSent(t *testing.T) {
	t.Parallel()

	serviceMock := &haproxysync.MockHaproxysync{}
	serviceMock.On("IssueMainDomainDNS", mock.AnythingOfType("context.backgroundCtx"),
		[]string{"vdi.example.com"},
		acme.ACMEAccount{Server: "letsencrypt", Email: "admin@example.com"},
		acme.ACMEDNSCredentials{
			BaseURL:   "https://auth.example.com",
			Username:  "the-username",
			Password:  "the-password",
			Subdomain: "the-subdomain",
		}).Return(nil)

	srv := grpc.NewHAProxySyncServer(log.New("test", "debug"), nil, cfg.GRPC{}, serviceMock)

	_, err := srv.IssueMainDomain(context.Background(), &haproxysyncv1.IssueMainDomainRequest{
		Names:            []string{"vdi.example.com"},
		AcmeServer:       "letsencrypt",
		AcmeEmail:        "admin@example.com",
		AcmeDnsBaseUrl:   "https://auth.example.com",
		AcmeDnsUsername:  "the-username",
		AcmeDnsPassword:  "the-password",
		AcmeDnsSubdomain: "the-subdomain",
	})

	assert.NoError(t, err)
	serviceMock.AssertExpectations(t)
	serviceMock.AssertNotCalled(t, "IssueMainDomain", mock.Anything, mock.Anything, mock.Anything)
}

func TestIssueMainDomainStaysOnHTTP01WithoutCredentials(t *testing.T) {
	t.Parallel()

	serviceMock := &haproxysync.MockHaproxysync{}
	serviceMock.On("IssueMainDomain", mock.AnythingOfType("context.backgroundCtx"),
		[]string{"vdi.example.com"},
		acme.ACMEAccount{Server: "letsencrypt"}).Return(nil)

	srv := grpc.NewHAProxySyncServer(log.New("test", "debug"), nil, cfg.GRPC{}, serviceMock)

	_, err := srv.IssueMainDomain(context.Background(), &haproxysyncv1.IssueMainDomainRequest{
		Names:      []string{"vdi.example.com"},
		AcmeServer: "letsencrypt",
	})

	assert.NoError(t, err)
	serviceMock.AssertExpectations(t)
	serviceMock.AssertNotCalled(t, "IssueMainDomainDNS", mock.Anything, mock.Anything,
		mock.Anything, mock.Anything)
}

// Three of four goes to the DNS-01 path so the operator gets a message naming
// what is missing. Routing it to HTTP-01 instead would attempt the challenge
// they moved away from and report its failure, which says nothing about the
// field they left blank.
func TestIssueMainDomainSendsPartialCredentialsToTheDNSPath(t *testing.T) {
	t.Parallel()

	serviceMock := &haproxysync.MockHaproxysync{}
	serviceMock.On("IssueMainDomainDNS", mock.AnythingOfType("context.backgroundCtx"),
		[]string{"vdi.example.com"}, acme.ACMEAccount{},
		acme.ACMEDNSCredentials{BaseURL: "https://auth.example.com"}).
		Return(errors.New("incomplete acme-dns credentials"))

	srv := grpc.NewHAProxySyncServer(log.New("test", "debug"), nil, cfg.GRPC{}, serviceMock)

	_, err := srv.IssueMainDomain(context.Background(), &haproxysyncv1.IssueMainDomainRequest{
		Names:          []string{"vdi.example.com"},
		AcmeDnsBaseUrl: "https://auth.example.com",
	})

	assert.Error(t, err)
	serviceMock.AssertNotCalled(t, "IssueMainDomain", mock.Anything, mock.Anything, mock.Anything)
}
