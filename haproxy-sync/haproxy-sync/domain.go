package haproxysync

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"gitlab.com/isard/isardvdi/haproxy-sync/acme"
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

	// Add the missing domains, and re-issue the ones whose certificate changed.
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
			// First sync after a restart: adopt the already-served state instead
			// of re-issuing, or a restart hits the CA once per branding domain.
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
			// Leave the fingerprint unset on failure, or the next sync believes
			// the domain is up to date and never retries.
			continue
		}

		h.Domains.specs[d.Name] = fingerprint
		if len(d.Certificate) == 0 {
			certsIssued += 1
		}
	}

	// Remove the extra domains, reporting failures per domain rather than
	// aborting: aborting would wedge DomainSync for the whole installation.
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

// defaultAccountThumbprintPath is where acme.sh stores the HTTP-01 account thumbprint.
const defaultAccountThumbprintPath = "/etc/acme/account-thumbprint"

// pushAccountThumbprint writes the HTTP-01 account thumbprint into HAProxy's
// proc var before each issuance: a reload resets it to the parse-time env
// value, so it must be re-pushed. Never fatal (no account file is the normal
// state of an install that does not use ACME for its main domain).
func (h *HAproxySync) pushAccountThumbprint() {
	raw, err := os.ReadFile(h.Domains.accountThumbprintPath)
	if err != nil {
		if !os.IsNotExist(err) {
			h.log.Warn().Err(err).Msg("could not read the ACME account thumbprint")
		}
		return
	}

	if err := h.haproxy.SetProcVar("proc.acme_thumbprint", strings.TrimSpace(string(raw))); err != nil {
		h.log.Warn().Err(err).
			Msg("could not push the ACME account thumbprint; HTTP-01 challenges may not validate")
	}
}

// domainFingerprint is a stable signature of the certificate a domain asks for;
// a change means it must be re-issued even though HAProxy already serves the name.
func domainFingerprint(d DomainSyncDomain) string {
	if len(d.Certificate) > 0 {
		sum := sha256.Sum256(d.Certificate)
		return "custom:" + hex.EncodeToString(sum[:])
	}

	if d.IsACMEDNS() {
		// The account that answers the challenge, deliberately not the
		// password that reaches it. Rotating a credential does not change what
		// certificate the domain is asking for, so re-issuing on one would
		// spend certificate-authority rate limit to install a byte-identical
		// certificate -- and rate limit is the resource that runs out quietly
		// and takes a week to come back. Leaving the secret out also keeps a
		// hash of it from sitting in memory keyed by domain.
		sum := sha256.Sum256([]byte(strings.Join(
			[]string{d.ACMEDNSBaseURL, d.ACMEDNSUsername, d.ACMEDNSSubdomain}, "\x00")))
		return "acmedns:" + hex.EncodeToString(sum[:])
	}

	return "http01"
}

// materializeCert produces the PEM bytes for a domain, writing the uploaded
// certificate or issuing one over ACME.
func (h *HAproxySync) materializeCert(ctx context.Context, d DomainSyncDomain) ([]byte, error) {
	pemName := domainPemName(d.Name)
	certPath := domainCertPath(h.Domains.CertsPath, pemName)

	if len(d.Certificate) > 0 {
		if err := os.WriteFile(certPath, d.Certificate, 0600); err != nil {
			return nil, fmt.Errorf("write provided certificate: %w", err)
		}
		return d.Certificate, nil
	}

	if d.hasPartialACMEDNS() {
		return nil, fmt.Errorf(
			"issue certificate: incomplete acme-dns credentials for '%s': all of base url, username, password and subdomain are required",
			d.Name,
		)
	}

	if d.IsACMEDNS() {
		// No account thumbprint: that is what HAProxy answers a stateless
		// HTTP-01 challenge from, and a DNS-01 challenge never reaches HAProxy.
		if err := h.acme.IssueCertDNS(ctx, d.Name, pemName, d.acmeDNSCredentials()); err != nil {
			return nil, fmt.Errorf("issue certificate: %w", err)
		}
	} else {
		h.pushAccountThumbprint()

		if err := h.acme.IssueCert(ctx, d.Name, pemName); err != nil {
			return nil, fmt.Errorf("issue certificate: %w", err)
		}
	}

	pemData, err := os.ReadFile(certPath)
	if err != nil {
		return nil, fmt.Errorf("read certificate file: %w", err)
	}

	return pemData, nil
}

// reissueDomain swaps the certificate of an already-served domain, deliberately
// not touching the crt-list or domain map so the change takes effect without a reload.
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
// from acme.sh. The acme.sh deregistration failure is logged, not returned:
// HAProxy has already stopped serving, so the removal the caller cares about
// has succeeded.
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

// mainDomainPemName is the crt-list default, i.e. what the deployment is served with.
const mainDomainPemName = "chain.pem"

// customPortalPemName, when present, is preferred by the boot-time crt-list over the ACME one.
const customPortalPemName = "custom-portal-chain.pem"

// checkMainDomainNames rejects a name set the main domain cannot be issued for.
func checkMainDomainNames(names []string) error {
	if len(names) == 0 {
		return fmt.Errorf("%w: no names given for the main domain", ErrInvalidDomain)
	}

	for _, name := range names {
		if err := validateDomain(name); err != nil {
			return err
		}
	}

	return nil
}

// refuseIfShadowed refuses while an operator-supplied certificate outranks the one
// we would issue: the crt-list prefers that file, so anything issued here would be
// deployed and logged as successful, and never served.
//
// The caller holds h.mux.
func (h *HAproxySync) refuseIfShadowed() error {
	shadow := domainCertPath(h.Domains.CertsPath, customPortalPemName)
	if _, err := os.Stat(shadow); err == nil {
		return fmt.Errorf(
			"refusing to issue the main domain certificate: %s takes precedence in the crt-list, so %s would never be served; remove it to let the configured certificate take over",
			customPortalPemName, mainDomainPemName)
	}

	return nil
}

// IssueMainDomain issues the certificate the whole deployment is served with.
//
// Deliberately unlike every other domain here: the main domain is routed by the
// base ACL rather than the domain map, and its certificate is the crt-list
// default rather than a crt-list entry, so this deploys to that default and
// touches nothing else.
func (h *HAproxySync) IssueMainDomain(ctx context.Context, names []string, account acme.ACMEAccount) error {
	if err := checkMainDomainNames(names); err != nil {
		return err
	}

	h.mux.Lock()
	defer h.mux.Unlock()

	if err := h.refuseIfShadowed(); err != nil {
		return err
	}

	h.pushAccountThumbprint()

	if err := h.acme.IssueMainDomain(ctx, names, mainDomainPemName, account); err != nil {
		return fmt.Errorf("issue main domain certificate: %w", err)
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

// IssueMainDomainDNS issues the deployment's certificate over DNS-01.
//
// Same guards as the HTTP-01 path, and one thing left out: the account
// thumbprint is not pushed. That thumbprint is what HAProxy answers a
// stateless HTTP-01 challenge from, and a DNS-01 challenge is answered by
// acme-dns without ever reaching HAProxy.
func (h *HAproxySync) IssueMainDomainDNS(ctx context.Context, names []string, account acme.ACMEAccount, creds acme.ACMEDNSCredentials) error {
	if err := checkMainDomainNames(names); err != nil {
		return err
	}

	if !creds.Complete() {
		return fmt.Errorf(
			"issue main domain certificate: incomplete acme-dns credentials: all of base url, username, password and subdomain are required")
	}

	h.mux.Lock()
	defer h.mux.Unlock()

	if err := h.refuseIfShadowed(); err != nil {
		return err
	}

	if err := h.acme.IssueMainDomainDNS(ctx, names, mainDomainPemName, account, creds); err != nil {
		return fmt.Errorf("issue main domain certificate: %w", err)
	}

	return nil
}
