package authentication

import (
	"errors"
	"testing"

	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/stretchr/testify/assert"
)

func TestProviderManagerProviders(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareProviders func() map[string]provider.Provider
		Expected         []string
	}{
		"should return form sub-providers and form itself": {
			PrepareProviders: func() map[string]provider.Provider {
				return map[string]provider.Provider{
					types.ProviderUnknown:  &provider.Unknown{},
					types.ProviderExternal: &provider.External{},
					types.ProviderForm:     provider.InitForm(cfg.Authentication{}, provider.InitLocal(nil), nil),
				}
			},
			Expected: []string{"local", "form"},
		},
		"should include SAML when enabled": {
			PrepareProviders: func() map[string]provider.Provider {
				log := log.New("test", "debug")

				return map[string]provider.Provider{
					types.ProviderUnknown:  &provider.Unknown{},
					types.ProviderExternal: &provider.External{},
					types.ProviderForm:     provider.InitForm(cfg.Authentication{}, provider.InitLocal(nil), nil),
					types.ProviderSAML:     provider.InitSAML("", "", log, nil),
				}
			},
			Expected: []string{"local", "form", "saml"},
		},
		"should include Google when enabled": {
			PrepareProviders: func() map[string]provider.Provider {
				return map[string]provider.Provider{
					types.ProviderUnknown:  &provider.Unknown{},
					types.ProviderExternal: &provider.External{},
					types.ProviderForm:     provider.InitForm(cfg.Authentication{}, provider.InitLocal(nil), nil),
					types.ProviderGoogle:   provider.InitGoogle(cfg.Authentication{}),
				}
			},
			Expected: []string{"local", "form", "google"},
		},
		"should include all providers when all are enabled": {
			PrepareProviders: func() map[string]provider.Provider {
				log := log.New("test", "debug")

				return map[string]provider.Provider{
					types.ProviderUnknown:  &provider.Unknown{},
					types.ProviderExternal: &provider.External{},
					types.ProviderForm:     provider.InitForm(cfg.Authentication{}, provider.InitLocal(nil), nil),
					types.ProviderSAML:     provider.InitSAML("", "", log, nil),
					types.ProviderGoogle:   provider.InitGoogle(cfg.Authentication{}),
				}
			},
			Expected: []string{"local", "form", "saml", "google"},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			m := &ProviderManager{
				providers: tc.PrepareProviders(),
			}

			assert.ElementsMatch(tc.Expected, m.Providers())
		})
	}
}

func TestProviderManagerProvider(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		LookupName   string
		ExpectedName string
	}{
		"should return the provider by direct lookup": {
			LookupName:   types.ProviderForm,
			ExpectedName: types.ProviderForm,
		},
		"should fall back to form sub-provider": {
			LookupName:   types.ProviderLocal,
			ExpectedName: types.ProviderLocal,
		},
		"should fall back to unknown for nonexistent provider": {
			LookupName:   "nonexistent",
			ExpectedName: types.ProviderUnknown,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			m := &ProviderManager{
				providers: map[string]provider.Provider{
					types.ProviderUnknown: &provider.Unknown{},
					types.ProviderForm:    provider.InitForm(cfg.Authentication{}, provider.InitLocal(nil), nil),
				},
			}

			p := m.Provider(tc.LookupName)

			assert.Equal(tc.ExpectedName, p.String())
		})
	}
}

func TestProviderManagerHealthcheck(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareProviders func(*testing.T) map[string]provider.Provider
		ExpectedErr      string
	}{
		"should return nil when all providers are healthy": {
			PrepareProviders: func(_ *testing.T) map[string]provider.Provider {
				return map[string]provider.Provider{
					types.ProviderUnknown: &provider.Unknown{},
				}
			},
		},
		"should return an error when a provider is unhealthy": {
			PrepareProviders: func(t *testing.T) map[string]provider.Provider {
				mockPrv := provider.NewMockProvider(t)
				mockPrv.On("Healthcheck").Return(errors.New("connection refused"))
				mockPrv.On("String").Return("mock")

				return map[string]provider.Provider{
					"mock": mockPrv,
				}
			},
			ExpectedErr: "connection refused",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			log := log.New("test", "debug")

			m := &ProviderManager{
				log:       log,
				providers: tc.PrepareProviders(t),
			}

			err := m.Healthcheck()

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}
		})
	}
}

func TestProviderManagerSAML(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareProviders func() map[string]provider.Provider
	}{
		"should return the SAML middleware when the SAML provider is present": {
			PrepareProviders: func() map[string]provider.Provider {
				log := log.New("test", "debug")

				return map[string]provider.Provider{
					types.ProviderSAML: provider.InitSAML("", "", log, nil),
				}
			},
		},
		"should return nil when the SAML provider is not present": {
			PrepareProviders: func() map[string]provider.Provider {
				return map[string]provider.Provider{}
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			m := &ProviderManager{
				providers: tc.PrepareProviders(),
			}

			assert.Nil(m.SAML())
		})
	}
}
