package haproxysync

import (
	"context"
	"errors"
	"fmt"
	"maps"
	"os"
	"slices"
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
	// Restore adds back to the HAProxy worker the runtime state it lacks after a reload.
	Restore(ctx context.Context) error

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

	// workerPID is the HAProxy worker the state was last restored into.
	workerPID int

	haproxy haproxy.Interface
	acme    acme.Interface
}

type HAProxySyncDomains struct {
	DomainsMapName string
	CrtListPath    string
	CertsPath      string
	BaseDomain     string

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
			BaseDomain:     cfg.Domains.BaseDomain,
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
	h.mux.Lock()
	defer h.mux.Unlock()

	pid, err := h.haproxy.ShowPID()
	if err != nil {
		return fmt.Errorf("get HAProxy worker PID: %w", err)
	}

	// A different worker means HAProxy was reloaded without haproxy-reload.
	if pid == h.workerPID {
		return nil
	}

	return h.restore(ctx, pid)
}

func (h *HAproxySync) Restore(ctx context.Context) error {
	h.mux.Lock()
	defer h.mux.Unlock()

	pid, err := h.haproxy.ShowPID()
	if err != nil {
		return fmt.Errorf("get HAProxy worker PID: %w", err)
	}

	return h.restore(ctx, pid)
}

// restore only records pid once everything is in, so the next Check retries a failure.
func (h *HAproxySync) restore(ctx context.Context, pid int) (err error) {
	// A failed sync forgets what it couldn't add, but the retry needs it.
	subdomains := maps.Clone(h.Bastion.subdomains)
	individualDomains := maps.Clone(h.Bastion.individualDomains)
	domains := maps.Clone(h.Domains.domains)
	defer func() {
		if err != nil {
			h.Bastion.subdomains = subdomains
			h.Bastion.individualDomains = individualDomains
			h.Domains.domains = domains
		}
	}()

	// Syncing a state that was never synced would empty the worker, and remove its certificates.
	if len(subdomains) != 0 || len(individualDomains) != 0 {
		bastion := BastionSyncMaps{
			Subdomains:        slices.Collect(maps.Keys(subdomains)),
			IndividualDomains: slices.Collect(maps.Keys(individualDomains)),
		}

		if _, err := h.bastionSyncMaps(bastion); err != nil {
			return fmt.Errorf("restore the bastion maps: %w", err)
		}
	}

	if len(domains) != 0 {
		wanted := make([]DomainSyncDomain, 0, len(domains))
		for d := range domains {
			certData, err := os.ReadFile(domainCertPath(h.Domains.CertsPath, domainPemName(d)))
			if err != nil {
				return fmt.Errorf("restore the domains: read certificate file for domain '%s': %w", d, err)
			}

			wanted = append(wanted, DomainSyncDomain{Name: d, Certificate: certData})
		}

		result, err := h.domainSync(ctx, wanted)
		if err != nil {
			return fmt.Errorf("restore the domains: %w", err)
		}

		var errs []error
		for _, f := range result.FailedDomains {
			errs = append(errs, fmt.Errorf("domain '%s': %s", f.Domain, f.Error))
		}

		if err := errors.Join(errs...); err != nil {
			return fmt.Errorf("restore the domains: %w", err)
		}
	}

	h.workerPID = pid

	h.log.Info().
		Int("worker_pid", pid).
		Int("subdomains", len(h.Bastion.subdomains)).
		Int("individual_domains", len(h.Bastion.individualDomains)).
		Int("domains", len(h.Domains.domains)).
		Msg("HAProxy state restored into the worker")

	return nil
}
