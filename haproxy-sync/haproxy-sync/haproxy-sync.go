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

var (
	ErrMissingSubdomain = errors.New("missing subdomain")
	ErrMissingDomain    = errors.New("missing domain")
)

type Interface interface {
	// Check ensures the service is working correctly.
	Check(ctx context.Context) error

	//
	// DomainSync performs a full synchronization of all the domains that HAProxy needs to accept / manage.
	//
	DomainSync(ctx context.Context, domains []string) (DomainSyncResult, error)

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

type DomainSyncResult struct {
	DomainsAdded   int
	DomainsRemoved int
	CertsIssued    int
	CertsRemoved   int
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

	domains map[string]bool
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
		},

		Bastion: &HAProxySyncBastion{
			SubdomainsMapName:        cfg.Bastion.SubdomainsMap,
			IndividualDomainsMapName: cfg.Bastion.IndividualDomainsMap,
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
