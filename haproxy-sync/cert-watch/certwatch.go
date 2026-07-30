package certwatch

import (
	"errors"
	"fmt"
	"io/fs"
	"os"
	"strings"

	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy"

	"github.com/rs/zerolog"
)

// CertWatch keeps the certificates HAProxy serves in sync with the ones on disk.
type CertWatch struct {
	log     *zerolog.Logger
	haproxy haproxy.Interface

	crtListPath string
}

// NewCertWatch returns a CertWatch that reads the certificates from the given crt-list.
func NewCertWatch(log *zerolog.Logger, haproxy haproxy.Interface, crtListPath string) *CertWatch {
	return &CertWatch{
		log:         log,
		haproxy:     haproxy,
		crtListPath: crtListPath,
	}
}

// Certs returns the PEM paths referenced by the HAProxy crt-list. A crt-list entry is
// the certificate path optionally followed by SNI filters, and lines starting with '#'
// are comments.
func (c *CertWatch) Certs() ([]string, error) {
	b, err := os.ReadFile(c.crtListPath)
	if err != nil {
		// The crt-list is written by prepare.sh at startup, so it can legitimately
		// not be there yet on the first ticks.
		if errors.Is(err, fs.ErrNotExist) {
			return []string{}, nil
		}

		return nil, fmt.Errorf("read the crt-list '%s': %w", c.crtListPath, err)
	}

	certs := []string{}
	for line := range strings.Lines(string(b)) {
		fields := strings.Fields(line)
		if len(fields) == 0 || strings.HasPrefix(fields[0], "#") {
			continue
		}

		certs = append(certs, fields[0])
	}

	return certs, nil
}

// Update loads each certificate into HAProxy and commits it over the admin socket. This
// is a hot update: HAProxy validates the PEM before committing it and no worker is
// reloaded, so established connections are untouched.
func (c *CertWatch) Update(certs []string) error {
	for _, cert := range certs {
		pem, err := os.ReadFile(cert)
		if err != nil {
			return fmt.Errorf("read the certificate '%s': %w", cert, err)
		}

		if err := c.haproxy.SetSslCert(cert, pem); err != nil {
			return err
		}

		if err := c.haproxy.CommitSslCert(cert); err != nil {
			return err
		}

		c.log.Info().Str("cert", cert).Msg("tls certificate updated")
	}

	return nil
}
