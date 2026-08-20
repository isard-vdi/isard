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

	// IssueMainDomain issues the deployment's main certificate (see domain.go).
	IssueMainDomain(ctx context.Context, names []string, account acme.ACMEAccount) error

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

	// acme-dns (DNS-01) credentials, all four or none. One registration per
	// domain: an acme-dns account holds a bounded number of TXT records, so
	// domains sharing one would evict each other's challenges.
	ACMEDNSBaseURL   string
	ACMEDNSUsername  string
	ACMEDNSPassword  string
	ACMEDNSSubdomain string
}

// IsACMEDNS reports whether this domain is to be certified over DNS-01.
func (d DomainSyncDomain) IsACMEDNS() bool {
	return d.acmeDNSCredentials().Complete()
}

// hasPartialACMEDNS reports a credential set that is started but not finished.
//
// Worth distinguishing from both of the other two states. Nothing set is a
// plain HTTP-01 domain; all four set is a DNS-01 one; some set is a
// configuration that cannot work, and quietly treating it as HTTP-01 would
// attempt the very challenge the operator moved away from and report its
// failure, which says nothing about the field they left blank.
func (d DomainSyncDomain) hasPartialACMEDNS() bool {
	c := d.acmeDNSCredentials()
	any := c.BaseURL != "" || c.Username != "" || c.Password != "" || c.Subdomain != ""
	return any && !c.Complete()
}

func (d DomainSyncDomain) acmeDNSCredentials() acme.ACMEDNSCredentials {
	return acme.ACMEDNSCredentials{
		BaseURL:   d.ACMEDNSBaseURL,
		Username:  d.ACMEDNSUsername,
		Password:  d.ACMEDNSPassword,
		Subdomain: d.ACMEDNSSubdomain,
	}
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

	// specs remembers the fingerprint last materialized per domain, so a sync
	// tells "already served" apart from "served with the cert we want". In
	// memory and deliberately NOT persisted: on startup every served domain is
	// adopted as-is rather than re-issued, which would hit the CA per domain.
	specs map[string]string

	// accountThumbprintPath is where acme.sh keeps the HTTP-01 account thumbprint.
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
