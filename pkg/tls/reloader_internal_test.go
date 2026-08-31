package tls

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/fsnotify/fsnotify"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestKeyPairReloaderGetCertificate(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareChange      func(t *testing.T, certPath, keyPath string)
		ExpectedChanged    bool
		ExpectedCommonName string
		ExpectedErr        string
	}{
		"should work as expected": {
			PrepareChange: func(t *testing.T, certPath, keyPath string) {
				cfg := CertConfig{
					CommonName: "new.example.com",
					Duration:   time.Hour,
				}

				require.NoError(t, GenerateSelfSignedKeyPair(certPath, keyPath, cfg))
			},
			ExpectedChanged:    true,
			ExpectedCommonName: "new.example.com",
		},
		"should keep serving the previous certificate if the new one can't be read": {
			PrepareChange: func(t *testing.T, certPath, keyPath string) {
				require.NoError(t, os.WriteFile(certPath, []byte("not a pem"), 0o644))
			},
			ExpectedChanged:    false,
			ExpectedCommonName: "old.example.com",
			ExpectedErr:        "read tls certificate: tls: failed to find any PEM data in certificate input",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			dir := t.TempDir()
			certPath := filepath.Join(dir, "chain.pem")
			keyPath := filepath.Join(dir, "chain.key")

			cfg := CertConfig{
				CommonName: "old.example.com",
				Duration:   time.Hour,
			}

			require.NoError(t, GenerateSelfSignedKeyPair(certPath, keyPath, cfg))

			logger := log.New("test", "debug")

			kpr, err := NewKeyPairReloader(logger, certPath, keyPath)
			require.NoError(t, err)

			cert, err := kpr.GetCertificate(nil)
			require.NoError(t, err)
			require.NotNil(t, cert.Leaf)
			assert.Equal("old.example.com", cert.Leaf.Subject.CommonName)

			tc.PrepareChange(t, certPath, keyPath)

			changed, err := kpr.poll.Check()

			assert.Equal(tc.ExpectedChanged, changed)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			cert, err = kpr.GetCertificate(nil)
			require.NoError(t, err)
			require.NotNil(t, cert.Leaf)
			assert.Equal(tc.ExpectedCommonName, cert.Leaf.Subject.CommonName)
		})
	}
}

func TestKeyPairReloaderStart(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareFiles       func(t *testing.T, certPath, keyPath string)
		PrepareChange      func(t *testing.T, certPath, keyPath string)
		ExpectedCommonName string
		ExpectedErr        string
	}{
		"should reload the certificate if it changes on disk": {
			PrepareChange: func(t *testing.T, certPath, keyPath string) {
				cfg := CertConfig{
					CommonName: "new.example.com",
					Duration:   time.Hour,
				}

				require.NoError(t, GenerateSelfSignedKeyPair(certPath, keyPath, cfg))
			},
			ExpectedCommonName: "new.example.com",
		},
		"should rewatch and reload the certificate if it's replaced": {
			PrepareChange: func(t *testing.T, certPath, keyPath string) {
				staging := t.TempDir()
				stagedCertPath := filepath.Join(staging, "chain.pem")
				stagedKeyPath := filepath.Join(staging, "chain.key")

				cfg := CertConfig{
					CommonName: "replaced.example.com",
					Duration:   time.Hour,
				}

				require.NoError(t, GenerateSelfSignedKeyPair(stagedCertPath, stagedKeyPath, cfg))

				require.NoError(t, os.Rename(stagedKeyPath, keyPath))
				require.NoError(t, os.Rename(stagedCertPath, certPath))
			},
			ExpectedCommonName: "replaced.example.com",
		},
		"should return an error if the certificate can't be watched": {
			PrepareFiles: func(t *testing.T, certPath, keyPath string) {
				require.NoError(t, os.Remove(certPath))
			},
			ExpectedErr: "to the filesystem watcher: no such file or directory",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			dir := t.TempDir()
			certPath := filepath.Join(dir, "chain.pem")
			keyPath := filepath.Join(dir, "chain.key")

			cfg := CertConfig{
				CommonName: "old.example.com",
				Duration:   time.Hour,
			}

			require.NoError(t, GenerateSelfSignedKeyPair(certPath, keyPath, cfg))

			logger := log.New("test", "debug")

			kpr, err := NewKeyPairReloader(logger, certPath, keyPath)
			require.NoError(t, err)

			if tc.PrepareFiles != nil {
				tc.PrepareFiles(t, certPath, keyPath)
			}

			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()

			done := make(chan error, 1)
			go func() {
				done <- kpr.Start(ctx)
			}()

			if tc.ExpectedErr != "" {
				select {
				case err := <-done:
					assert.ErrorContains(err, tc.ExpectedErr)

				case <-time.After(10 * time.Second):
					t.Fatal("Start never returned the filesystem watch error")
				}

				// Start owns the watcher, so it has to close it before giving up on
				// it, otherwise the inotify descriptor is leaked.
				assert.ErrorIs(kpr.watcher.Add(keyPath), fsnotify.ErrClosed)

				return
			}

			require.Eventually(t, func() bool {
				kpr.poll.mux.Lock()
				defer kpr.poll.mux.Unlock()

				return len(kpr.poll.hashes) == 2
			}, 10*time.Second, 10*time.Millisecond)

			tc.PrepareChange(t, certPath, keyPath)

			assert.Eventually(func() bool {
				cert, err := kpr.GetCertificate(nil)
				if err != nil || cert.Leaf == nil {
					return false
				}

				return cert.Leaf.Subject.CommonName == tc.ExpectedCommonName
			}, 10*time.Second, 10*time.Millisecond)

			cancel()

			select {
			case err := <-done:
				assert.NoError(err)

			case <-time.After(10 * time.Second):
				t.Fatal("Start never returned after the context was cancelled")
			}
		})
	}
}
