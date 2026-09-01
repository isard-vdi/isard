package haproxysync

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"golang.org/x/net/idna"
)

// maxDNSNameLength is the maximum length of a DNS domain name in bytes
// per RFC 1035. The idna Lookup profile does not enforce this on its own.
const maxDNSNameLength = 253

// validateDomain validates a domain name using the IDNA Lookup profile
// (RFC 5891) plus an explicit length check. Wildcards are not accepted:
// any "*" must be expanded to a concrete domain before sync. Returns an
// error wrapping ErrInvalidDomain so callers can match it with errors.Is.
func validateDomain(d string) error {
	if d == "" {
		return fmt.Errorf("%w: empty", ErrInvalidDomain)
	}

	if len(d) > maxDNSNameLength {
		return fmt.Errorf("%w: %q exceeds %d bytes", ErrInvalidDomain, d, maxDNSNameLength)
	}

	if _, err := idna.Lookup.ToASCII(d); err != nil {
		return fmt.Errorf("%w: %q: %w", ErrInvalidDomain, d, err)
	}

	return nil
}

func domainPemName(domain string) string {
	return domain + ".pem"
}

func domainCertPath(certsPath, pemName string) string {
	return filepath.Join(certsPath, pemName)
}

func (h *HAproxySync) DomainSync(ctx context.Context, domains []DomainSyncDomain) (DomainSyncResult, error) {
	for _, d := range domains {
		if err := validateDomain(d.Name); err != nil {
			return DomainSyncResult{}, err
		}
	}

	h.mux.Lock()
	defer h.mux.Unlock()

	// Get the actual domains in the HAProxy
	h.Domains.domains = map[string]bool{}
	currentDomains, err := h.haproxy.ShowMap(h.Domains.DomainsMapName)
	if err != nil {
		return DomainSyncResult{}, fmt.Errorf("get current domains from HAProxy: %w", err)
	}

	for _, d := range currentDomains {
		h.Domains.domains[d] = true
	}

	domainsAdded := 0
	domainsRemoved := 0
	certsIssued := 0
	certsRemoved := 0
	var failedDomains []DomainSyncError

	// A second certificate for the domain the base one already serves leaves two
	// crt-list entries with the same SAN, and neither reliably wins SNI.
	wanted := make([]DomainSyncDomain, 0, len(domains))
	for _, d := range domains {
		if h.isBaseDomain(d.Name) {
			h.log.Warn().
				Str("domain", d.Name).
				Msg("refusing to manage the deployment's own domain, the base certificate already serves it")

			failedDomains = append(failedDomains, DomainSyncError{
				Domain: d.Name,
				Error:  fmt.Sprintf("%q is the deployment's own domain, already served by the base certificate", d.Name),
			})

			continue
		}

		wanted = append(wanted, d)
	}

	// Build a set of desired domain names for quick lookup during removal.
	desiredDomains := make(map[string]bool, len(wanted))
	for _, d := range wanted {
		desiredDomains[d.Name] = true
	}

	// Add the missing domains
	for _, d := range wanted {
		if _, ok := h.Domains.domains[d.Name]; !ok {
			if err := h.addDomain(ctx, d.Name, d.Certificate); err != nil {
				h.log.Warn().Err(err).Str("domain", d.Name).Msg("failed to add domain, skipping")
				failedDomains = append(failedDomains, DomainSyncError{
					Domain: d.Name,
					Error:  err.Error(),
				})
				continue
			}

			domainsAdded += 1
			if len(d.Certificate) == 0 {
				certsIssued += 1
			}
		}
	}

	// Remove the extra domains
	for d := range h.Domains.domains {
		if desiredDomains[d] {
			continue
		}

		pemName := domainPemName(d)
		certPath := domainCertPath(h.Domains.CertsPath, pemName)

		if h.isBaseDomain(d) {
			h.dropBaseDomain(d, certPath)

			delete(h.Domains.domains, d)
			domainsRemoved += 1

			continue
		}

		if err := h.haproxy.DelMap(h.Domains.DomainsMapName, d); err != nil {
			return DomainSyncResult{}, fmt.Errorf("delete domain from HAProxy: %w", err)
		}

		if err := h.haproxy.DelSslCrtList(h.Domains.CrtListPath, certPath); err != nil {
			return DomainSyncResult{}, fmt.Errorf("delete ssl crt-list for domain '%s': %w", d, err)
		}

		if err := h.haproxy.DelSslCert(certPath); err != nil {
			return DomainSyncResult{}, fmt.Errorf("delete ssl cert for domain '%s': %w", d, err)
		}

		h.acme.RemoveCert(ctx, d, pemName)
		certsRemoved += 1

		delete(h.Domains.domains, d)
		domainsRemoved += 1
	}

	return DomainSyncResult{
		DomainsAdded:   domainsAdded,
		DomainsRemoved: domainsRemoved,
		CertsIssued:    certsIssued,
		CertsRemoved:   certsRemoved,
		FailedDomains:  failedDomains,
	}, nil
}

// dropBaseDomain removes a duplicate registered before the refusal above,
// leaving untouched the ACME state the base certificate renews from.
func (h *HAproxySync) dropBaseDomain(d, certPath string) {
	if err := h.haproxy.DelMap(h.Domains.DomainsMapName, d); err != nil {
		h.log.Warn().Err(err).Str("domain", d).Msg("delete the deployment's own domain from the domains map")
	}

	if err := h.haproxy.DelSslCrtList(h.Domains.CrtListPath, certPath); err != nil {
		h.log.Warn().Err(err).Str("domain", d).Msg("delete the deployment's own domain from the crt-list")
	}

	if err := h.haproxy.DelSslCert(certPath); err != nil {
		h.log.Warn().Err(err).Str("domain", d).Msg("delete the deployment's own domain certificate")
	}

	h.log.Warn().
		Str("domain", d).
		Msg("dropped the deployment's own domain from HAProxy, its ACME state was left untouched")
}

// isBaseDomain reports whether d is the deployment's own domain, matched case
// insensitively as DNS names are.
func (h *HAproxySync) isBaseDomain(d string) bool {
	return h.Domains.BaseDomain != "" && strings.EqualFold(d, h.Domains.BaseDomain)
}

func (h *HAproxySync) addDomain(ctx context.Context, d string, certData []byte) error {
	pemName := domainPemName(d)
	certPath := domainCertPath(h.Domains.CertsPath, pemName)

	var pemData []byte
	if len(certData) > 0 {
		if err := os.WriteFile(certPath, certData, 0600); err != nil {
			return fmt.Errorf("write provided certificate: %w", err)
		}
		pemData = certData
	} else {
		if err := h.acme.IssueCert(ctx, d, pemName); err != nil {
			return fmt.Errorf("issue certificate: %w", err)
		}

		var err error
		pemData, err = os.ReadFile(certPath)
		if err != nil {
			return fmt.Errorf("read certificate file: %w", err)
		}
	}

	if err := h.haproxy.NewSslCert(certPath); err != nil {
		return fmt.Errorf("create ssl cert storage: %w", err)
	}

	if err := h.haproxy.SetSslCert(certPath, pemData); err != nil {
		return fmt.Errorf("set ssl cert content: %w", err)
	}

	if err := h.haproxy.CommitSslCert(certPath); err != nil {
		return fmt.Errorf("commit ssl cert: %w", err)
	}

	if err := h.haproxy.AddSslCrtList(h.Domains.CrtListPath, certPath); err != nil {
		return fmt.Errorf("add ssl crt-list: %w", err)
	}

	if err := h.haproxy.AddMap(h.Domains.DomainsMapName, d); err != nil {
		return fmt.Errorf("add domain to map: %w", err)
	}

	h.Domains.domains[d] = true
	return nil
}
