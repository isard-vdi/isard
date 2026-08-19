package haproxysync

import (
	"context"
	"errors"
	"fmt"
	"sync"

	"gitlab.com/isard/isardvdi/haproxy-sync/acme"
	"gitlab.com/isard/isardvdi/haproxy-sync/cfg"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy"

	"github.com/rs/zerolog"
)

var ErrInvalidDomain = errors.New("invalid domain name")

type Interface interface {
	// Check ensures the service is working correctly.
	Check(ctx context.Context) error

	//
	// DomainSync performs a full synchronization of all the domains that HAProxy needs to accept / manage.
	//
	DomainSync(ctx context.Context, domains []DomainSyncDomain) (DomainSyncResult, error)

	//
	// Bastion
	//

	// BastionSyncMaps performs a full synchronization of all the maps.
	BastionSyncMaps(ctx context.Context, maps BastionSyncMaps) (BastionSyncMapsResult, error)
	// BastionGetCurrentMaps returns the state of all the maps.
	BastionGetCurrentMaps(ctx context.Context) (BastionCurrentMaps, error)

	// Bastion Subdomains
	BastionAddSubdomain(ctx context.Context, subdomain string) error
	BastionDeleteSubdomain(ctx context.Context, subdomain string) error

	// Bastion Individual Domains
	BastionAddIndividualDomain(ctx context.Context, domain string) error
	BastionDeleteIndividualDomain(ctx context.Context, domain string) error
}

type DomainSyncDomain struct {
	Name        string
	Certificate []byte // PEM. If empty, issued via ACME.
}

type DomainSyncError struct {
	Domain string
	Error  string
}

type DomainSyncResult struct {
	DomainsAdded   int
	DomainsRemoved int
	CertsIssued    int
	CertsRemoved   int
	FailedDomains  []DomainSyncError
}

type BastionSyncMaps struct {
	Subdomains        []string
	IndividualDomains []string
}

type BastionSyncMapsResult struct {
	SubdomainsAdded          int
	SubdomainsRemoved        int
	IndividualDomainsAdded   int
	IndividualDomainsRemoved int
}

type BastionCurrentMaps struct {
	Subdomains        []string
	IndividualDomains []string
}

var _ Interface = &HAproxySync{}

type HAproxySync struct {
	log *zerolog.Logger
	mux sync.RWMutex

	Domains *HAProxySyncDomains
	Bastion *HAProxySyncBastion

	haproxy haproxy.Interface
	acme    acme.Interface
}

type HAProxySyncDomains struct {
	DomainsMapName string
	CrtListPath    string
	CertsPath      string
	BaseDomain     string

	// domains is the presence set, rebuilt from HAProxy's map on every sync.
	domains map[string]bool

	// specs remembers the certificate fingerprint last materialized for each
	// domain, so a sync can tell "already served" apart from "already served
	// with the certificate we want". Without it, DomainSync only ever compared
	// names and a change of certificate source was silently dropped.
	//
	// It lives in memory for the process lifetime and is deliberately NOT
	// persisted: on startup every already-served domain is unknown and gets
	// adopted as-is, because re-issuing all of them would hit the CA once per
	// branding domain on every restart. The cost is that a change made while
	// this process was down is adopted rather than applied — the next real
	// change is picked up normally. Deriving the fingerprint from the
	// certificate HAProxy actually serves would remove that gap.
	specs map[string]string

	// accountThumbprintPath is where acme.sh keeps the HTTP-01 account
	// thumbprint that the challenge responder answers with.
	accountThumbprintPath string
}

type HAProxySyncBastion struct {
	SubdomainsMapName        string
	IndividualDomainsMapName string

	subdomains        map[string]bool
	individualDomains map[string]bool
}

func Init(log *zerolog.Logger, cfg cfg.HAProxy, haproxy haproxy.Interface, acme acme.Interface) *HAproxySync {
	return &HAproxySync{
		log: log,

		Domains: &HAProxySyncDomains{
			DomainsMapName: cfg.Domains.DomainsMap,
			CrtListPath:    cfg.Domains.CrtListPath,
			CertsPath:      cfg.Domains.CertsPath,
			BaseDomain:     cfg.Domains.BaseDomain,
			specs:          map[string]string{},

			accountThumbprintPath: defaultAccountThumbprintPath,
		},

		Bastion: &HAProxySyncBastion{
			SubdomainsMapName:        cfg.Bastion.SubdomainsMap,
			IndividualDomainsMapName: cfg.Bastion.IndividualDomainsMap,
			subdomains:               map[string]bool{},
			individualDomains:        map[string]bool{},
		},

		haproxy: haproxy,
		acme:    acme,
	}
}

func (h *HAproxySync) Check(ctx context.Context) error {
	if _, err := h.haproxy.ShowVersion(); err != nil {
		return fmt.Errorf("get HAProxy version: %w", err)
	}

	return nil
}
