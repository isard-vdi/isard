package acme

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/rs/zerolog"
)

const (
	issueScriptPath    = "/usr/local/bin/acme-generate-cert.sh"
	issueDNSScriptPath = "/usr/local/bin/acme-dns-generate-cert.sh"
	removeScriptPath   = "/usr/local/bin/acme-remove-cert.sh"
)

// ACMEAccount identifies the CA and account to issue under. The main domain
// carries its own (configured in the database); branding domains inherit the
// container's.
type ACMEAccount struct {
	Server string
	Email  string
}

// ACMEDNSCredentials is one acme-dns registration: the account that may write
// the challenge TXT record under one throwaway subdomain, and nothing else.
//
// One registration per domain rather than one per deployment. An acme-dns
// account holds a bounded number of TXT records, so domains sharing one would
// evict each other's challenges -- intermittently, and only when two renewals
// happen close together, which is the worst way for it to show up.
type ACMEDNSCredentials struct {
	BaseURL   string
	Username  string
	Password  string
	Subdomain string
}

// Complete reports whether the credentials can actually issue anything.
//
// All four or none: three of four is not a degraded mode, it is a failure that
// happens inside acme.sh with a message about DNS resolution, which sends
// whoever reads it to look at the zone instead of at the form they just saved.
func (c ACMEDNSCredentials) Complete() bool {
	return c.BaseURL != "" && c.Username != "" && c.Password != "" && c.Subdomain != ""
}

type Interface interface {
	IssueCert(ctx context.Context, domain, pemName string) error
	IssueCertDNS(ctx context.Context, domain, pemName string, creds ACMEDNSCredentials) error
	IssueMainDomain(ctx context.Context, names []string, pemName string, account ACMEAccount) error
	IssueMainDomainDNS(ctx context.Context, names []string, pemName string, account ACMEAccount, creds ACMEDNSCredentials) error
	RemoveCert(ctx context.Context, domain, pemName string) error
}

var _ Interface = &ACME{}

type ACME struct {
	log       *zerolog.Logger
	certsPath string

	// Script locations, fields rather than constants only so the tests can
	// point them at a stub. Production always uses the defaults below.
	issueScript    string
	issueDNSScript string
	removeScript   string
}

func NewACME(log *zerolog.Logger, certsPath string) *ACME {
	return &ACME{
		log:            log,
		certsPath:      certsPath,
		issueScript:    issueScriptPath,
		issueDNSScript: issueDNSScriptPath,
		removeScript:   removeScriptPath,
	}
}

func (a *ACME) IssueCert(ctx context.Context, domain, pemName string) error {
	a.log.Info().
		Str("domain", domain).
		Str("pem_name", pemName).
		Msg("issuing ACME certificate")

	out, err := exec.CommandContext(ctx, a.issueScript, domain, pemName).CombinedOutput()
	if err != nil {
		return fmt.Errorf("issue ACME certificate for '%s': %w: %s", domain, err, out)
	}

	certPath := filepath.Join(a.certsPath, pemName)
	if _, err := os.Stat(certPath); err != nil {
		return fmt.Errorf("verify certificate file '%s': %w", certPath, err)
	}

	a.log.Info().
		Str("domain", domain).
		Str("pem_name", pemName).
		Msg("ACME certificate issued")

	return nil
}

func (a *ACME) RemoveCert(ctx context.Context, domain, pemName string) error {
	a.log.Info().
		Str("domain", domain).
		Str("pem_name", pemName).
		Msg("removing ACME certificate")

	out, err := exec.CommandContext(ctx, a.removeScript, domain, pemName).CombinedOutput()
	if err != nil {
		a.log.Warn().
			Err(err).
			Str("domain", domain).
			Str("pem_name", pemName).
			Str("output", string(out)).
			Msg("ACME certificate removal failed, domain may not exist in ACME")
		return nil
	}

	a.log.Info().
		Str("domain", domain).
		Str("pem_name", pemName).
		Msg("ACME certificate removed")

	return nil
}

// IssueMainDomain issues the deployment's certificate under the given account.
// Each name is a separate argument: joining them would make a name containing
// whitespace an argument-injection vector into acme.sh.
func (a *ACME) IssueMainDomain(ctx context.Context, names []string, pemName string, account ACMEAccount) error {
	if len(names) == 0 {
		return fmt.Errorf("issue main domain certificate: no names given")
	}

	a.log.Info().
		Strs("names", names).
		Str("primary", names[0]).
		Str("pem_name", pemName).
		Str("acme_server", account.Server).
		Msg("issuing main domain certificate")

	// acme-generate-cert.sh <primary> <pem> <server> <email> [extra names...]
	args := append([]string{names[0], pemName, account.Server, account.Email}, names[1:]...)

	out, err := exec.CommandContext(ctx, a.issueScript, args...).CombinedOutput()
	if err != nil {
		return fmt.Errorf("issue main domain certificate for '%s': %w: %s", names[0], err, out)
	}

	certPath := filepath.Join(a.certsPath, pemName)
	if _, err := os.Stat(certPath); err != nil {
		return fmt.Errorf("verify certificate file '%s': %w", certPath, err)
	}

	a.log.Info().
		Strs("names", names).
		Str("pem_name", pemName).
		Msg("main domain certificate issued")

	return nil
}

// issueDNS runs the DNS-01 issuance script with the password on stdin.
//
// Everything about how the password travels is here. It is NOT an argument,
// because argv is readable through /proc/<pid>/cmdline by anything else in the
// container and is printed by any ps an operator runs -- which is exactly what
// they run while debugging the failure that made them look. It is NOT in the
// child's environment either: the script puts it into acme.sh's environment
// itself, from stdin, so adding it here would only widen the exposure to
// /proc/<pid>/environ for the whole run.
//
// The script's output is deliberately not captured into the error. acme.sh's
// dns_acmedns plugin logs the acme-dns request it makes and the password is a
// header on it, so the script keeps that output in a file of its own; putting
// it back in an error would send it up through gRPC into an apiv4 log line,
// which is the same destination the argv exposure had.
func (a *ACME) issueDNS(ctx context.Context, creds ACMEDNSCredentials, args ...string) error {
	cmd := exec.CommandContext(ctx, a.issueDNSScript, args...)
	cmd.Env = append(os.Environ(),
		"ACMEDNS_BASE_URL="+creds.BaseURL,
		"ACMEDNS_USERNAME="+creds.Username,
		"ACMEDNS_SUBDOMAIN="+creds.Subdomain,
	)
	cmd.Stdin = strings.NewReader(creds.Password + "\n")

	return cmd.Run()
}

func (a *ACME) verifyIssued(pemName string) error {
	certPath := filepath.Join(a.certsPath, pemName)
	if _, err := os.Stat(certPath); err != nil {
		return fmt.Errorf("verify certificate file '%s': %w", certPath, err)
	}
	return nil
}

// IssueCertDNS issues a per-category branding domain certificate over DNS-01.
func (a *ACME) IssueCertDNS(ctx context.Context, domain, pemName string, creds ACMEDNSCredentials) error {
	if !creds.Complete() {
		return fmt.Errorf("issue ACME DNS-01 certificate for '%s': incomplete acme-dns credentials", domain)
	}

	// The base URL is logged and the username is not secret; the password and
	// the subdomain are left out. The subdomain is what the account may write
	// to, so it is half of the credential.
	a.log.Info().
		Str("domain", domain).
		Str("pem_name", pemName).
		Str("acme_dns_base_url", creds.BaseURL).
		Msg("issuing ACME DNS-01 certificate")

	if err := a.issueDNS(ctx, creds, domain, pemName); err != nil {
		return fmt.Errorf("issue ACME DNS-01 certificate for '%s': %w", domain, err)
	}

	if err := a.verifyIssued(pemName); err != nil {
		return err
	}

	a.log.Info().
		Str("domain", domain).
		Str("pem_name", pemName).
		Msg("ACME DNS-01 certificate issued")

	return nil
}

// IssueMainDomainDNS issues the deployment's own certificate over DNS-01.
//
// A single name only. One acme.sh invocation uses one acme-dns account for
// every name on the certificate, and an account holds a bounded number of TXT
// records, so a multi-name certificate here is a different problem that wants
// its own design. Refused with a message about names rather than left to the
// script, which can only answer with an exit code.
func (a *ACME) IssueMainDomainDNS(ctx context.Context, names []string, pemName string, account ACMEAccount, creds ACMEDNSCredentials) error {
	if len(names) == 0 {
		return fmt.Errorf("issue main domain DNS-01 certificate: no names given")
	}
	if len(names) > 1 {
		return fmt.Errorf(
			"issue main domain DNS-01 certificate: dns-01 issuance takes a single name, refusing to ignore: %s",
			strings.Join(names[1:], ", "),
		)
	}
	if !creds.Complete() {
		return fmt.Errorf("issue main domain DNS-01 certificate for '%s': incomplete acme-dns credentials", names[0])
	}

	a.log.Info().
		Str("primary", names[0]).
		Str("pem_name", pemName).
		Str("acme_server", account.Server).
		Str("acme_dns_base_url", creds.BaseURL).
		Msg("issuing main domain DNS-01 certificate")

	if err := a.issueDNS(ctx, creds, names[0], pemName, account.Server); err != nil {
		return fmt.Errorf("issue main domain DNS-01 certificate for '%s': %w", names[0], err)
	}

	if err := a.verifyIssued(pemName); err != nil {
		return err
	}

	a.log.Info().
		Str("primary", names[0]).
		Str("pem_name", pemName).
		Msg("main domain DNS-01 certificate issued")

	return nil
}
