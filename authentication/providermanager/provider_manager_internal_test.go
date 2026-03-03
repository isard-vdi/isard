package providermanager

import (
	"context"
	"errors"
	"sync"
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
					types.ProviderExternal: provider.InitExternal(nil),
					types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log.New("test", "debug"), provider.InitLocal(nil), nil),
				}
			},
			Expected: []string{"form", "local"},
		},
		"should not include form when it has no sub-providers": {
			PrepareProviders: func() map[string]provider.Provider {
				return map[string]provider.Provider{
					types.ProviderUnknown:  &provider.Unknown{},
					types.ProviderExternal: provider.InitExternal(nil),
					types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log.New("test", "debug"), nil, nil),
				}
			},
			Expected: []string{},
		},
		"should include SAML when enabled": {
			PrepareProviders: func() map[string]provider.Provider {
				log := log.New("test", "debug")

				return map[string]provider.Provider{
					types.ProviderUnknown:  &provider.Unknown{},
					types.ProviderExternal: provider.InitExternal(nil),
					types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
					types.ProviderSAML:     provider.InitSAML("", "", log, nil),
				}
			},
			Expected: []string{"form", "local", "saml"},
		},
		"should include Google when enabled": {
			PrepareProviders: func() map[string]provider.Provider {
				log := log.New("test", "debug")

				return map[string]provider.Provider{
					types.ProviderUnknown:  &provider.Unknown{},
					types.ProviderExternal: provider.InitExternal(nil),
					types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
					types.ProviderGoogle:   provider.InitGoogle(cfg.Authentication{}),
				}
			},
			Expected: []string{"form", "google", "local"},
		},
		"should include all providers when all are enabled": {
			PrepareProviders: func() map[string]provider.Provider {
				log := log.New("test", "debug")

				return map[string]provider.Provider{
					types.ProviderUnknown:  &provider.Unknown{},
					types.ProviderExternal: provider.InitExternal(nil),
					types.ProviderForm:     provider.InitForm(cfg.Authentication{}, log, provider.InitLocal(nil), nil),
					types.ProviderSAML:     provider.InitSAML("", "", log, nil),
					types.ProviderGoogle:   provider.InitGoogle(cfg.Authentication{}),
				}
			},
			Expected: []string{"form", "google", "local", "saml"},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			m := &ProviderManager{
				providers: tc.PrepareProviders(),
			}

			assert.Equal(tc.Expected, m.Providers())
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
					types.ProviderForm:    provider.InitForm(cfg.Authentication{}, log.New("test", "debug"), provider.InitLocal(nil), nil),
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
		"should return nil when the SAML provider is not present": {
			PrepareProviders: func() map[string]provider.Provider {
				return map[string]provider.Provider{}
			},
		},
		"should return nil when the SAML provider has no middleware configured": {
			PrepareProviders: func() map[string]provider.Provider {
				return map[string]provider.Provider{
					types.ProviderSAML: provider.InitSAML("", "", log.New("test", "debug"), nil),
				}
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

func TestProviderManagerEnableProvider(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareManager    func() *ProviderManager
		EnableProvider    string
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
				m.providers[types.ProviderSAML] = provider.InitSAML("", "", log, nil)

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
				m.providers[types.ProviderForm] = provider.InitForm(cfg.Authentication{}, log, local, nil)

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
				m.providers[types.ProviderForm] = provider.InitForm(cfg.Authentication{}, log, nil, ldap)

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
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()

			var wg sync.WaitGroup

			m := tc.PrepareManager()

			m.enableProvider(ctx, &wg, tc.EnableProvider)

			if tc.ExpectedFormSub != nil {
				f := m.providers[types.ProviderForm].(*provider.Form)
				assert.ElementsMatch(tc.ExpectedFormSub, f.Providers())
			}

			if tc.ExpectedProviders != nil {
				for _, p := range tc.ExpectedProviders {
					assert.NotNil(m.providers[p])
				}
			}

			expectedWatchers := tc.ExpectedWatchers
			if expectedWatchers == nil {
				expectedWatchers = []string{}
			}

			actualWatchers := []string{}
			for k := range m.cfgWatcherCancels {
				actualWatchers = append(actualWatchers, k)
			}

			assert.ElementsMatch(expectedWatchers, actualWatchers)

			cancel()
			wg.Wait()
		})
	}
}

func TestProviderManagerDisableProvider(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareManager   func() *ProviderManager
		DisableProvider  string
		ExpectedFormSub  []string
		ExpectedAbsent   []string
		ExpectedWatchers []string
	}{
		"should disable local provider from form": {
			PrepareManager: func() *ProviderManager {
				log := log.New("test", "debug")

				local := provider.InitLocal(nil)

				m := InitProviderManager(cfg.Authentication{}, log, nil)
				m.providers[types.ProviderForm] = provider.InitForm(cfg.Authentication{}, log, local, nil)

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
				m.providers[types.ProviderForm] = provider.InitForm(cfg.Authentication{}, log, nil, ldap)

				_, cancel := context.WithCancel(context.Background())
				m.cfgWatcherCancels[types.ProviderLDAP] = cancel

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
				m.providers[types.ProviderSAML] = provider.InitSAML("", "", log, nil)

				_, cancel := context.WithCancel(context.Background())
				m.cfgWatcherCancels[types.ProviderSAML] = cancel

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
				m.providers[types.ProviderGoogle] = provider.InitGoogle(cfg.Authentication{})

				_, cancel := context.WithCancel(context.Background())
				m.cfgWatcherCancels[types.ProviderGoogle] = cancel

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
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			m := tc.PrepareManager()

			m.disableProvider(tc.DisableProvider)

			if tc.ExpectedFormSub != nil {
				f := m.providers[types.ProviderForm].(*provider.Form)
				assert.ElementsMatch(tc.ExpectedFormSub, f.Providers())
			}

			if tc.ExpectedAbsent != nil {
				for _, p := range tc.ExpectedAbsent {
					assert.Nil(m.providers[p])
				}
			}

			actualWatchers := []string{}
			for k := range m.cfgWatcherCancels {
				actualWatchers = append(actualWatchers, k)
			}

			assert.ElementsMatch(tc.ExpectedWatchers, actualWatchers)
		})
	}
}

func TestProviderManagerHandleProviderChange(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Change          providerChange
		ExpectedFormSub []string
	}{
		"should enable provider when Enabled is true": {
			Change: providerChange{
				Provider: types.ProviderLocal,
				Enabled:  true,
			},
			ExpectedFormSub: []string{"local"},
		},
		"should disable provider when Enabled is false": {
			Change: providerChange{
				Provider: types.ProviderLocal,
				Enabled:  false,
			},
			ExpectedFormSub: []string{},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()

			var wg sync.WaitGroup

			log := log.New("test", "debug")

			m := InitProviderManager(cfg.Authentication{}, log, nil)

			if !tc.Change.Enabled {
				local := provider.InitLocal(nil)

				m.providers[types.ProviderForm] = provider.InitForm(cfg.Authentication{}, log, local, nil)
			}

			m.handleProviderChange(ctx, &wg, tc.Change)

			f := m.providers[types.ProviderForm].(*provider.Form)
			assert.ElementsMatch(tc.ExpectedFormSub, f.Providers())

			cancel()
			wg.Wait()
		})
	}
}
