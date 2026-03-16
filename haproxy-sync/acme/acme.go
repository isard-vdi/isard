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

type Interface interface {
	IssueCert(ctx context.Context, domain, pemName string) error
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
		return fmt.Errorf("remove ACME certificate for '%s': %w: %s", domain, err, out)
	}

	a.log.Info().
		Str("domain", domain).
		Str("pem_name", pemName).
		Msg("ACME certificate removed")

	return nil
}
