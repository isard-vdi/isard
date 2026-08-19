package haproxysync

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
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

	// Add the missing domains, and re-issue the ones whose certificate source
	// changed since they were last materialized.
	for _, d := range wanted {
		fingerprint := domainFingerprint(d)

		if _, present := h.Domains.domains[d.Name]; !present {
			if err := h.addDomain(ctx, d); err != nil {
				h.log.Warn().Err(err).Str("domain", d.Name).Msg("failed to add domain, skipping")
				failedDomains = append(failedDomains, DomainSyncError{
					Domain: d.Name,
					Error:  err.Error(),
				})
				continue
			}

			h.Domains.specs[d.Name] = fingerprint
			domainsAdded += 1
			if len(d.Certificate) == 0 {
				certsIssued += 1
			}
			continue
		}

		previous, known := h.Domains.specs[d.Name]
		if !known {
			// First time this process sees an already-served domain, e.g. right
			// after a restart. Adopt its current state instead of re-issuing,
			// so a restart does not hit the CA once per branding domain.
			h.Domains.specs[d.Name] = fingerprint
			continue
		}
		if previous == fingerprint {
			continue
		}

		if err := h.reissueDomain(ctx, d); err != nil {
			h.log.Warn().Err(err).Str("domain", d.Name).Msg("failed to re-issue domain, skipping")
			failedDomains = append(failedDomains, DomainSyncError{
				Domain: d.Name,
				Error:  err.Error(),
			})
			// Leave the remembered fingerprint alone: recording the one we
			// failed to reach would make the next sync believe the domain is
			// already up to date and never retry.
			continue
		}

		h.Domains.specs[d.Name] = fingerprint
		if len(d.Certificate) == 0 {
			certsIssued += 1
		}
	}

	// Remove the extra domains, reporting failures per domain the way the add
	// path does. Aborting the sync instead would be unrecoverable rather than
	// transient: the entry stays in HAProxy's map, so the next sync rebuilds
	// the same desired set, reaches the same domain and fails at the same
	// point, leaving DomainSync wedged for the whole installation.
	for d := range h.Domains.domains {
		if desiredDomains[d] {
			continue
		}

		certPath := domainCertPath(h.Domains.CertsPath, domainPemName(d))

		if h.isBaseDomain(d) {
			h.dropBaseDomain(d, certPath)

			delete(h.Domains.domains, d)
			domainsRemoved += 1

			continue
		}

		if err := h.removeDomain(ctx, d); err != nil {
			h.log.Warn().Err(err).Str("domain", d).Msg("failed to remove domain, skipping")
			failedDomains = append(failedDomains, DomainSyncError{
				Domain: d,
				Error:  err.Error(),
			})
			continue
		}

		certsRemoved += 1

		delete(h.Domains.domains, d)
		delete(h.Domains.specs, d)
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

// domainFingerprint is a stable signature of what certificate a domain is
// asking for. When it differs from the one last materialized, the desired
// certificate is not the one on disk and the domain must be re-issued even
// though HAProxy is already serving that name.
func domainFingerprint(d DomainSyncDomain) string {
	if len(d.Certificate) > 0 {
		sum := sha256.Sum256(d.Certificate)
		return "custom:" + hex.EncodeToString(sum[:])
	}

	return "http01"
}

// materializeCert produces the PEM bytes for a domain: writing the uploaded
// certificate, or issuing one over ACME and reading the result back.
func (h *HAproxySync) materializeCert(ctx context.Context, d DomainSyncDomain) ([]byte, error) {
	pemName := domainPemName(d.Name)
	certPath := domainCertPath(h.Domains.CertsPath, pemName)

	if len(d.Certificate) > 0 {
		if err := os.WriteFile(certPath, d.Certificate, 0600); err != nil {
			return nil, fmt.Errorf("write provided certificate: %w", err)
		}
		return d.Certificate, nil
	}

	if err := h.acme.IssueCert(ctx, d.Name, pemName); err != nil {
		return nil, fmt.Errorf("issue certificate: %w", err)
	}

	pemData, err := os.ReadFile(certPath)
	if err != nil {
		return nil, fmt.Errorf("read certificate file: %w", err)
	}

	return pemData, nil
}

// reissueDomain swaps the certificate of a domain HAProxy already serves. It
// deliberately does not touch the crt-list or the domain map, which already
// contain the domain: that is what lets a certificate source change take effect
// in place, without a reload.
func (h *HAproxySync) reissueDomain(ctx context.Context, d DomainSyncDomain) error {
	certPath := domainCertPath(h.Domains.CertsPath, domainPemName(d.Name))

	pemData, err := h.materializeCert(ctx, d)
	if err != nil {
		return err
	}

	if err := h.haproxy.SetSslCert(certPath, pemData); err != nil {
		return fmt.Errorf("set ssl cert content: %w", err)
	}

	if err := h.haproxy.CommitSslCert(certPath); err != nil {
		return fmt.Errorf("commit ssl cert: %w", err)
	}

	return nil
}

// removeDomain stops HAProxy serving a domain and deregisters its certificate
// from acme.sh.
//
// The acme.sh deregistration is deliberately tolerant. By the time it runs,
// HAProxy has already stopped serving the domain, so the removal has succeeded
// in the way the caller cares about; reporting a failure here would make the
// domain look un-removed and invite a retry of work that is already done. It
// is worth knowing about, though -- acme.sh will keep renewing a certificate
// nothing serves -- so it is logged rather than dropped.
func (h *HAproxySync) removeDomain(ctx context.Context, d string) error {
	pemName := domainPemName(d)
	certPath := domainCertPath(h.Domains.CertsPath, pemName)

	if err := h.haproxy.DelMap(h.Domains.DomainsMapName, d); err != nil {
		return fmt.Errorf("delete domain from HAProxy: %w", err)
	}

	if err := h.haproxy.DelSslCrtList(h.Domains.CrtListPath, certPath); err != nil {
		return fmt.Errorf("delete ssl crt-list for domain '%s': %w", d, err)
	}

	if err := h.haproxy.DelSslCert(certPath); err != nil {
		return fmt.Errorf("delete ssl cert for domain '%s': %w", d, err)
	}

	if err := h.acme.RemoveCert(ctx, d, pemName); err != nil {
		h.log.Warn().Err(err).Str("domain", d).
			Msg("could not deregister the certificate from acme.sh; it will keep renewing a certificate nothing serves")
	}

	return nil
}

func (h *HAproxySync) addDomain(ctx context.Context, d DomainSyncDomain) error {
	pemName := domainPemName(d.Name)
	certPath := domainCertPath(h.Domains.CertsPath, pemName)

	pemData, err := h.materializeCert(ctx, d)
	if err != nil {
		return err
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

	if err := h.haproxy.AddMap(h.Domains.DomainsMapName, d.Name); err != nil {
		return fmt.Errorf("add domain to map: %w", err)
	}

	h.Domains.domains[d.Name] = true
	return nil
}
