package authentication

import (
	"errors"
	"net/url"
	"testing"

	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/providermanager"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/stretchr/testify/assert"
)

func TestProviders(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareProviderManager func(*testing.T) *providermanager.MockProvidermanager
		CategoryID             string
		Expected               []string
	}{
		"should delegate to provider manager": {
			PrepareProviderManager: func(t *testing.T) *providermanager.MockProvidermanager {
				m := providermanager.NewMockProvidermanager(t)
				m.On("Providers", "default").Return([]string{"form", "local", "saml"})
				return m
			},
			CategoryID: "default",
			Expected:   []string{"form", "local", "saml"},
		},
		"should return empty list when no providers": {
			PrepareProviderManager: func(t *testing.T) *providermanager.MockProvidermanager {
				m := providermanager.NewMockProvidermanager(t)
				m.On("Providers", "empty-cat").Return([]string{})
				return m
			},
			CategoryID: "empty-cat",
			Expected:   []string{},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			a := &Authentication{
				Log:        log.New("test", "debug"),
				BaseURL:    &url.URL{Scheme: "https", Host: "localhost"},
				prvManager: tc.PrepareProviderManager(t),
			}

			result := a.Providers(tc.CategoryID)
			assert.Equal(tc.Expected, result)
		})
	}
}

func TestProvider(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareProviderManager func(*testing.T) *providermanager.MockProvidermanager
		ProviderName           string
		CategoryID             string
		ExpectedName           string
	}{
		"should delegate to provider manager": {
			PrepareProviderManager: func(t *testing.T) *providermanager.MockProvidermanager {
				mockPrv := provider.NewMockProvider(t)
				mockPrv.On("String").Return("local")

				m := providermanager.NewMockProvidermanager(t)
				m.On("Provider", "local", "default").Return(mockPrv)
				return m
			},
			ProviderName: "local",
			CategoryID:   "default",
			ExpectedName: "local",
		},
		"should return unknown for nonexistent provider": {
			PrepareProviderManager: func(t *testing.T) *providermanager.MockProvidermanager {
				mockPrv := provider.NewMockProvider(t)
				mockPrv.On("String").Return("unknown")

				m := providermanager.NewMockProvidermanager(t)
				m.On("Provider", "nonexistent", "default").Return(mockPrv)
				return m
			},
			ProviderName: "nonexistent",
			CategoryID:   "default",
			ExpectedName: "unknown",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			a := &Authentication{
				Log:        log.New("test", "debug"),
				BaseURL:    &url.URL{Scheme: "https", Host: "localhost"},
				prvManager: tc.PrepareProviderManager(t),
			}

			result := a.Provider(tc.ProviderName, tc.CategoryID)
			assert.Equal(tc.ExpectedName, result.String())
		})
	}
}

func TestSAML(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareProviderManager func(*testing.T) *providermanager.MockProvidermanager
		CategoryID             string
	}{
		"should delegate to provider manager and return nil when no SAML": {
			PrepareProviderManager: func(t *testing.T) *providermanager.MockProvidermanager {
				m := providermanager.NewMockProvidermanager(t)
				m.On("SAML", "default").Return(nil)
				return m
			},
			CategoryID: "default",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			a := &Authentication{
				Log:        log.New("test", "debug"),
				BaseURL:    &url.URL{Scheme: "https", Host: "localhost"},
				prvManager: tc.PrepareProviderManager(t),
			}

			result := a.SAML(tc.CategoryID)
			assert.Nil(result)
		})
	}
}

func TestHealthcheck(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareProviderManager func(*testing.T) *providermanager.MockProvidermanager
		ExpectedErr            string
	}{
		"should return nil when healthy": {
			PrepareProviderManager: func(t *testing.T) *providermanager.MockProvidermanager {
				m := providermanager.NewMockProvidermanager(t)
				m.On("Healthcheck").Return(nil)
				return m
			},
		},
		"should return error when unhealthy": {
			PrepareProviderManager: func(t *testing.T) *providermanager.MockProvidermanager {
				m := providermanager.NewMockProvidermanager(t)
				m.On("Healthcheck").Return(errors.New("connection refused"))
				return m
			},
			ExpectedErr: "connection refused",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			a := &Authentication{
				Log:        log.New("test", "debug"),
				BaseURL:    &url.URL{Scheme: "https", Host: "localhost"},
				prvManager: tc.PrepareProviderManager(t),
			}

			err := a.Healthcheck()

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}
		})
	}
}
