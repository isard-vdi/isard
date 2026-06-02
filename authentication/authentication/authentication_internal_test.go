package authentication

import (
	"errors"
	"net/url"
	"testing"

	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/providermanager"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
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
				m.On("SAML", "default", "").Return(nil)
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

			result := a.SAML(tc.CategoryID, "")
			assert.Nil(result)
		})
	}
}

func TestHealthcheck(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB              func(*r.Mock)
		PrepareAPI             func(*apiv4.MockInvoker)
		PrepareProviderManager func(*testing.T) *providermanager.MockProvidermanager
		ExpectedErr            string
	}{
		"should work as expected": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Expr(1)).Return(1, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("APIVersion", mock.AnythingOfType("*context.cancelCtx")).Return(&apiv4.ApiVersion{}, nil)
			},
			PrepareProviderManager: func(t *testing.T) *providermanager.MockProvidermanager {
				m := providermanager.NewMockProvidermanager(t)
				m.On("Healthcheck", mock.AnythingOfType("*context.cancelCtx")).Return(nil)
				return m
			},
		},
		"should return an error if the DB ping fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Expr(1)).Return(nil, errors.New("connection refused"))
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {},
			PrepareProviderManager: func(t *testing.T) *providermanager.MockProvidermanager {
				return providermanager.NewMockProvidermanager(t)
			},
			ExpectedErr: "ping the DB: connection refused",
		},
		"should return an error if the API ping fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Expr(1)).Return(1, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("APIVersion", mock.AnythingOfType("*context.cancelCtx")).Return(nil, errors.New("connection refused"))
			},
			PrepareProviderManager: func(t *testing.T) *providermanager.MockProvidermanager {
				return providermanager.NewMockProvidermanager(t)
			},
			ExpectedErr: "ping the API: connection refused",
		},
		"should return an error if the provider manager fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Expr(1)).Return(1, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("APIVersion", mock.AnythingOfType("*context.cancelCtx")).Return(&apiv4.ApiVersion{}, nil)
			},
			PrepareProviderManager: func(t *testing.T) *providermanager.MockProvidermanager {
				m := providermanager.NewMockProvidermanager(t)
				m.On("Healthcheck", mock.AnythingOfType("*context.cancelCtx")).Return(errors.New("connection refused"))
				return m
			},
			ExpectedErr: "connection refused",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			dbMock := r.NewMock()
			tc.PrepareDB(dbMock)

			apiMock := apiv4.NewMockInvoker(t)
			tc.PrepareAPI(apiMock)

			pm := tc.PrepareProviderManager(t)
			a := &Authentication{
				Log:        log.New("test", "debug"),
				DB:         dbMock,
				API:        apiMock,
				prvManager: pm,
			}

			err := a.Healthcheck(t.Context())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			dbMock.AssertExpectations(t)
			pm.AssertExpectations(t)
		})
	}
}
