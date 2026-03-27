package haproxysync

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
)

func domainPemName(domain string) string {
	return domain + ".pem"
}

func domainCertPath(certsPath, pemName string) string {
	return filepath.Join(certsPath, pemName)
}

func (h *HAproxySync) DomainSync(ctx context.Context, domains []DomainSyncDomain) (DomainSyncResult, error) {
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

	// Build a set of desired domain names for quick lookup during removal
	desiredDomains := make(map[string]bool, len(domains))
	for _, d := range domains {
		desiredDomains[d.Name] = true
	}

	// Add the missing domains
	for _, d := range domains {
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
		if !desiredDomains[d] {
			pemName := domainPemName(d)
			certPath := domainCertPath(h.Domains.CertsPath, pemName)

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
	}

	return DomainSyncResult{
		DomainsAdded:   domainsAdded,
		DomainsRemoved: domainsRemoved,
		CertsIssued:    certsIssued,
		CertsRemoved:   certsRemoved,
		FailedDomains:  failedDomains,
	}, nil
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
