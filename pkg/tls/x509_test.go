package tls_test

import (
	"crypto/rsa"
	"crypto/tls"
	"crypto/x509"
	"os"
	"path/filepath"
	"testing"
	"time"

	pkgTls "gitlab.com/isard/isardvdi/pkg/tls"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestGenerateSelfSignedKeyPair(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Cfg          pkgTls.CertConfig
		PreparePaths func(t *testing.T) (certPath, keyPath string)
		ExpectedErr  string
	}{
		"should work as expected": {
			Cfg: pkgTls.CertConfig{
				CommonName: "sp.example.com",
				Duration:   10 * 365 * 24 * time.Hour,
			},
			PreparePaths: func(t *testing.T) (string, string) {
				dir := t.TempDir()

				return filepath.Join(dir, "cert.pem"), filepath.Join(dir, "key.pem")
			},
		},
		"should overwrite an existing key pair": {
			Cfg: pkgTls.CertConfig{
				CommonName: "sp.example.com",
				Duration:   time.Hour,
			},
			PreparePaths: func(t *testing.T) (string, string) {
				dir := t.TempDir()
				certPath := filepath.Join(dir, "cert.pem")
				keyPath := filepath.Join(dir, "key.pem")

				require.NoError(t, os.WriteFile(certPath, []byte("old"), 0o644))
				require.NoError(t, os.WriteFile(keyPath, []byte("old"), 0o600))

				return certPath, keyPath
			},
		},
		"should return an error if the directory does not exist": {
			Cfg: pkgTls.CertConfig{
				CommonName: "sp.example.com",
				Duration:   time.Hour,
			},
			PreparePaths: func(t *testing.T) (string, string) {
				return "/nonexistent/cert.pem", "/nonexistent/key.pem"
			},
			ExpectedErr: "write certificate file",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			certPath, keyPath := tc.PreparePaths(t)

			err := pkgTls.GenerateSelfSignedKeyPair(certPath, keyPath, tc.Cfg)

			if tc.ExpectedErr != "" {
				assert.ErrorContains(err, tc.ExpectedErr)
				return
			}

			require.NoError(t, err)

			pair, err := tls.LoadX509KeyPair(certPath, keyPath)
			require.NoError(t, err)

			cert, err := x509.ParseCertificate(pair.Certificate[0])
			require.NoError(t, err)

			assert.Equal(tc.Cfg.CommonName, cert.Subject.CommonName)

			key, ok := cert.PublicKey.(*rsa.PublicKey)
			require.True(t, ok)
			assert.Equal(4096, key.N.BitLen())

			assert.WithinDuration(time.Now().Add(tc.Cfg.Duration), cert.NotAfter, time.Minute)
		})
	}
}
