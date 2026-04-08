package haproxysync

import (
	"context"
	"fmt"
	"slices"
	"strings"
)

func (HAproxySync) bastionPrefixSubdomain(subdomain string) string {
	return "." + subdomain
}

func (HAproxySync) bastionRemovePrefixSubdomain(subdomain string) string {
	sub, _ := strings.CutPrefix(subdomain, ".")
	return sub
}

func (h *HAproxySync) BastionSyncMaps(ctx context.Context, maps BastionSyncMaps) (BastionSyncMapsResult, error) {
	h.mux.Lock()
	defer h.mux.Unlock()

	// Get the actual individual domains in the HAProxy
	h.Bastion.subdomains = map[string]bool{}
	currentSubdomains, err := h.haproxy.ShowMap(h.Bastion.SubdomainsMapName)
	if err != nil {
		return BastionSyncMapsResult{}, fmt.Errorf("get current subdomains from HAProxy: %w", err)
	}

	for _, d := range currentSubdomains {
		h.Bastion.subdomains[h.bastionRemovePrefixSubdomain(d)] = true
	}

	subdomainsAdded := 0
	subdomainsRemoved := 0

	// Add the missing subdomains
	for _, d := range maps.Subdomains {
		if _, ok := h.Bastion.subdomains[d]; !ok {
			if err := h.haproxy.AddMap(h.Bastion.SubdomainsMapName, h.bastionPrefixSubdomain(d)); err != nil {
				return BastionSyncMapsResult{}, fmt.Errorf("add subdomain to HAProxy: %w", err)
			}

			h.Bastion.subdomains[d] = true
			subdomainsAdded += 1
		}
	}

	// Remove the extra subdomains
	for d := range h.Bastion.subdomains {
		if !slices.Contains(maps.Subdomains, d) {
			if err := h.haproxy.DelMap(h.Bastion.SubdomainsMapName, h.bastionPrefixSubdomain(d)); err != nil {
				return BastionSyncMapsResult{}, fmt.Errorf("delete subdomain from HAProxy: %w", err)
			}

			delete(h.Bastion.subdomains, d)
			subdomainsRemoved += 1
		}
	}

	// Get the actual individual domains in the HAProxy
	h.Bastion.individualDomains = map[string]bool{}
	currentIndividualDomains, err := h.haproxy.ShowMap(h.Bastion.IndividualDomainsMapName)
	if err != nil {
		return BastionSyncMapsResult{}, fmt.Errorf("get current individual domains from HAProxy: %w", err)
	}

	for _, d := range currentIndividualDomains {
		h.Bastion.individualDomains[d] = true
	}

	individualDomainsAdded := 0
	individualDomainsRemoved := 0

	// Add the missing domains
	for _, d := range maps.IndividualDomains {
		if _, ok := h.Bastion.individualDomains[d]; !ok {
			if err := h.haproxy.AddMap(h.Bastion.IndividualDomainsMapName, d); err != nil {
				return BastionSyncMapsResult{}, fmt.Errorf("add individual domain to HAProxy: %w", err)
			}

			h.Bastion.individualDomains[d] = true
			individualDomainsAdded += 1
		}
	}

	// Remove the extra domains
	for d := range h.Bastion.individualDomains {
		if !slices.Contains(maps.IndividualDomains, d) {
			if err := h.haproxy.DelMap(h.Bastion.IndividualDomainsMapName, d); err != nil {
				return BastionSyncMapsResult{}, fmt.Errorf("delete subdomain from HAProxy: %w", err)
			}

			delete(h.Bastion.individualDomains, d)
			individualDomainsRemoved += 1
		}
	}

	return BastionSyncMapsResult{
		SubdomainsAdded:          subdomainsAdded,
		SubdomainsRemoved:        subdomainsRemoved,
		IndividualDomainsAdded:   individualDomainsAdded,
		IndividualDomainsRemoved: individualDomainsRemoved,
	}, nil
}

func (h *HAproxySync) BastionGetCurrentMaps(ctx context.Context) (BastionCurrentMaps, error) {
	h.mux.RLock()
	defer h.mux.RUnlock()

	result := BastionCurrentMaps{
		Subdomains:        []string{},
		IndividualDomains: []string{},
	}

	for d := range h.Bastion.subdomains {
		result.Subdomains = append(result.Subdomains, d)
	}

	for d := range h.Bastion.individualDomains {
		result.IndividualDomains = append(result.IndividualDomains, d)
	}

	return result, nil
}

func (h *HAproxySync) BastionAddSubdomain(ctx context.Context, subdomain string) error {
	h.mux.Lock()
	defer h.mux.Unlock()

	if err := validateDomain(subdomain); err != nil {
		return err
	}

	if ok := h.Bastion.subdomains[subdomain]; ok {
		h.log.Debug().Str("subdomain", subdomain).Msg("subdomain already in HAProxy, skipping")
		return nil
	}

	if err := h.haproxy.AddMap(h.Bastion.SubdomainsMapName, h.bastionPrefixSubdomain(subdomain)); err != nil {
		return fmt.Errorf("add subdomain to HAProxy: %w", err)
	}

	h.Bastion.subdomains[subdomain] = true

	return nil
}

func (h *HAproxySync) BastionDeleteSubdomain(ctx context.Context, subdomain string) error {
	h.mux.Lock()
	defer h.mux.Unlock()

	if err := validateDomain(subdomain); err != nil {
		return err
	}

	if ok := h.Bastion.subdomains[subdomain]; !ok {
		h.log.Debug().Str("subdomain", subdomain).Msg("subdomain not present in HAProxy, skipping")
		return nil
	}

	if err := h.haproxy.DelMap(h.Bastion.SubdomainsMapName, h.bastionPrefixSubdomain(subdomain)); err != nil {
		return fmt.Errorf("delete subdomain from HAProxy: %w", err)
	}

	delete(h.Bastion.subdomains, subdomain)

	return nil
}

func (h *HAproxySync) BastionAddIndividualDomain(ctx context.Context, domain string) error {
	h.mux.Lock()
	defer h.mux.Unlock()

	if err := validateDomain(domain); err != nil {
		return err
	}

	if ok := h.Bastion.individualDomains[domain]; ok {
		h.log.Debug().Str("domain", domain).Msg("individual domain already in HAProxy, skipping")
		return nil
	}

	if err := h.haproxy.AddMap(h.Bastion.IndividualDomainsMapName, domain); err != nil {
		return fmt.Errorf("add individual domain to HAProxy: %w", err)
	}

	h.Bastion.individualDomains[domain] = true

	return nil
}

func (h *HAproxySync) BastionDeleteIndividualDomain(ctx context.Context, domain string) error {
	h.mux.Lock()
	defer h.mux.Unlock()

	if err := validateDomain(domain); err != nil {
		return err
	}

	if ok := h.Bastion.individualDomains[domain]; !ok {
		h.log.Debug().Str("domain", domain).Msg("individual domain not present in HAProxy, skipping")
		return nil
	}

	if err := h.haproxy.DelMap(h.Bastion.IndividualDomainsMapName, domain); err != nil {
		return fmt.Errorf("delete individual domain from HAProxy: %w", err)
	}

	delete(h.Bastion.individualDomains, domain)

	return nil
}
