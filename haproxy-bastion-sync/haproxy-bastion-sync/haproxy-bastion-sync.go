package haproxybastionsync

import (
	"context"
	"errors"
	"fmt"
	"slices"
	"strings"
	"sync"

	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi/haproxy-bastion-sync/cfg"
	"gitlab.com/isard/isardvdi/haproxy-bastion-sync/haproxy"
)

var (
	ErrMissingSubdomain = errors.New("missing subdomain")
	ErrMissingDomain    = errors.New("missing domain")
)

type Interface interface {
	// Check ensures the service is working correctly
	Check(ctx context.Context) error

	// SyncMaps performs a full syncronization of all the maps
	SyncMaps(ctx context.Context, maps SyncMaps) (SyncMapsResult, error)
	// GetCurrentMaps returns a the state of all the maps
	GetCurrentMaps(ctx context.Context) (CurrentMaps, error)

	// Subdomains
	AddSubdomain(ctx context.Context, subdomain string) error
	DeleteSubdomain(ctx context.Context, subdomain string) error

	// Individual Domains
	AddIndividualDomain(ctx context.Context, domain string) error
	DeleteIndividualDomain(ctx context.Context, domain string) error
}

type SyncMaps struct {
	Subdomains        []string
	IndividualDomains []string
}

type SyncMapsResult struct {
	SubdomainsAdded          int
	SubdomainsRemoved        int
	IndividualDomainsAdded   int
	IndividualDomainsRemoved int
}

type CurrentMaps struct {
	Subdomains        []string
	IndividualDomains []string
}

var _ Interface = &HAproxyBastionSync{}

type HAproxyBastionSync struct {
	log *zerolog.Logger
	mux sync.RWMutex

	SubdomainsMapName        string
	IndividualDomainsMapName string

	subdomains        map[string]bool
	individualDomains map[string]bool

	haproxy haproxy.Interface
}

func Init(log *zerolog.Logger, cfg cfg.Cfg, haproxy haproxy.Interface) *HAproxyBastionSync {
	return &HAproxyBastionSync{
		log: log,

		SubdomainsMapName:        cfg.Haproxy.SubdomainsMap,
		IndividualDomainsMapName: cfg.Haproxy.IndividualDomainsMap,

		haproxy: haproxy,
	}
}

func (HAproxyBastionSync) prefixSubdomain(subdomain string) string {
	return "." + subdomain
}

func (HAproxyBastionSync) removePrefixSubdomain(subdomain string) string {
	sub, _ := strings.CutPrefix(subdomain, ".")
	return sub
}

func (h *HAproxyBastionSync) Check(ctx context.Context) error {
	if _, err := h.haproxy.ShowVersion(); err != nil {
		return fmt.Errorf("get HAProxy version: %w", err)
	}

	return nil
}

func (h *HAproxyBastionSync) SyncMaps(ctx context.Context, maps SyncMaps) (SyncMapsResult, error) {
	h.mux.Lock()
	defer h.mux.Unlock()

	// Get the actual individual domains in the HAProxy
	h.subdomains = map[string]bool{}
	currentSubdomains, err := h.haproxy.ShowMap(h.SubdomainsMapName)
	if err != nil {
		return SyncMapsResult{}, fmt.Errorf("get current subdomains from HAProxy: %w", err)
	}

	for _, d := range currentSubdomains {
		h.subdomains[h.removePrefixSubdomain(d)] = true
	}

	subdomainsAdded := 0
	subdomainsRemoved := 0

	// Add the missing subdomains
	for _, d := range maps.Subdomains {
		if _, ok := h.subdomains[d]; !ok {
			if err := h.haproxy.AddMap(h.SubdomainsMapName, h.prefixSubdomain(d)); err != nil {
				return SyncMapsResult{}, fmt.Errorf("add subdomain to HAProxy: %w", err)
			}

			h.subdomains[d] = true
			subdomainsAdded += 1
		}
	}

	// Remove the extra subdomains
	for d := range h.subdomains {
		if !slices.Contains(maps.Subdomains, d) {
			if err := h.haproxy.DelMap(h.SubdomainsMapName, h.prefixSubdomain(d)); err != nil {
				return SyncMapsResult{}, fmt.Errorf("delete subdomain from HAProxy: %w", err)
			}

			delete(h.subdomains, d)
			subdomainsRemoved += 1
		}
	}

	// Get the actual individual domains in the HAProxy
	h.individualDomains = map[string]bool{}
	currentIndividualDomains, err := h.haproxy.ShowMap(h.IndividualDomainsMapName)
	if err != nil {
		return SyncMapsResult{}, fmt.Errorf("get current individual domains from HAProxy: %w", err)
	}

	for _, d := range currentIndividualDomains {
		h.individualDomains[d] = true
	}

	individualDomainsAdded := 0
	individualDomainsRemoved := 0

	// Add the missing domains
	for _, d := range maps.IndividualDomains {
		if _, ok := h.individualDomains[d]; !ok {
			if err := h.haproxy.AddMap(h.IndividualDomainsMapName, d); err != nil {
				return SyncMapsResult{}, fmt.Errorf("add individual domain to HAProxy: %w", err)
			}

			h.individualDomains[d] = true
			individualDomainsAdded += 1
		}
	}

	// Remove the extra domains
	for d := range h.individualDomains {
		if !slices.Contains(maps.IndividualDomains, d) {
			if err := h.haproxy.DelMap(h.IndividualDomainsMapName, d); err != nil {
				return SyncMapsResult{}, fmt.Errorf("delete subdomain from HAProxy: %w", err)
			}

			delete(h.individualDomains, d)
			individualDomainsRemoved += 1
		}
	}

	return SyncMapsResult{
		SubdomainsAdded:          subdomainsAdded,
		SubdomainsRemoved:        subdomainsRemoved,
		IndividualDomainsAdded:   individualDomainsAdded,
		IndividualDomainsRemoved: individualDomainsRemoved,
	}, nil
}

func (h *HAproxyBastionSync) GetCurrentMaps(ctx context.Context) (CurrentMaps, error) {
	h.mux.RLock()
	defer h.mux.RUnlock()

	result := CurrentMaps{
		Subdomains:        []string{},
		IndividualDomains: []string{},
	}

	for d := range h.subdomains {
		result.Subdomains = append(result.Subdomains, d)
	}

	for d := range h.individualDomains {
		result.IndividualDomains = append(result.IndividualDomains, d)
	}

	return result, nil
}

func (h *HAproxyBastionSync) AddSubdomain(ctx context.Context, subdomain string) error {
	h.mux.Lock()
	defer h.mux.Unlock()

	if subdomain == "" {
		return ErrMissingSubdomain
	}

	if ok := h.subdomains[subdomain]; ok {
		h.log.Debug().Str("subdomain", subdomain).Msg("subdomain already in HAProxy, skipping")
		return nil
	}

	if err := h.haproxy.AddMap(h.SubdomainsMapName, h.prefixSubdomain(subdomain)); err != nil {
		return fmt.Errorf("add subdomain to HAProxy: %w", err)
	}

	h.subdomains[subdomain] = true

	return nil
}

func (h *HAproxyBastionSync) DeleteSubdomain(ctx context.Context, subdomain string) error {
	h.mux.Lock()
	defer h.mux.Unlock()

	if subdomain == "" {
		return ErrMissingSubdomain
	}

	if ok := h.subdomains[subdomain]; !ok {
		h.log.Debug().Str("subdomain", subdomain).Msg("subdomain not present in HAProxy, skipping")
		return nil
	}

	if err := h.haproxy.DelMap(h.SubdomainsMapName, h.prefixSubdomain(subdomain)); err != nil {
		return fmt.Errorf("delete subdomain from HAProxy: %w", err)
	}

	delete(h.subdomains, subdomain)

	return nil
}

func (h *HAproxyBastionSync) AddIndividualDomain(ctx context.Context, domain string) error {
	h.mux.Lock()
	defer h.mux.Unlock()

	if domain == "" {
		return ErrMissingDomain
	}

	if ok := h.individualDomains[domain]; ok {
		h.log.Debug().Str("domain", domain).Msg("individual domain already in HAProxy, skipping")
		return nil
	}

	if err := h.haproxy.AddMap(h.IndividualDomainsMapName, domain); err != nil {
		return fmt.Errorf("add individual domain to HAProxy: %w", err)
	}

	h.individualDomains[domain] = true

	return nil
}

func (h *HAproxyBastionSync) DeleteIndividualDomain(ctx context.Context, domain string) error {
	h.mux.Lock()
	defer h.mux.Unlock()

	if domain == "" {
		return ErrMissingDomain
	}

	if ok := h.individualDomains[domain]; !ok {
		h.log.Debug().Str("domain", domain).Msg("individual domain not present in HAProxy, skipping")
		return nil
	}

	if err := h.haproxy.DelMap(h.IndividualDomainsMapName, domain); err != nil {
		return fmt.Errorf("delete individual domain from HAProxy: %w", err)
	}

	delete(h.individualDomains, domain)

	return nil
}
