package acme

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"

	"github.com/rs/zerolog"
)

const (
	issueScriptPath  = "/usr/local/bin/acme-generate-cert.sh"
	removeScriptPath = "/usr/local/bin/acme-remove-cert.sh"
)

// ACMEAccount identifies the CA and account to issue under. The main domain
// carries its own (configured in the database); branding domains inherit the
// container's.
type ACMEAccount struct {
	Server string
	Email  string
}

type Interface interface {
	IssueCert(ctx context.Context, domain, pemName string) error
	IssueMainDomain(ctx context.Context, names []string, pemName string, account ACMEAccount) error
	RemoveCert(ctx context.Context, domain, pemName string) error
}

var _ Interface = &ACME{}

type ACME struct {
	log       *zerolog.Logger
	certsPath string
}

func NewACME(log *zerolog.Logger, certsPath string) *ACME {
	return &ACME{
		log:       log,
		certsPath: certsPath,
	}
}

func (a *ACME) IssueCert(ctx context.Context, domain, pemName string) error {
	a.log.Info().
		Str("domain", domain).
		Str("pem_name", pemName).
		Msg("issuing ACME certificate")

	out, err := exec.CommandContext(ctx, issueScriptPath, domain, pemName).CombinedOutput()
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

	out, err := exec.CommandContext(ctx, removeScriptPath, domain, pemName).CombinedOutput()
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

	out, err := exec.CommandContext(ctx, issueScriptPath, args...).CombinedOutput()
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
