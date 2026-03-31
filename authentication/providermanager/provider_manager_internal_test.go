package providermanager

import (
	"context"
	"errors"
	"net/http"
	"sync"
	"testing"
	"testing/synctest"
	"time"

	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

var noNetworkClient = &http.Client{
	Transport: roundTripperFunc(func(*http.Request) (*http.Response, error) {
		return nil, errors.New("no network in tests")
	}),
}

type roundTripperFunc func(*http.Request) (*http.Response, error)

func (f roundTripperFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return f(req)
}

func TestProviderManagerProviders(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareManager func() *ProviderManager
		CategoryID     string
		Expected       []string
	}{
		"should return form sub-providers and form itself": {
			PrepareManager: func() *ProviderManager {
				return &ProviderManager{
					log:                         log.New("test", "debug"),
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown:  &provider.Unknown{},
							types.ProviderExternal: provider.InitExternal(nil),
							types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log.New("test", "debug"), provider.InitLocal(nil), nil),
						},
					},
					categories: map[string]*providerSet{},
				}
			},
			Expected: []string{"form", "local"},
		},
		"should not include form when it has no sub-providers": {
			PrepareManager: func() *ProviderManager {
				return &ProviderManager{
					log:                         log.New("test", "debug"),
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown:  &provider.Unknown{},
							types.ProviderExternal: provider.InitExternal(nil),
							types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log.New("test", "debug"), nil, nil),
						},
					},
					categories: map[string]*providerSet{},
				}
			},
			Expected: []string{},
		},
		"should include SAML when enabled": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				return &ProviderManager{
					log:                         log,
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown:  &provider.Unknown{},
							types.ProviderExternal: provider.InitExternal(nil),
							types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
							types.ProviderSAML:     provider.InitSAML("", "", nil, log, nil, nil),
						},
					},
					categories: map[string]*providerSet{},
				}
			},
			Expected: []string{"form", "local", "saml"},
		},
		"should include Google when enabled": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				return &ProviderManager{
					log:                         log,
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown:  &provider.Unknown{},
							types.ProviderExternal: provider.InitExternal(nil),
							types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
							types.ProviderGoogle:   provider.InitGoogle(cfg.Authentication{}),
						},
					},
					categories: map[string]*providerSet{},
				}
			},
			Expected: []string{"form", "google", "local"},
		},
		"should include all providers when all are enabled": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				return &ProviderManager{
					log:                         log,
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown:  &provider.Unknown{},
							types.ProviderExternal: provider.InitExternal(nil),
							types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
							types.ProviderSAML:     provider.InitSAML("", "", nil, log, nil, nil),
							types.ProviderGoogle:   provider.InitGoogle(cfg.Authentication{}),
						},
					},
					categories: map[string]*providerSet{},
				}
			},
			Expected: []string{"form", "google", "local", "saml"},
		},
		"should merge category providers with global providers": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				return &ProviderManager{
					log:                         log,
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown:  &provider.Unknown{},
							types.ProviderExternal: provider.InitExternal(nil),
							types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
							types.ProviderSAML:     provider.InitSAML("", "", nil, log, nil, nil),
							types.ProviderGoogle:   provider.InitGoogle(cfg.Authentication{}),
						},
					},
					categories: map[string]*providerSet{
						"cat1": {
							providers: map[string]provider.Provider{
								types.ProviderUnknown:  &provider.Unknown{},
								types.ProviderExternal: provider.InitExternal(nil),
								types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
							},
						},
					},
				}
			},
			CategoryID: "cat1",
			Expected:   []string{"form", "google", "local", "saml"},
		},
		"should return category providers merged with global providers": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				return &ProviderManager{
					log:                         log,
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown:  &provider.Unknown{},
							types.ProviderExternal: provider.InitExternal(nil),
							types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
							types.ProviderSAML:     provider.InitSAML("", "", nil, log, nil, nil),
						},
					},
					categories: map[string]*providerSet{
						"cat1": {
							providers: map[string]provider.Provider{
								types.ProviderUnknown:  &provider.Unknown{},
								types.ProviderExternal: provider.InitExternal(nil),
								types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
							},
						},
					},
				}
			},
			CategoryID: "cat1",
			Expected:   []string{"form", "local", "saml"},
		},
		"should fallback to global providers when category has no specific providers": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				return &ProviderManager{
					log:                         log,
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown:  &provider.Unknown{},
							types.ProviderExternal: provider.InitExternal(nil),
							types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
							types.ProviderSAML:     provider.InitSAML("", "", nil, log, nil, nil),
						},
					},
					categories: map[string]*providerSet{},
				}
			},
			CategoryID: "nonexistent",
			Expected:   []string{"form", "local", "saml"},
		},
		"should exclude disabled provider from merged list": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				m := &ProviderManager{
					log:                         log,
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown:  &provider.Unknown{},
							types.ProviderExternal: provider.InitExternal(nil),
							types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
							types.ProviderSAML:     provider.InitSAML("", "", nil, log, nil, nil),
						},
					},
					categories: map[string]*providerSet{
						"cat1": {
							providers: map[string]provider.Provider{
								types.ProviderUnknown:  &provider.Unknown{},
								types.ProviderExternal: provider.InitExternal(nil),
								types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
							},
						},
					},
				}
				m.handleCategoryDisabledProviderChange("cat1", types.ProviderSAML, true)

				return m
			},
			CategoryID: "cat1",
			Expected:   []string{"form", "local"},
		},
		"should exclude disabled provider even when category has no providerSet": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				m := &ProviderManager{
					log:                         log,
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown:  &provider.Unknown{},
							types.ProviderExternal: provider.InitExternal(nil),
							types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
							types.ProviderSAML:     provider.InitSAML("", "", nil, log, nil, nil),
							types.ProviderGoogle:   provider.InitGoogle(cfg.Authentication{}),
						},
					},
					categories: map[string]*providerSet{},
				}
				m.handleCategoryDisabledProviderChange("cat1", types.ProviderSAML, true)

				return m
			},
			CategoryID: "cat1",
			Expected:   []string{"form", "google", "local"},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			m := tc.PrepareManager()

			result := m.Providers(tc.CategoryID)
			assert.Equal(tc.Expected, result)
		})
	}
}

func TestProviderManagerProvider(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareManager func() *ProviderManager
		LookupName     string
		CategoryID     string
		ExpectedName   string
	}{
		"should return the provider by direct lookup": {
			PrepareManager: func() *ProviderManager {
				return &ProviderManager{
					log:                         log.New("test", "debug"),
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown: &provider.Unknown{},
							types.ProviderForm:    provider.InitForm(cfg.Authentication{}, log.New("test", "debug"), provider.InitLocal(nil), nil),
						},
					},
					categories: map[string]*providerSet{},
				}
			},
			LookupName:   types.ProviderForm,
			ExpectedName: types.ProviderForm,
		},
		"should fall back to form sub-provider": {
			PrepareManager: func() *ProviderManager {
				return &ProviderManager{
					log:                         log.New("test", "debug"),
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown: &provider.Unknown{},
							types.ProviderForm:    provider.InitForm(cfg.Authentication{}, log.New("test", "debug"), provider.InitLocal(nil), nil),
						},
					},
					categories: map[string]*providerSet{},
				}
			},
			LookupName:   types.ProviderLocal,
			ExpectedName: types.ProviderLocal,
		},
		"should fall back to unknown for nonexistent provider": {
			PrepareManager: func() *ProviderManager {
				return &ProviderManager{
					log:                         log.New("test", "debug"),
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown: &provider.Unknown{},
							types.ProviderForm:    provider.InitForm(cfg.Authentication{}, log.New("test", "debug"), provider.InitLocal(nil), nil),
						},
					},
					categories: map[string]*providerSet{},
				}
			},
			LookupName:   "nonexistent",
			ExpectedName: types.ProviderUnknown,
		},
		"should fall back to global for provider not in category scope": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				return &ProviderManager{
					log:                         log,
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown: &provider.Unknown{},
							types.ProviderForm:    provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
							types.ProviderSAML:    provider.InitSAML("", "", nil, log, nil, nil),
						},
					},
					categories: map[string]*providerSet{
						"cat1": {
							providers: map[string]provider.Provider{
								types.ProviderUnknown: &provider.Unknown{},
								types.ProviderForm:    provider.InitForm(cfg.Authentication{}, log, nil, nil),
							},
						},
					},
				}
			},
			LookupName:   types.ProviderSAML,
			CategoryID:   "cat1",
			ExpectedName: types.ProviderSAML,
		},
		"should fall back to global provider when not found in category scope": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				return &ProviderManager{
					log:                         log,
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown: &provider.Unknown{},
							types.ProviderForm:    provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
							types.ProviderSAML:    provider.InitSAML("", "", nil, log, nil, nil),
						},
					},
					categories: map[string]*providerSet{
						"cat1": {
							providers: map[string]provider.Provider{
								types.ProviderUnknown: &provider.Unknown{},
								types.ProviderForm:    provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
							},
						},
					},
				}
			},
			LookupName:   types.ProviderSAML,
			CategoryID:   "cat1",
			ExpectedName: types.ProviderSAML,
		},
		"should fall back to global form sub-provider when not found in category form": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				return &ProviderManager{
					log:                         log,
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown: &provider.Unknown{},
							types.ProviderForm:    provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
						},
					},
					categories: map[string]*providerSet{
						"cat1": {
							providers: map[string]provider.Provider{
								types.ProviderUnknown: &provider.Unknown{},
								types.ProviderForm:    provider.InitForm(cfg.Authentication{}, log, nil, nil),
							},
						},
					},
				}
			},
			LookupName:   types.ProviderLocal,
			CategoryID:   "cat1",
			ExpectedName: types.ProviderLocal,
		},
		"should fallback to global provider when category has no specific providers": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				return &ProviderManager{
					log:                         log,
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown: &provider.Unknown{},
							types.ProviderForm:    provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
						},
					},
					categories: map[string]*providerSet{},
				}
			},
			LookupName:   types.ProviderLocal,
			CategoryID:   "nonexistent",
			ExpectedName: types.ProviderLocal,
		},
		"should not fall back to global when provider is explicitly disabled in category": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				m := &ProviderManager{
					log:                         log,
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown: &provider.Unknown{},
							types.ProviderForm:    provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
							types.ProviderSAML:    provider.InitSAML("", "", nil, log, nil, nil),
						},
					},
					categories: map[string]*providerSet{
						"cat1": {
							providers: map[string]provider.Provider{
								types.ProviderUnknown: &provider.Unknown{},
								types.ProviderForm:    provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
							},
						},
					},
				}
				m.handleCategoryDisabledProviderChange("cat1", types.ProviderSAML, true)

				return m
			},
			LookupName:   types.ProviderSAML,
			CategoryID:   "cat1",
			ExpectedName: types.ProviderUnknown,
		},
		"should not fall back to global form sub-provider when disabled in category": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				m := &ProviderManager{
					log:                         log,
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown: &provider.Unknown{},
							types.ProviderForm:    provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
						},
					},
					categories: map[string]*providerSet{
						"cat1": {
							providers: map[string]provider.Provider{
								types.ProviderUnknown: &provider.Unknown{},
								types.ProviderForm:    provider.InitForm(cfg.Authentication{}, log, nil, nil),
							},
						},
					},
				}
				m.handleCategoryDisabledProviderChange("cat1", types.ProviderLocal, true)

				return m
			},
			LookupName:   types.ProviderLocal,
			CategoryID:   "cat1",
			ExpectedName: types.ProviderUnknown,
		},
		"should not fall back when category has no providerSet but provider is disabled": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				m := &ProviderManager{
					log:                         log,
					categoriesDisabledProviders: map[string]map[string]bool{},
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown: &provider.Unknown{},
							types.ProviderForm:    provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
							types.ProviderSAML:    provider.InitSAML("", "", nil, log, nil, nil),
						},
					},
					categories: map[string]*providerSet{},
				}
				m.handleCategoryDisabledProviderChange("cat1", types.ProviderSAML, true)

				return m
			},
			LookupName:   types.ProviderSAML,
			CategoryID:   "cat1",
			ExpectedName: types.ProviderUnknown,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			m := tc.PrepareManager()

			p := m.Provider(tc.LookupName, tc.CategoryID)

			assert.Equal(tc.ExpectedName, p.String())
		})
	}
}

func TestProviderManagerHealthcheck(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareManager func(*testing.T) *ProviderManager
		ExpectedErr    string
	}{
		"should return nil when all providers are healthy": {
			PrepareManager: func(_ *testing.T) *ProviderManager {
				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown: &provider.Unknown{},
						},
					},
					categories:      map[string]*providerSet{},
					brandingDomains: map[string]categoryBrandingDomainChange{},
				}
			},
		},
		"should return an error when a global provider is unhealthy": {
			PrepareManager: func(t *testing.T) *ProviderManager {
				mockPrv := provider.NewMockProvider(t)
				mockPrv.On("Healthcheck").Return(errors.New("connection refused"))
				mockPrv.On("String").Return("mock")

				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{
							"mock": mockPrv,
						},
					},
					categories: map[string]*providerSet{},
				}
			},
			ExpectedErr: "connection refused",
		},
		"should return an error when a category provider is unhealthy": {
			PrepareManager: func(t *testing.T) *ProviderManager {
				mockPrv := provider.NewMockProvider(t)
				mockPrv.On("Healthcheck").Return(errors.New("category connection refused"))
				mockPrv.On("String").Return("mock")

				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown: &provider.Unknown{},
						},
					},
					categories: map[string]*providerSet{
						"cat1": {
							providers: map[string]provider.Provider{
								"mock": mockPrv,
							},
						},
					},
				}
			},
			ExpectedErr: "category connection refused",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			m := tc.PrepareManager(t)

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
		PrepareManager func() *ProviderManager
		CategoryID     string
	}{
		"should return nil when the SAML provider is not present": {
			PrepareManager: func() *ProviderManager {
				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{},
					},
					categories: map[string]*providerSet{},
				}
			},
		},
		"should return nil when the SAML provider has no middleware configured": {
			PrepareManager: func() *ProviderManager {
				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderSAML: provider.InitSAML("", "", nil, log.New("test", "debug"), nil, nil),
						},
					},
					categories:      map[string]*providerSet{},
					brandingDomains: map[string]categoryBrandingDomainChange{},
				}
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			m := tc.PrepareManager()

			assert.Nil(m.SAML(tc.CategoryID, ""))
		})
	}
}

func TestProviderManagerEnableProvider(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareManager    func() *ProviderManager
		EnableProvider    string
		CategoryID        *string
		ExpectedProviders []string
		ExpectedFormSub   []string
		ExpectedWatchers  []string
	}{
		"should enable local provider": {
			PrepareManager: func() *ProviderManager {
				return InitProviderManager(cfg.Authentication{}, log.New("test", "debug"), nil)
			},
			EnableProvider:   types.ProviderLocal,
			ExpectedFormSub:  []string{"local"},
			ExpectedWatchers: []string{},
		},
		"should enable ldap provider": {
			PrepareManager: func() *ProviderManager {
				return InitProviderManager(cfg.Authentication{}, log.New("test", "debug"), nil)
			},
			EnableProvider:   types.ProviderLDAP,
			ExpectedFormSub:  []string{"ldap"},
			ExpectedWatchers: []string{"ldap"},
		},
		"should enable saml provider": {
			PrepareManager: func() *ProviderManager {
				return InitProviderManager(cfg.Authentication{}, log.New("test", "debug"), nil)
			},
			EnableProvider:    types.ProviderSAML,
			ExpectedProviders: []string{"saml"},
			ExpectedWatchers:  []string{"saml"},
		},
		"should enable google provider": {
			PrepareManager: func() *ProviderManager {
				return InitProviderManager(cfg.Authentication{}, log.New("test", "debug"), nil)
			},
			EnableProvider:    types.ProviderGoogle,
			ExpectedProviders: []string{"google"},
			ExpectedWatchers:  []string{"google"},
		},
		"should not enable provider already in providers map": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				m := InitProviderManager(cfg.Authentication{}, log, nil)
				m.global.providers[types.ProviderSAML] = provider.InitSAML("", "", nil, log, nil, nil)

				return m
			},
			EnableProvider:    types.ProviderSAML,
			ExpectedProviders: []string{"saml"},
			ExpectedWatchers:  []string{},
		},
		"should not enable local already in form": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				local := provider.InitLocal(nil)

				m := InitProviderManager(cfg.Authentication{}, log, nil)
				m.global.providers[types.ProviderForm] = provider.InitForm(cfg.Authentication{}, log, local, nil)

				return m
			},
			EnableProvider:   types.ProviderLocal,
			ExpectedFormSub:  []string{"local"},
			ExpectedWatchers: []string{},
		},
		"should not enable ldap already in form": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				ldap := provider.InitLDAP("", log, nil)

				m := InitProviderManager(cfg.Authentication{}, log, nil)
				m.global.providers[types.ProviderForm] = provider.InitForm(cfg.Authentication{}, log, nil, ldap)

				return m
			},
			EnableProvider:   types.ProviderLDAP,
			ExpectedFormSub:  []string{"ldap"},
			ExpectedWatchers: []string{},
		},
		"should not enable unknown provider type": {
			PrepareManager: func() *ProviderManager {
				return InitProviderManager(cfg.Authentication{}, log.New("test", "debug"), nil)
			},
			EnableProvider:   "unknown-type",
			ExpectedWatchers: []string{},
		},
		"should enable local provider for a specific category": {
			PrepareManager: func() *ProviderManager {
				m := InitProviderManager(cfg.Authentication{}, log.New("test", "debug"), nil)

				changesChans := m.cfgWatcher.getOrCreateCategoryChangesChannels("cat1")
				m.cfgWatcher.categoriesChanges["cat1"] = changesChans

				return m
			},
			EnableProvider:   types.ProviderLocal,
			CategoryID:       strPtr("cat1"),
			ExpectedFormSub:  []string{"local"},
			ExpectedWatchers: []string{},
		},
		"should enable saml provider for a specific category": {
			PrepareManager: func() *ProviderManager {
				m := InitProviderManager(cfg.Authentication{}, log.New("test", "debug"), nil)

				changesChans := m.cfgWatcher.getOrCreateCategoryChangesChannels("cat1")
				m.cfgWatcher.categoriesChanges["cat1"] = changesChans

				return m
			},
			EnableProvider:    types.ProviderSAML,
			CategoryID:        strPtr("cat1"),
			ExpectedProviders: []string{"saml"},
			ExpectedWatchers:  []string{"saml"},
		},
		"should log error when category changes channels not found": {
			PrepareManager: func() *ProviderManager {
				return InitProviderManager(cfg.Authentication{}, log.New("test", "debug"), nil)
			},
			EnableProvider:   types.ProviderLocal,
			CategoryID:       strPtr("no-channels"),
			ExpectedWatchers: []string{},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()

			var wg sync.WaitGroup

			m := tc.PrepareManager()

			m.enableProvider(ctx, &wg, tc.EnableProvider, tc.CategoryID)

			scope := &m.global
			if tc.CategoryID != nil {
				scope = m.categories[*tc.CategoryID]
			}

			if tc.ExpectedFormSub != nil {
				f := scope.providers[types.ProviderForm].(*provider.Form)
				assert.ElementsMatch(tc.ExpectedFormSub, f.Providers())
			}

			if tc.ExpectedProviders != nil {
				for _, p := range tc.ExpectedProviders {
					assert.NotNil(scope.providers[p])
				}
			}

			expectedWatchers := tc.ExpectedWatchers
			if expectedWatchers == nil {
				expectedWatchers = []string{}
			}

			actualWatchers := []string{}
			for k := range scope.watcherCancels {
				actualWatchers = append(actualWatchers, k)
			}

			assert.ElementsMatch(expectedWatchers, actualWatchers)

			cancel()
			wg.Wait()
		})
	}
}

func strPtr(s string) *string {
	return &s
}

func TestProviderManagerDisableProvider(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareManager     func() *ProviderManager
		DisableProvider    string
		CategoryID         *string
		ExpectedFormSub    []string
		ExpectedAbsent     []string
		ExpectedWatchers   []string
		ExpectCategoryGone bool
	}{
		"should disable local provider from form": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				local := provider.InitLocal(nil)

				m := InitProviderManager(cfg.Authentication{}, log, nil)
				m.global.providers[types.ProviderForm] = provider.InitForm(cfg.Authentication{}, log, local, nil)

				return m
			},
			DisableProvider:  types.ProviderLocal,
			ExpectedFormSub:  []string{},
			ExpectedWatchers: []string{},
		},
		"should disable ldap provider from form and cancel watcher": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				ldap := provider.InitLDAP("", log, nil)

				m := InitProviderManager(cfg.Authentication{}, log, nil)
				m.global.providers[types.ProviderForm] = provider.InitForm(cfg.Authentication{}, log, nil, ldap)

				_, cancel := context.WithCancel(context.Background())
				m.global.watcherCancels[types.ProviderLDAP] = cancel

				return m
			},
			DisableProvider:  types.ProviderLDAP,
			ExpectedFormSub:  []string{},
			ExpectedWatchers: []string{},
		},
		"should disable saml provider from providers map and cancel watcher": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				m := InitProviderManager(cfg.Authentication{}, log, nil)
				m.global.providers[types.ProviderSAML] = provider.InitSAML("", "", nil, log, nil, nil)

				_, cancel := context.WithCancel(context.Background())
				m.global.watcherCancels[types.ProviderSAML] = cancel

				return m
			},
			DisableProvider:  types.ProviderSAML,
			ExpectedAbsent:   []string{"saml"},
			ExpectedWatchers: []string{},
		},
		"should disable google provider from providers map and cancel watcher": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				m := InitProviderManager(cfg.Authentication{}, log, nil)
				m.global.providers[types.ProviderGoogle] = provider.InitGoogle(cfg.Authentication{})

				_, cancel := context.WithCancel(context.Background())
				m.global.watcherCancels[types.ProviderGoogle] = cancel

				return m
			},
			DisableProvider:  types.ProviderGoogle,
			ExpectedAbsent:   []string{"google"},
			ExpectedWatchers: []string{},
		},
		"should not disable nonexistent provider": {
			PrepareManager: func() *ProviderManager {
				return InitProviderManager(cfg.Authentication{}, log.New("test", "debug"), nil)
			},
			DisableProvider:  "nonexistent",
			ExpectedWatchers: []string{},
		},
		"should disable category provider and clean up empty category": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				m := InitProviderManager(cfg.Authentication{}, log, nil)

				_, cancel := context.WithCancel(context.Background())
				m.categories["cat1"] = &providerSet{
					providers: map[string]provider.Provider{
						types.ProviderUnknown:  &provider.Unknown{},
						types.ProviderExternal: provider.InitExternal(nil),
						types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log, nil, nil),
						types.ProviderSAML:     provider.InitSAML("", "", nil, log, nil, nil),
					},
					watcherCancels: map[string]context.CancelFunc{
						types.ProviderSAML: cancel,
					},
				}
				m.cfgWatcher.categoriesChanges["cat1"] = m.cfgWatcher.getOrCreateCategoryChangesChannels("cat1")

				return m
			},
			DisableProvider:    types.ProviderSAML,
			CategoryID:         strPtr("cat1"),
			ExpectedAbsent:     []string{"saml"},
			ExpectCategoryGone: true,
		},
		"should warn when disabling provider from nonexistent category": {
			PrepareManager: func() *ProviderManager {
				return InitProviderManager(cfg.Authentication{}, log.New("test", "debug"), nil)
			},
			DisableProvider: types.ProviderSAML,
			CategoryID:      strPtr("nonexistent"),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			m := tc.PrepareManager()

			m.disableProvider(tc.DisableProvider, tc.CategoryID)

			scope := &m.global
			if tc.CategoryID != nil {
				if tc.ExpectCategoryGone {
					assert.Nil(m.categories[*tc.CategoryID])
					return
				}

				if s, ok := m.categories[*tc.CategoryID]; ok {
					scope = s
				} else {
					return
				}
			}

			if tc.ExpectedFormSub != nil {
				f := scope.providers[types.ProviderForm].(*provider.Form)
				assert.ElementsMatch(tc.ExpectedFormSub, f.Providers())
			}

			if tc.ExpectedAbsent != nil {
				for _, p := range tc.ExpectedAbsent {
					assert.Nil(scope.providers[p])
				}
			}

			actualWatchers := []string{}
			for k := range scope.watcherCancels {
				actualWatchers = append(actualWatchers, k)
			}

			if tc.ExpectedWatchers != nil {
				assert.ElementsMatch(tc.ExpectedWatchers, actualWatchers)
			}
		})
	}
}

func TestProviderManagerHandleProviderChange(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Change          providerChange
		PrepareManager  func(*zerolog.Logger) *ProviderManager
		ExpectedFormSub []string
	}{
		"should enable provider when Enabled is true": {
			Change: providerChange{
				Provider: types.ProviderLocal,
				Enabled:  true,
			},
			PrepareManager: func(log *zerolog.Logger) *ProviderManager {
				return InitProviderManager(cfg.Authentication{}, log, nil)
			},
			ExpectedFormSub: []string{"local"},
		},
		"should disable provider when Enabled is false": {
			Change: providerChange{
				Provider: types.ProviderLocal,
				Enabled:  false,
			},
			PrepareManager: func(log *zerolog.Logger) *ProviderManager {
				local := provider.InitLocal(nil)

				m := InitProviderManager(cfg.Authentication{}, log, nil)
				m.global.providers[types.ProviderForm] = provider.InitForm(cfg.Authentication{}, log, local, nil)

				return m
			},
			ExpectedFormSub: []string{},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()

			var wg sync.WaitGroup

			log := log.New("test", "debug")

			m := tc.PrepareManager(log)

			m.handleProviderChange(ctx, &wg, tc.Change)

			f := m.global.providers[types.ProviderForm].(*provider.Form)
			assert.ElementsMatch(tc.ExpectedFormSub, f.Providers())

			cancel()
			wg.Wait()
		})
	}
}

func TestHandleCategoryDisabledProviderChange(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		InitialDisabled map[string]map[string]bool
		CategoryID      string
		Provider        string
		Disabled        bool
		Expected        map[string]map[string]bool
	}{
		"should add disabled provider to new category": {
			InitialDisabled: map[string]map[string]bool{},
			CategoryID:      "cat1",
			Provider:        types.ProviderSAML,
			Disabled:        true,
			Expected: map[string]map[string]bool{
				"cat1": {types.ProviderSAML: true},
			},
		},
		"should add disabled provider to existing category": {
			InitialDisabled: map[string]map[string]bool{
				"cat1": {types.ProviderSAML: true},
			},
			CategoryID: "cat1",
			Provider:   types.ProviderLDAP,
			Disabled:   true,
			Expected: map[string]map[string]bool{
				"cat1": {types.ProviderSAML: true, types.ProviderLDAP: true},
			},
		},
		"should remove disabled provider and clean up empty category": {
			InitialDisabled: map[string]map[string]bool{
				"cat1": {types.ProviderSAML: true},
			},
			CategoryID: "cat1",
			Provider:   types.ProviderSAML,
			Disabled:   false,
			Expected:   map[string]map[string]bool{},
		},
		"should remove disabled provider but keep category with remaining providers": {
			InitialDisabled: map[string]map[string]bool{
				"cat1": {types.ProviderSAML: true, types.ProviderLDAP: true},
			},
			CategoryID: "cat1",
			Provider:   types.ProviderSAML,
			Disabled:   false,
			Expected: map[string]map[string]bool{
				"cat1": {types.ProviderLDAP: true},
			},
		},
		"should be a no-op when removing from non-existent category": {
			InitialDisabled: map[string]map[string]bool{},
			CategoryID:      "nonexistent",
			Provider:        types.ProviderSAML,
			Disabled:        false,
			Expected:        map[string]map[string]bool{},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			logger := log.New("test", "debug")
			m := &ProviderManager{
				log:                         logger,
				categoriesDisabledProviders: tc.InitialDisabled,
			}

			m.handleCategoryDisabledProviderChange(tc.CategoryID, tc.Provider, tc.Disabled)

			assert.Equal(tc.Expected, m.categoriesDisabledProviders)
		})
	}
}

func TestIsProvidersEmpty(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Providers map[string]provider.Provider
		Expected  bool
	}{
		"should return true when only unknown and external": {
			Providers: map[string]provider.Provider{
				types.ProviderUnknown:  &provider.Unknown{},
				types.ProviderExternal: provider.InitExternal(nil),
			},
			Expected: true,
		},
		"should return true when form has no sub-providers": {
			Providers: map[string]provider.Provider{
				types.ProviderUnknown:  &provider.Unknown{},
				types.ProviderExternal: provider.InitExternal(nil),
				types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log.New("test", "debug"), nil, nil),
			},
			Expected: true,
		},
		"should return false when form has sub-providers": {
			Providers: map[string]provider.Provider{
				types.ProviderUnknown:  &provider.Unknown{},
				types.ProviderExternal: provider.InitExternal(nil),
				types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log.New("test", "debug"), provider.InitLocal(nil), nil),
			},
			Expected: false,
		},
		"should return false when SAML is present": {
			Providers: map[string]provider.Provider{
				types.ProviderUnknown:  &provider.Unknown{},
				types.ProviderExternal: provider.InitExternal(nil),
				types.ProviderSAML:     provider.InitSAML("", "", nil, log.New("test", "debug"), nil, nil),
			},
			Expected: false,
		},
		"should return false when Google is present": {
			Providers: map[string]provider.Provider{
				types.ProviderUnknown:  &provider.Unknown{},
				types.ProviderExternal: provider.InitExternal(nil),
				types.ProviderGoogle:   provider.InitGoogle(cfg.Authentication{}),
			},
			Expected: false,
		},
		"should return true when map is empty": {
			Providers: map[string]provider.Provider{},
			Expected:  true,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			result := isProvidersEmpty(tc.Providers)
			assert.Equal(tc.Expected, result)
		})
	}
}

func TestHandleCategoryBrandingDomainChange(t *testing.T) {
	t.Parallel()

	cases := map[string]struct {
		PrepareManager func(*testing.T) *ProviderManager
		Change         categoryBrandingDomainChange
		CheckAfter     func(*testing.T, *ProviderManager)
	}{
		"should clear branding domain on global provider": {
			PrepareManager: func(t *testing.T) *ProviderManager {
				bap := provider.NewMockBrandingAwareProvider(t)
				bap.On("SetBrandingHost", t.Context(), "cat1", (*string)(nil)).Return(nil)

				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderSAML: bap,
						},
					},
					categories:      map[string]*providerSet{},
					brandingDomains: map[string]categoryBrandingDomainChange{},
				}
			},
			Change: categoryBrandingDomainChange{
				CategoryID:     "cat1",
				Host:           nil,
				Authentication: &model.CategoryAuthentication{},
			},
		},
		"should call SetBrandingHost on custom category provider": {
			PrepareManager: func(t *testing.T) *ProviderManager {
				bap := provider.NewMockBrandingAwareProvider(t)
				host := "branding.example.com"
				bap.On("SetBrandingHost", t.Context(), "cat1", &host).Return(nil)

				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{},
					},
					categories: map[string]*providerSet{
						"cat1": {
							providers: map[string]provider.Provider{
								types.ProviderSAML: bap,
							},
						},
					},
					brandingDomains: map[string]categoryBrandingDomainChange{},
				}
			},
			Change: categoryBrandingDomainChange{
				CategoryID: "cat1",
				Host:       strPtr("branding.example.com"),
				Authentication: &model.CategoryAuthentication{
					SAML: &model.CategoryAuthSAML{
						ConfigSource: model.CategoryAuthenticationConfigSourceCustom,
					},
				},
			},
		},
		"should call SetBrandingHost on global provider when config_source is global": {
			PrepareManager: func(t *testing.T) *ProviderManager {
				bap := provider.NewMockBrandingAwareProvider(t)
				host := "branding.example.com"
				bap.On("SetBrandingHost", t.Context(), "cat1", &host).Return(nil)

				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderSAML: bap,
						},
					},
					categories:      map[string]*providerSet{},
					brandingDomains: map[string]categoryBrandingDomainChange{},
				}
			},
			Change: categoryBrandingDomainChange{
				CategoryID: "cat1",
				Host:       strPtr("branding.example.com"),
				Authentication: &model.CategoryAuthentication{
					SAML: &model.CategoryAuthSAML{
						ConfigSource: model.CategoryAuthenticationConfigSourceGlobal,
					},
				},
			},
		},
		"should call SetBrandingHost on global provider when no provider config exists": {
			PrepareManager: func(t *testing.T) *ProviderManager {
				bap := provider.NewMockBrandingAwareProvider(t)
				host := "branding.example.com"
				bap.On("SetBrandingHost", t.Context(), "cat1", &host).Return(nil)

				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderSAML: bap,
						},
					},
					categories:      map[string]*providerSet{},
					brandingDomains: map[string]categoryBrandingDomainChange{},
				}
			},
			Change: categoryBrandingDomainChange{
				CategoryID:     "cat1",
				Host:           strPtr("branding.example.com"),
				Authentication: &model.CategoryAuthentication{},
			},
		},
		"should skip disabled provider": {
			PrepareManager: func(_ *testing.T) *ProviderManager {
				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderSAML: provider.InitSAML("", "", nil, log.New("test", "debug"), nil, nil),
						},
					},
					categories:      map[string]*providerSet{},
					brandingDomains: map[string]categoryBrandingDomainChange{},
				}
			},
			Change: categoryBrandingDomainChange{
				CategoryID: "cat1",
				Host:       strPtr("branding.example.com"),
				Authentication: &model.CategoryAuthentication{
					SAML: &model.CategoryAuthSAML{
						Disabled: true,
					},
				},
			},
		},
		"should skip providers that do not implement BrandingAwareProvider": {
			PrepareManager: func(_ *testing.T) *ProviderManager {
				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderUnknown: &provider.Unknown{},
						},
					},
					categories:      map[string]*providerSet{},
					brandingDomains: map[string]categoryBrandingDomainChange{},
				}
			},
			Change: categoryBrandingDomainChange{
				CategoryID:     "cat1",
				Host:           strPtr("branding.example.com"),
				Authentication: &model.CategoryAuthentication{},
			},
		},
		"should log error when SetBrandingHost fails": {
			PrepareManager: func(t *testing.T) *ProviderManager {
				bap := provider.NewMockBrandingAwareProvider(t)
				host := "branding.example.com"
				bap.On("SetBrandingHost", t.Context(), "cat1", &host).Return(errors.New("reload failed"))

				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{
							types.ProviderSAML: bap,
						},
					},
					categories:      map[string]*providerSet{},
					brandingDomains: map[string]categoryBrandingDomainChange{},
				}
			},
			Change: categoryBrandingDomainChange{
				CategoryID:     "cat1",
				Host:           strPtr("branding.example.com"),
				Authentication: &model.CategoryAuthentication{},
			},
		},
		"should store branding domain in map": {
			PrepareManager: func(_ *testing.T) *ProviderManager {
				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{},
					},
					categories:      map[string]*providerSet{},
					brandingDomains: map[string]categoryBrandingDomainChange{},
				}
			},
			Change: categoryBrandingDomainChange{
				CategoryID:     "cat1",
				Host:           strPtr("branding.example.com"),
				Authentication: &model.CategoryAuthentication{},
			},
			CheckAfter: func(t *testing.T, m *ProviderManager) {
				assert := assert.New(t)

				bd, ok := m.brandingDomains["cat1"]
				assert.True(ok)
				assert.Equal("branding.example.com", *bd.Host)
			},
		},
		"should remove branding domain from map when cleared": {
			PrepareManager: func(_ *testing.T) *ProviderManager {
				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{},
					},
					categories: map[string]*providerSet{},
					brandingDomains: map[string]categoryBrandingDomainChange{
						"cat1": {
							CategoryID: "cat1",
							Host:       strPtr("old.example.com"),
						},
					},
				}
			},
			Change: categoryBrandingDomainChange{
				CategoryID:     "cat1",
				Host:           nil,
				Authentication: &model.CategoryAuthentication{},
			},
			CheckAfter: func(t *testing.T, m *ProviderManager) {
				assert := assert.New(t)
				assert.Empty(m.brandingDomains)
			},
		},
		"should skip custom source when no category scope exists": {
			PrepareManager: func(_ *testing.T) *ProviderManager {
				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{},
					},
					categories:      map[string]*providerSet{},
					brandingDomains: map[string]categoryBrandingDomainChange{},
				}
			},
			Change: categoryBrandingDomainChange{
				CategoryID: "cat1",
				Host:       strPtr("branding.example.com"),
				Authentication: &model.CategoryAuthentication{
					SAML: &model.CategoryAuthSAML{
						ConfigSource: model.CategoryAuthenticationConfigSourceCustom,
					},
				},
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			m := tc.PrepareManager(t)

			// Mock expectations are verified automatically via t.Cleanup
			// registered by NewMockBrandingAwareProvider.
			m.handleCategoryBrandingDomainChange(t.Context(), tc.Change)

			if tc.CheckAfter != nil {
				tc.CheckAfter(t, m)
			}
		})
	}
}

func TestApplyStoredBranding(t *testing.T) {
	t.Parallel()

	cases := map[string]struct {
		PrepareManager func(*testing.T) *ProviderManager
		ProviderName   string
		CategoryID     *string
	}{
		"should apply branding to category provider": {
			PrepareManager: func(t *testing.T) *ProviderManager {
				bap := provider.NewMockBrandingAwareProvider(t)
				host := "branding.example.com"
				bap.On("SetBrandingHost", t.Context(), "cat1", &host).Return(nil)

				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{},
					},
					categories: map[string]*providerSet{
						"cat1": {
							providers: map[string]provider.Provider{
								types.ProviderSAML: bap,
							},
						},
					},
					brandingDomains: map[string]categoryBrandingDomainChange{
						"cat1": {
							CategoryID:     "cat1",
							Host:           strPtr("branding.example.com"),
							Authentication: &model.CategoryAuthentication{},
						},
					},
				}
			},
			ProviderName: types.ProviderSAML,
			CategoryID:   strPtr("cat1"),
		},
		"should skip when category ID is nil": {
			PrepareManager: func(_ *testing.T) *ProviderManager {
				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{},
					},
					categories:      map[string]*providerSet{},
					brandingDomains: map[string]categoryBrandingDomainChange{},
				}
			},
			ProviderName: types.ProviderSAML,
			CategoryID:   nil,
		},
		"should skip when provider is not BrandingAwareProvider": {
			PrepareManager: func(_ *testing.T) *ProviderManager {
				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{},
					},
					categories: map[string]*providerSet{
						"cat1": {
							providers: map[string]provider.Provider{
								types.ProviderUnknown: &provider.Unknown{},
							},
						},
					},
					brandingDomains: map[string]categoryBrandingDomainChange{
						"cat1": {
							CategoryID:     "cat1",
							Host:           strPtr("branding.example.com"),
							Authentication: &model.CategoryAuthentication{},
						},
					},
				}
			},
			ProviderName: types.ProviderUnknown,
			CategoryID:   strPtr("cat1"),
		},
		"should skip when no branding domain is stored for category": {
			PrepareManager: func(_ *testing.T) *ProviderManager {
				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{},
					},
					categories: map[string]*providerSet{
						"cat1": {
							providers: map[string]provider.Provider{
								types.ProviderSAML: provider.InitSAML("", "", nil, log.New("test", "debug"), nil, nil),
							},
						},
					},
					brandingDomains: map[string]categoryBrandingDomainChange{},
				}
			},
			ProviderName: types.ProviderSAML,
			CategoryID:   strPtr("cat1"),
		},
		"should apply branding even when stored authentication says provider is disabled": {
			PrepareManager: func(t *testing.T) *ProviderManager {
				bap := provider.NewMockBrandingAwareProvider(t)
				host := "branding.example.com"
				bap.On("SetBrandingHost", t.Context(), "cat1", &host).Return(nil)

				return &ProviderManager{
					log: log.New("test", "debug"),
					global: providerSet{
						providers: map[string]provider.Provider{},
					},
					categories: map[string]*providerSet{
						"cat1": {
							providers: map[string]provider.Provider{
								types.ProviderSAML: bap,
							},
						},
					},
					brandingDomains: map[string]categoryBrandingDomainChange{
						"cat1": {
							CategoryID: "cat1",
							Host:       strPtr("branding.example.com"),
							Authentication: &model.CategoryAuthentication{
								SAML: &model.CategoryAuthSAML{
									Disabled: true,
								},
							},
						},
					},
				}
			},
			ProviderName: types.ProviderSAML,
			CategoryID:   strPtr("cat1"),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			m := tc.PrepareManager(t)

			_, scope := m.resolveScope(tc.CategoryID)

			m.applyStoredBranding(t.Context(), m.log, scope, tc.ProviderName, tc.CategoryID)
		})
	}
}

func TestProviderManagerManage(t *testing.T) {
	t.Parallel()

	cases := map[string]struct {
		PrepareDB      func(*r.Mock)
		ReloadInterval time.Duration
		CategoryID     string
		Expected       []string
		CheckCategory  func(*testing.T, *ProviderManager)
	}{
		"should dynamically enable global provider on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					Local: model.Local{Enabled: true},
				}, nil).Once()
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					Local: model.Local{Enabled: true},
					LDAP:  model.LDAP{Enabled: true, LDAPConfig: model.LDAPConfig{Host: "ldap.test", Port: 636}},
				}, nil)
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			ReloadInterval: 10 * time.Millisecond,
			Expected:       []string{"form", "ldap", "local"},
		},
		"should dynamically disable global provider on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					Local: model.Local{Enabled: true},
					SAML:  model.SAML{Enabled: true, SAMLConfig: model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}},
				}, nil).Once()
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					Local: model.Local{Enabled: true},
				}, nil)
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			ReloadInterval: 10 * time.Millisecond,
			Expected:       []string{"form", "local"},
		},
		"should dynamically enable category provider on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					Local: model.Local{Enabled: true},
				}, nil)
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"disabled": true,
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{},
						},
					},
				}, nil)
			},
			ReloadInterval: 10 * time.Millisecond,
			CategoryID:     "cat1",
			Expected:       []string{"form", "local"},
		},
		"should dynamically disable category provider and clean up empty category": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					Local: model.Local{Enabled: true},
				}, nil)
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"disabled": true,
							},
						},
					},
				}, nil)
			},
			ReloadInterval: 10 * time.Millisecond,
			CategoryID:     "cat1",
			CheckCategory: func(t *testing.T, m *ProviderManager) {
				assert := assert.New(t)

				time.Sleep(11 * time.Millisecond)
				synctest.Wait()

				m.mux.RLock()
				defer m.mux.RUnlock()

				assert.Nil(m.categories["cat1"])
			},
		},
		"should process branding domain change through manage pipeline": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					Local: model.Local{Enabled: true},
					SAML:  model.SAML{Enabled: true, SAMLConfig: model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}},
				}, nil)
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{},
						},
						"branding": map[string]any{
							"domain": map[string]any{
								"enabled": true,
								"name":    "branding.example.com",
							},
						},
					},
				}, nil)
			},
			CategoryID: "cat1",
			Expected:   []string{"form", "local", "saml"},
		},
		"should store branding domain when no matching provider exists": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					Local: model.Local{Enabled: true},
				}, nil)
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"disabled": true,
							},
						},
						"branding": map[string]any{
							"domain": map[string]any{
								"enabled": true,
								"name":    "branding.example.com",
							},
						},
					},
				}, nil)
			},
			CategoryID: "cat1",
			Expected:   []string{"form", "local"},
		},
		"should apply stored branding domain when category custom provider is enabled on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					Local: model.Local{Enabled: true},
				}, nil)

				// Initial: cat1 has branding domain but no custom SAML.
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id":             "cat1",
						"authentication": map[string]any{},
						"branding": map[string]any{
							"domain": map[string]any{
								"enabled": true,
								"name":    "branding.example.com",
							},
						},
					},
				}, nil).Once()

				// Reload: cat1 now has custom SAML.
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"config_source": "custom",
								"saml_config": map[string]any{
									"metadata_url": "https://cat1-saml.test/metadata",
								},
							},
						},
						"branding": map[string]any{
							"domain": map[string]any{
								"enabled": true,
								"name":    "branding.example.com",
							},
						},
					},
				}, nil)
			},
			ReloadInterval: 10 * time.Millisecond,
			CheckCategory: func(t *testing.T, m *ProviderManager) {
				assert := assert.New(t)

				time.Sleep(11 * time.Millisecond)
				synctest.Wait()

				assert.Equal([]string{"form", "local", "saml"}, m.Providers("cat1"))

				m.mux.RLock()
				defer m.mux.RUnlock()

				bd, ok := m.brandingDomains["cat1"]
				assert.True(ok)
				assert.Equal("branding.example.com", *bd.Host)
			},
		},
		"should apply stored branding domain when provider goes from disabled to custom on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					Local: model.Local{Enabled: true},
				}, nil)

				// Initial: cat1 has branding domain with SAML explicitly disabled.
				// The stored Authentication will have SAML.Disabled=true.
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"disabled": true,
							},
						},
						"branding": map[string]any{
							"domain": map[string]any{
								"enabled": true,
								"name":    "branding.example.com",
							},
						},
					},
				}, nil).Once()

				// Reload: SAML goes from disabled to custom+enabled.
				// Branding host unchanged → no new branding event.
				// The stored Authentication is stale (still says disabled).
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"config_source": "custom",
								"saml_config": map[string]any{
									"metadata_url": "https://cat1-saml.test/metadata",
								},
							},
						},
						"branding": map[string]any{
							"domain": map[string]any{
								"enabled": true,
								"name":    "branding.example.com",
							},
						},
					},
				}, nil)
			},
			ReloadInterval: 10 * time.Millisecond,
			CheckCategory: func(t *testing.T, m *ProviderManager) {
				assert := assert.New(t)

				time.Sleep(11 * time.Millisecond)
				synctest.Wait()

				assert.Equal([]string{"form", "local", "saml"}, m.Providers("cat1"))

				m.mux.RLock()
				defer m.mux.RUnlock()

				bd, ok := m.brandingDomains["cat1"]
				assert.True(ok)
				assert.Equal("branding.example.com", *bd.Host)
			},
		},
		"should clear stored branding domain when category is deleted": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					Local: model.Local{Enabled: true},
				}, nil)

				// Initial: cat1 has branding domain.
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id":             "cat1",
						"authentication": map[string]any{},
						"branding": map[string]any{
							"domain": map[string]any{
								"enabled": true,
								"name":    "branding.example.com",
							},
						},
					},
				}, nil).Once()

				// Reload: category deleted from DB.
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			ReloadInterval: 10 * time.Millisecond,
			CheckCategory: func(t *testing.T, m *ProviderManager) {
				assert := assert.New(t)

				// Verify branding was stored initially.
				m.mux.RLock()
				_, ok := m.brandingDomains["cat1"]
				m.mux.RUnlock()
				assert.True(ok)

				// After reload, category is deleted → branding should be cleared.
				time.Sleep(11 * time.Millisecond)
				synctest.Wait()

				m.mux.RLock()
				defer m.mux.RUnlock()

				assert.Empty(m.brandingDomains)
			},
		},
		"should handle full lifecycle of provider enable, category override, disable, and re-enable": {
			PrepareDB: func(m *r.Mock) {
				globalLocalOnly := model.Config{
					Local: model.Local{Enabled: true},
				}
				globalWithSAML := model.Config{
					Local: model.Local{Enabled: true},
					SAML:  model.SAML{Enabled: true, SAMLConfig: model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}},
				}

				m.On(r.Table("config").Get(1).Field("auth")).Return(globalLocalOnly, nil).Once()
				m.On(r.Table("config").Get(1).Field("auth")).Return(globalWithSAML, nil).Times(5)
				m.On(r.Table("config").Get(1).Field("auth")).Return(globalLocalOnly, nil)

				catEmpty := []any{}
				catCustomSAML := []any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"config_source": "custom",
								"saml_config": map[string]any{
									"metadata_url": "https://cat1-saml.test/metadata",
								},
							},
						},
					},
				}
				catDisabledSAML := []any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"disabled": true,
							},
						},
					},
				}
				catGlobalSAML := []any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"config_source": "global",
							},
						},
					},
				}

				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return(catEmpty, nil).Times(2)
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return(catCustomSAML, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return(catDisabledSAML, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return(catCustomSAML, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return(catGlobalSAML, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return(catEmpty, nil)
			},
			ReloadInterval: 1 * time.Second,
			CheckCategory: func(t *testing.T, m *ProviderManager) {
				assert := assert.New(t)

				// Initial load.
				assert.Equal([]string{"form", "local"}, m.Providers("cat1"))
				assert.Equal(types.ProviderUnknown, m.Provider(types.ProviderSAML, "cat1").String())

				// Enable global SAML.
				time.Sleep(1100 * time.Millisecond)
				synctest.Wait()
				assert.Equal([]string{"form", "local", "saml"}, m.Providers("cat1"))
				assert.Equal(types.ProviderSAML, m.Provider(types.ProviderSAML, "cat1").String())

				// Enable custom category SAML.
				time.Sleep(1100 * time.Millisecond)
				synctest.Wait()
				assert.Equal([]string{"form", "local", "saml"}, m.Providers("cat1"))
				assert.Equal(types.ProviderSAML, m.Provider(types.ProviderSAML, "cat1").String())

				// Disable category SAML.
				time.Sleep(1100 * time.Millisecond)
				synctest.Wait()
				assert.Equal([]string{"form", "local"}, m.Providers("cat1"))
				assert.Equal(types.ProviderUnknown, m.Provider(types.ProviderSAML, "cat1").String())

				// Re-enable custom category SAML.
				time.Sleep(1100 * time.Millisecond)
				synctest.Wait()
				assert.Equal([]string{"form", "local", "saml"}, m.Providers("cat1"))
				assert.Equal(types.ProviderSAML, m.Provider(types.ProviderSAML, "cat1").String())

				// Switch to global config_source.
				time.Sleep(1100 * time.Millisecond)
				synctest.Wait()
				assert.Equal([]string{"form", "local", "saml"}, m.Providers("cat1"))
				assert.Equal(types.ProviderSAML, m.Provider(types.ProviderSAML, "cat1").String())

				// Disable global SAML.
				time.Sleep(1100 * time.Millisecond)
				synctest.Wait()
				assert.Equal([]string{"form", "local"}, m.Providers("cat1"))
				assert.Equal(types.ProviderUnknown, m.Provider(types.ProviderSAML, "cat1").String())
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			synctest.Test(t, func(t *testing.T) {
				assert := assert.New(t)

				ctx, cancel := context.WithCancel(t.Context())
				defer cancel()

				var wg sync.WaitGroup

				dbMock := r.NewMock()
				tc.PrepareDB(dbMock)

				m := InitProviderManager(cfg.Authentication{}, log.New("test", "debug"), dbMock)
				m.httpClient = noNetworkClient

				if tc.ReloadInterval > 0 {
					m.cfgWatcher.reloadInterval = tc.ReloadInterval
				}

				m.Manage(ctx, &wg)
				synctest.Wait()

				if tc.ReloadInterval > 0 && tc.CheckCategory == nil {
					time.Sleep(tc.ReloadInterval + time.Millisecond)
					synctest.Wait()
				}

				if tc.CheckCategory != nil {
					tc.CheckCategory(t, m)
				} else {
					result := m.Providers(tc.CategoryID)
					assert.Equal(tc.Expected, result)
				}

				cancel()
				synctest.Wait()
				wg.Wait()
			})
		})
	}
}

func TestProviderConfigSource(t *testing.T) {
	t.Parallel()

	cases := map[string]struct {
		Auth             *model.CategoryAuthentication
		Provider         string
		ExpectedSource   model.CategoryAuthenticationConfigSource
		ExpectedDisabled bool
	}{
		"should return global when auth is nil": {
			Auth:           nil,
			Provider:       types.ProviderSAML,
			ExpectedSource: model.CategoryAuthenticationConfigSourceGlobal,
		},
		"should return global when SAML is nil": {
			Auth:           &model.CategoryAuthentication{},
			Provider:       types.ProviderSAML,
			ExpectedSource: model.CategoryAuthenticationConfigSourceGlobal,
		},
		"should return global when LDAP is nil": {
			Auth:           &model.CategoryAuthentication{},
			Provider:       types.ProviderLDAP,
			ExpectedSource: model.CategoryAuthenticationConfigSourceGlobal,
		},
		"should return global when Google is nil": {
			Auth:           &model.CategoryAuthentication{},
			Provider:       types.ProviderGoogle,
			ExpectedSource: model.CategoryAuthenticationConfigSourceGlobal,
		},
		"should return custom for SAML with custom config_source": {
			Auth: &model.CategoryAuthentication{
				SAML: &model.CategoryAuthSAML{
					ConfigSource: model.CategoryAuthenticationConfigSourceCustom,
				},
			},
			Provider:       types.ProviderSAML,
			ExpectedSource: model.CategoryAuthenticationConfigSourceCustom,
		},
		"should return custom for LDAP with custom config_source": {
			Auth: &model.CategoryAuthentication{
				LDAP: &model.CategoryAuthLDAP{
					ConfigSource: model.CategoryAuthenticationConfigSourceCustom,
				},
			},
			Provider:       types.ProviderLDAP,
			ExpectedSource: model.CategoryAuthenticationConfigSourceCustom,
		},
		"should return custom for Google with custom config_source": {
			Auth: &model.CategoryAuthentication{
				Google: &model.CategoryAuthGoogle{
					ConfigSource: model.CategoryAuthenticationConfigSourceCustom,
				},
			},
			Provider:       types.ProviderGoogle,
			ExpectedSource: model.CategoryAuthenticationConfigSourceCustom,
		},
		"should return global for SAML with global config_source": {
			Auth: &model.CategoryAuthentication{
				SAML: &model.CategoryAuthSAML{
					ConfigSource: model.CategoryAuthenticationConfigSourceGlobal,
				},
			},
			Provider:       types.ProviderSAML,
			ExpectedSource: model.CategoryAuthenticationConfigSourceGlobal,
		},
		"should return global for LDAP with global config_source": {
			Auth: &model.CategoryAuthentication{
				LDAP: &model.CategoryAuthLDAP{
					ConfigSource: model.CategoryAuthenticationConfigSourceGlobal,
				},
			},
			Provider:       types.ProviderLDAP,
			ExpectedSource: model.CategoryAuthenticationConfigSourceGlobal,
		},
		"should return global for Google with global config_source": {
			Auth: &model.CategoryAuthentication{
				Google: &model.CategoryAuthGoogle{
					ConfigSource: model.CategoryAuthenticationConfigSourceGlobal,
				},
			},
			Provider:       types.ProviderGoogle,
			ExpectedSource: model.CategoryAuthenticationConfigSourceGlobal,
		},
		"should return disabled true for disabled SAML": {
			Auth: &model.CategoryAuthentication{
				SAML: &model.CategoryAuthSAML{
					Disabled: true,
				},
			},
			Provider:         types.ProviderSAML,
			ExpectedSource:   model.CategoryAuthenticationConfigSourceGlobal,
			ExpectedDisabled: true,
		},
		"should return disabled true for disabled LDAP": {
			Auth: &model.CategoryAuthentication{
				LDAP: &model.CategoryAuthLDAP{
					Disabled: true,
				},
			},
			Provider:         types.ProviderLDAP,
			ExpectedSource:   model.CategoryAuthenticationConfigSourceGlobal,
			ExpectedDisabled: true,
		},
		"should return disabled true for disabled Google": {
			Auth: &model.CategoryAuthentication{
				Google: &model.CategoryAuthGoogle{
					Disabled: true,
				},
			},
			Provider:         types.ProviderGoogle,
			ExpectedSource:   model.CategoryAuthenticationConfigSourceGlobal,
			ExpectedDisabled: true,
		},
		"should normalize unknown config_source to global": {
			Auth: &model.CategoryAuthentication{
				SAML: &model.CategoryAuthSAML{
					ConfigSource: "unknown",
				},
			},
			Provider:       types.ProviderSAML,
			ExpectedSource: model.CategoryAuthenticationConfigSourceGlobal,
		},
		"should return global for unknown provider": {
			Auth:           &model.CategoryAuthentication{},
			Provider:       "nonexistent",
			ExpectedSource: model.CategoryAuthenticationConfigSourceGlobal,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			assert := assert.New(t)

			source, disabled := providerConfigSource(tc.Auth, tc.Provider)
			assert.Equal(tc.ExpectedSource, source)
			assert.Equal(tc.ExpectedDisabled, disabled)
		})
	}
}
