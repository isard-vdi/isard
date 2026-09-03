package certwatch_test

import (
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"testing"

	certwatch "gitlab.com/isard/isardvdi/haproxy-sync/cert-watch"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestCertWatchCerts(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		CrtList     string
		WriteFile   bool
		MakeDir     bool
		Expected    []string
		ExpectedErr string
	}{
		"should return no certificates if the crt-list doesn't exist yet": {
			Expected: []string{},
		},
		"should work as expected": {
			CrtList:   "/certs/chain.pem\n",
			WriteFile: true,
			Expected:  []string{"/certs/chain.pem"},
		},
		"should ignore empty lines and comments": {
			CrtList:   "# the portal certificate\n\n/certs/chain.pem\n\n",
			WriteFile: true,
			Expected:  []string{"/certs/chain.pem"},
		},
		"should only take the certificate path if the entry has sni filters": {
			CrtList:   "/certs/chain.pem !*.example.com\n",
			WriteFile: true,
			Expected:  []string{"/certs/chain.pem"},
		},
		"should return an error if the crt-list can't be read": {
			MakeDir:     true,
			ExpectedErr: "read the crt-list",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			path := filepath.Join(t.TempDir(), "crt-list.cfg")
			if tc.WriteFile {
				require.NoError(t, os.WriteFile(path, []byte(tc.CrtList), 0o644))
			}

			if tc.MakeDir {
				require.NoError(t, os.Mkdir(path, 0o755))
			}

			logger := log.New("test", "debug")
			hapMock := haproxy.NewMockHaproxy(t)

			c := certwatch.NewCertWatch(logger, hapMock, path)

			certs, err := c.Certs()

			if tc.ExpectedErr != "" {
				assert.ErrorContains(err, tc.ExpectedErr)

				hapMock.AssertExpectations(t)

				return
			}

			assert.NoError(err)
			assert.Equal(tc.Expected, certs)

			hapMock.AssertExpectations(t)
		})
	}
}

func TestCertWatchUpdate(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		WriteFile        bool
		PrepareMock      func(m *haproxy.MockHaproxy, path string)
		ExpectedErr      string
		ExpectedNotExist bool
	}{
		"should work as expected": {
			WriteFile: true,
			PrepareMock: func(m *haproxy.MockHaproxy, path string) {
				m.On("SetSslCert", path, []byte("pem contents")).Return(nil)
				m.On("CommitSslCert", path).Return(nil)
			},
		},
		"should return an error if the certificate can't be read": {
			ExpectedNotExist: true,
		},
		"should return an error if the certificate can't be loaded": {
			WriteFile: true,
			PrepareMock: func(m *haproxy.MockHaproxy, path string) {
				m.On("SetSslCert", path, []byte("pem contents")).Return(errors.New("set ssl cert: haproxy error"))
			},
			ExpectedErr: "set ssl cert: haproxy error",
		},
		"should return an error if the certificate can't be committed": {
			WriteFile: true,
			PrepareMock: func(m *haproxy.MockHaproxy, path string) {
				m.On("SetSslCert", path, []byte("pem contents")).Return(nil)
				m.On("CommitSslCert", path).Return(errors.New("commit ssl cert: haproxy error"))
			},
			ExpectedErr: "commit ssl cert: haproxy error",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			path := filepath.Join(t.TempDir(), "chain.pem")
			if tc.WriteFile {
				require.NoError(t, os.WriteFile(path, []byte("pem contents"), 0o644))
			}

			logger := log.New("test", "debug")
			hapMock := haproxy.NewMockHaproxy(t)
			if tc.PrepareMock != nil {
				tc.PrepareMock(hapMock, path)
			}

			crtListPath := filepath.Join(t.TempDir(), "crt-list.cfg")

			c := certwatch.NewCertWatch(logger, hapMock, crtListPath)

			err := c.Update([]string{path})

			if tc.ExpectedNotExist {
				assert.ErrorIs(err, fs.ErrNotExist)

				hapMock.AssertExpectations(t)

				return
			}

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)

				hapMock.AssertExpectations(t)

				return
			}

			assert.NoError(err)

			hapMock.AssertExpectations(t)
		})
	}
}
