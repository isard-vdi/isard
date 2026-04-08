package providermanager

import (
	"context"
	"errors"
	"sync"
	"testing"
	"testing/synctest"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestNotifyIfNeeded(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Old         string
		New         string
		ExpectValue bool
	}{
		"should send on channel when config changes": {
			Old:         "old",
			New:         "new",
			ExpectValue: true,
		},
		"should not send on channel when config is equal": {
			Old:         "same",
			New:         "same",
			ExpectValue: false,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ch := make(chan string, 1)

			notifyIfNeeded(ch, tc.Old, tc.New)

			if tc.ExpectValue {
				select {
				case v := <-ch:
					assert.Equal(tc.New, v)
				default:
					t.Fatal("expected value on channel but got none")
				}

			} else {
				select {
				case <-ch:
					t.Fatal("expected no value on channel but got one")
				default:
				}
			}
		})
	}
}

func TestExtractBrandingHost(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Entry    model.CategoryConfigEntry
		Expected *string
	}{
		"should return host when branding domain is enabled": {
			Entry: model.CategoryConfigEntry{
				Branding: model.CategoryBranding{
					Domain: model.CategoryBrandingDomain{Enabled: true, Name: "branding.example.com"},
				},
			},
			Expected: strPtr("branding.example.com"),
		},
		"should return nil when branding domain is disabled": {
			Entry: model.CategoryConfigEntry{
				Branding: model.CategoryBranding{
					Domain: model.CategoryBrandingDomain{Enabled: false, Name: "branding.example.com"},
				},
			},
			Expected: nil,
		},
		"should return nil when branding is zero value": {
			Entry:    model.CategoryConfigEntry{},
			Expected: nil,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			result := extractBrandingHost(tc.Entry)
			assert.Equal(tc.Expected, result)
		})
	}
}

func TestNotifyBrandingDomainChangeIfNeeded(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	testAuth := &model.CategoryAuthentication{
		SAML: &model.CategoryAuthSAML{
			ConfigSource: model.CategoryAuthenticationConfigSourceGlobal,
		},
	}

	cases := map[string]struct {
		Old         *string
		New         *string
		ExpectValue bool
	}{
		"should send on channel when branding host changes from nil to set": {
			Old:         nil,
			New:         strPtr("branding.example.com"),
			ExpectValue: true,
		},
		"should send on channel when branding host changes from set to nil": {
			Old:         strPtr("branding.example.com"),
			New:         nil,
			ExpectValue: true,
		},
		"should send on channel when branding host changes value": {
			Old:         strPtr("old.example.com"),
			New:         strPtr("new.example.com"),
			ExpectValue: true,
		},
		"should not send on channel when branding host is equal": {
			Old:         strPtr("same.example.com"),
			New:         strPtr("same.example.com"),
			ExpectValue: false,
		},
		"should not send on channel when both are nil": {
			Old:         nil,
			New:         nil,
			ExpectValue: false,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ch := make(chan categoryBrandingDomainChange, 1)

			notifyBrandingDomainChangeIfNeeded(ch, "cat1", tc.Old, tc.New, testAuth)

			if tc.ExpectValue {
				select {
				case v := <-ch:
					assert.Equal("cat1", v.CategoryID)
					assert.Equal(tc.New, v.Host)
					assert.Equal(testAuth, v.Authentication)
				default:
					t.Fatal("expected value on channel but got none")
				}
			} else {
				select {
				case <-ch:
					t.Fatal("expected no value on channel but got one")
				default:
				}
			}
		})
	}
}

func TestCfgWatcherWatch(t *testing.T) {
	t.Parallel()

	cases := map[string]struct {
		PrepareDB        func(*r.Mock)
		PrepareProviders func(
			ctx context.Context,
			ldap *provider.MockConfigurableProvider[model.LDAPConfig],
			saml *provider.MockConfigurableProvider[model.SAMLConfig],
			google *provider.MockConfigurableProvider[model.GoogleConfig],
		)
	}{
		"should broadcast initial config to all watchers": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					LDAP:   model.LDAP{Enabled: true, LDAPConfig: model.LDAPConfig{Host: "ldap.test", Port: 636}},
					SAML:   model.SAML{Enabled: true, SAMLConfig: model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}},
					Google: model.Google{Enabled: true, GoogleConfig: model.GoogleConfig{ClientID: "test-client-id"}},
				}, nil)
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			PrepareProviders: func(ctx context.Context, ldap *provider.MockConfigurableProvider[model.LDAPConfig], saml *provider.MockConfigurableProvider[model.SAMLConfig], google *provider.MockConfigurableProvider[model.GoogleConfig]) {
				ldap.On("LoadConfig", ctx, model.LDAPConfig{Host: "ldap.test", Port: 636}).Return(nil)
				saml.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}).Return(nil)
				google.On("LoadConfig", ctx, model.GoogleConfig{ClientID: "test-client-id"}).Return(nil)
			},
		},
		"should notify watchers when config changes on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					LDAP:   model.LDAP{Enabled: true, LDAPConfig: model.LDAPConfig{Host: "ldap.test", Port: 636}},
					SAML:   model.SAML{Enabled: true, SAMLConfig: model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}},
					Google: model.Google{Enabled: true, GoogleConfig: model.GoogleConfig{ClientID: "test-client-id"}},
				}, nil).Once()
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					LDAP:   model.LDAP{Enabled: true, LDAPConfig: model.LDAPConfig{Host: "ldap2.test", Port: 389}},
					SAML:   model.SAML{Enabled: true, SAMLConfig: model.SAMLConfig{MetadataURL: "https://saml2.test/metadata"}},
					Google: model.Google{Enabled: true, GoogleConfig: model.GoogleConfig{ClientID: "new-client-id"}},
				}, nil)
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			PrepareProviders: func(ctx context.Context, ldap *provider.MockConfigurableProvider[model.LDAPConfig], saml *provider.MockConfigurableProvider[model.SAMLConfig], google *provider.MockConfigurableProvider[model.GoogleConfig]) {
				ldap.On("LoadConfig", ctx, model.LDAPConfig{Host: "ldap.test", Port: 636}).Return(nil)
				ldap.On("LoadConfig", ctx, model.LDAPConfig{Host: "ldap2.test", Port: 389}).Return(nil)
				saml.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}).Return(nil)
				saml.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "https://saml2.test/metadata"}).Return(nil)
				google.On("LoadConfig", ctx, model.GoogleConfig{ClientID: "test-client-id"}).Return(nil)
				google.On("LoadConfig", ctx, model.GoogleConfig{ClientID: "new-client-id"}).Return(nil)
			},
		},
		"should not notify watchers when config has not changed on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					LDAP:   model.LDAP{Enabled: true, LDAPConfig: model.LDAPConfig{Host: "ldap.test", Port: 636}},
					SAML:   model.SAML{Enabled: true, SAMLConfig: model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}},
					Google: model.Google{Enabled: true, GoogleConfig: model.GoogleConfig{ClientID: "test-client-id"}},
				}, nil)
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			PrepareProviders: func(ctx context.Context, ldap *provider.MockConfigurableProvider[model.LDAPConfig], saml *provider.MockConfigurableProvider[model.SAMLConfig], google *provider.MockConfigurableProvider[model.GoogleConfig]) {
				ldap.On("LoadConfig", ctx, model.LDAPConfig{Host: "ldap.test", Port: 636}).Return(nil)
				saml.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}).Return(nil)
				google.On("LoadConfig", ctx, model.GoogleConfig{ClientID: "test-client-id"}).Return(nil)
			},
		},
		"should handle error during config reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					LDAP:   model.LDAP{Enabled: true, LDAPConfig: model.LDAPConfig{Host: "ldap.test", Port: 636}},
					SAML:   model.SAML{Enabled: true, SAMLConfig: model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}},
					Google: model.Google{Enabled: true, GoogleConfig: model.GoogleConfig{ClientID: "test-client-id"}},
				}, nil).Once()
				m.On(r.Table("config").Get(1).Field("auth")).Return(nil, errors.New("reload error"))
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			PrepareProviders: func(ctx context.Context, ldap *provider.MockConfigurableProvider[model.LDAPConfig], saml *provider.MockConfigurableProvider[model.SAMLConfig], google *provider.MockConfigurableProvider[model.GoogleConfig]) {
				ldap.On("LoadConfig", ctx, model.LDAPConfig{Host: "ldap.test", Port: 636}).Return(nil)
				saml.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}).Return(nil)
				google.On("LoadConfig", ctx, model.GoogleConfig{ClientID: "test-client-id"}).Return(nil)
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			synctest.Test(t, func(t *testing.T) {
				ctx, cancel := context.WithCancel(t.Context())
				defer cancel()

				dbMock := r.NewMock()
				tc.PrepareDB(dbMock)

				logger := log.New("test", "debug")
				watcher := initCfgWatcher(logger)
				watcher.reloadInterval = 10 * time.Millisecond

				ldapMock := provider.NewMockConfigurableProvider[model.LDAPConfig](t)
				samlMock := provider.NewMockConfigurableProvider[model.SAMLConfig](t)
				googleMock := provider.NewMockConfigurableProvider[model.GoogleConfig](t)

				if tc.PrepareProviders != nil {
					tc.PrepareProviders(ctx, ldapMock, samlMock, googleMock)
				}

				var watcherWg sync.WaitGroup
				addLDAPWatcher(ctx, &watcherWg, logger, watcher.globalChanges.ldapChanges, ldapMock)
				addSAMLWatcher(ctx, &watcherWg, logger, watcher.globalChanges.samlChanges, samlMock)
				addGoogleWatcher(ctx, &watcherWg, logger, watcher.globalChanges.googleChanges, googleMock)

				var watchWg sync.WaitGroup
				watcher.Watch(ctx, &watchWg, dbMock)

				time.Sleep(watcher.reloadInterval + time.Millisecond)
				synctest.Wait()

				cancel()
				synctest.Wait()

				watcherWg.Wait()
				watchWg.Wait()

				dbMock.AssertExpectations(t)
			})
		})
	}
}

func TestNotifyProviderChangeIfNeeded(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Enabled    bool
		NewEnabled bool
		ExpectSend bool
	}{
		"should send change when enabled becomes disabled": {
			Enabled:    true,
			NewEnabled: false,
			ExpectSend: true,
		},
		"should send change when disabled becomes enabled": {
			Enabled:    false,
			NewEnabled: true,
			ExpectSend: true,
		},
		"should not send when enabled stays true": {
			Enabled:    true,
			NewEnabled: true,
			ExpectSend: false,
		},
		"should not send when enabled stays false": {
			Enabled:    false,
			NewEnabled: false,
			ExpectSend: false,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ch := make(chan providerChange, 1)

			logger := log.New("test", "debug")
			notifyProviderChangeIfNeeded(logger, ch, nil, "test-provider", tc.Enabled, tc.NewEnabled)

			if tc.ExpectSend {
				select {
				case v := <-ch:
					assert.Equal("test-provider", v.Provider)
					assert.Equal(tc.NewEnabled, v.Enabled)
				default:
					t.Fatal("expected value on channel but got none")
				}
			} else {
				select {
				case <-ch:
					t.Fatal("expected no value on channel but got one")
				default:
				}
			}
		})
	}
}

func TestNotifyDisabledProviderChangeIfNeeded(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Disabled    bool
		NewDisabled bool
		ExpectSend  bool
	}{
		"should send change when disabled becomes enabled": {
			Disabled:    true,
			NewDisabled: false,
			ExpectSend:  true,
		},
		"should send change when enabled becomes disabled": {
			Disabled:    false,
			NewDisabled: true,
			ExpectSend:  true,
		},
		"should not send when disabled stays true": {
			Disabled:    true,
			NewDisabled: true,
			ExpectSend:  false,
		},
		"should not send when disabled stays false": {
			Disabled:    false,
			NewDisabled: false,
			ExpectSend:  false,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ch := make(chan categoryDisabledProviderChange, 1)

			logger := log.New("test", "debug")
			notifyDisabledProviderChangeIfNeeded(logger, ch, "cat1", "test-provider", tc.Disabled, tc.NewDisabled)

			if tc.ExpectSend {
				select {
				case v := <-ch:
					assert.Equal("cat1", v.CategoryID)
					assert.Equal("test-provider", v.Provider)
					assert.Equal(tc.NewDisabled, v.Disabled)
				default:
					t.Fatal("expected value on channel but got none")
				}
			} else {
				select {
				case <-ch:
					t.Fatal("expected no value on channel but got one")
				default:
				}
			}
		})
	}
}

func testAddProviderWatcher[T any](
	t *testing.T,
	addWatcher func(context.Context, *sync.WaitGroup, *zerolog.Logger, chan T, provider.ConfigurableProvider[T]),
	getChan func(*cfgWatcher) chan T,
	config *T,
	prepareMock func(context.Context, *provider.MockConfigurableProvider[T]),
) {
	t.Helper()

	synctest.Test(t, func(t *testing.T) {
		ctx, cancel := context.WithCancel(t.Context())
		defer cancel()

		logger := log.New("test", "debug")
		watcher := initCfgWatcher(logger)

		mock := provider.NewMockConfigurableProvider[T](t)
		if prepareMock != nil {
			prepareMock(ctx, mock)
		}

		ch := getChan(watcher)

		var wg sync.WaitGroup
		addWatcher(ctx, &wg, logger, ch, mock)

		if config != nil {
			ch <- *config
			synctest.Wait()
		}

		cancel()
		synctest.Wait()
		wg.Wait()
	})
}

func TestCfgWatcherAddLDAPWatcher(t *testing.T) {
	t.Parallel()

	cases := map[string]struct {
		PrepareMock func(context.Context, *provider.MockConfigurableProvider[model.LDAPConfig])
		Config      *model.LDAPConfig
	}{
		"should call LoadConfig on config change": {
			PrepareMock: func(ctx context.Context, m *provider.MockConfigurableProvider[model.LDAPConfig]) {
				m.On("LoadConfig", ctx, model.LDAPConfig{Host: "ldap.test", Port: 636}).Return(nil)
			},
			Config: &model.LDAPConfig{Host: "ldap.test", Port: 636},
		},
		"should log error when LoadConfig fails": {
			PrepareMock: func(ctx context.Context, m *provider.MockConfigurableProvider[model.LDAPConfig]) {
				m.On("LoadConfig", ctx, model.LDAPConfig{Host: "bad.test"}).Return(errors.New("invalid config"))
			},
			Config: &model.LDAPConfig{Host: "bad.test"},
		},
		"should stop when context cancelled": {},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			testAddProviderWatcher(t, addLDAPWatcher,
				func(w *cfgWatcher) chan model.LDAPConfig { return w.globalChanges.ldapChanges },
				tc.Config, tc.PrepareMock,
			)
		})
	}
}

func TestCfgWatcherAddSAMLWatcher(t *testing.T) {
	t.Parallel()

	cases := map[string]struct {
		PrepareMock func(context.Context, *provider.MockConfigurableProvider[model.SAMLConfig])
		Config      *model.SAMLConfig
	}{
		"should call LoadConfig on config change": {
			PrepareMock: func(ctx context.Context, m *provider.MockConfigurableProvider[model.SAMLConfig]) {
				m.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}).Return(nil)
			},
			Config: &model.SAMLConfig{MetadataURL: "https://saml.test/metadata"},
		},
		"should log error when LoadConfig fails": {
			PrepareMock: func(ctx context.Context, m *provider.MockConfigurableProvider[model.SAMLConfig]) {
				m.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "bad"}).Return(errors.New("invalid config"))
			},
			Config: &model.SAMLConfig{MetadataURL: "bad"},
		},
		"should stop when context cancelled": {},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			testAddProviderWatcher(t, addSAMLWatcher,
				func(w *cfgWatcher) chan model.SAMLConfig { return w.globalChanges.samlChanges },
				tc.Config, tc.PrepareMock,
			)
		})
	}
}

func TestCfgWatcherAddGoogleWatcher(t *testing.T) {
	t.Parallel()

	cases := map[string]struct {
		PrepareMock func(context.Context, *provider.MockConfigurableProvider[model.GoogleConfig])
		Config      *model.GoogleConfig
	}{
		"should call LoadConfig on config change": {
			PrepareMock: func(ctx context.Context, m *provider.MockConfigurableProvider[model.GoogleConfig]) {
				m.On("LoadConfig", ctx, model.GoogleConfig{ClientID: "test-client-id"}).Return(nil)
			},
			Config: &model.GoogleConfig{ClientID: "test-client-id"},
		},
		"should log error when LoadConfig fails": {
			PrepareMock: func(ctx context.Context, m *provider.MockConfigurableProvider[model.GoogleConfig]) {
				m.On("LoadConfig", ctx, model.GoogleConfig{ClientID: "bad"}).Return(errors.New("invalid config"))
			},
			Config: &model.GoogleConfig{ClientID: "bad"},
		},
		"should stop when context cancelled": {},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			testAddProviderWatcher(t, addGoogleWatcher,
				func(w *cfgWatcher) chan model.GoogleConfig { return w.globalChanges.googleChanges },
				tc.Config, tc.PrepareMock,
			)
		})
	}
}

func TestGetOrCreateCategoryChangesChannels(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareWatcher func() *cfgWatcher
		CategoryID     string
		ExpectNew      bool
	}{
		"should create new channels when category does not exist": {
			PrepareWatcher: func() *cfgWatcher {
				logger := log.New("test", "debug")
				return initCfgWatcher(logger)
			},
			CategoryID: "new-cat",
			ExpectNew:  true,
		},
		"should return existing channels when category already exists": {
			PrepareWatcher: func() *cfgWatcher {
				logger := log.New("test", "debug")

				w := initCfgWatcher(logger)

				changesChans := &providerChangesChannels{
					ldapChanges:   make(chan model.LDAPConfig, 1024),
					samlChanges:   make(chan model.SAMLConfig, 1024),
					googleChanges: make(chan model.GoogleConfig, 1024),
				}
				w.categoriesChanges["existing-cat"] = changesChans

				return w
			},
			CategoryID: "existing-cat",
			ExpectNew:  false,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			w := tc.PrepareWatcher()

			existing := w.categoriesChanges[tc.CategoryID]

			result := w.getOrCreateCategoryChangesChannels(tc.CategoryID)

			assert.NotNil(result)
			assert.NotNil(result.ldapChanges)
			assert.NotNil(result.samlChanges)
			assert.NotNil(result.googleChanges)

			if tc.ExpectNew {
				assert.Nil(existing)
			} else {
				assert.Same(existing, result)
			}
		})
	}
}

func TestCfgWatcherWatchCategories(t *testing.T) {
	t.Parallel()

	cases := map[string]struct {
		PrepareDB               func(*r.Mock)
		ExpectedChanges         []providerChange
		ExpectedDisabledChanges []categoryDisabledProviderChange
		ExpectedBrandingChanges []categoryBrandingDomainChange
		ExpectedLDAPConfigs     []model.LDAPConfig
		ExpectedSAMLConfigs     []model.SAMLConfig
		ExpectedGoogleConfigs   []model.GoogleConfig
	}{
		"should broadcast initial local provider for category": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
			},
		},
		"should broadcast initial LDAP provider and config for category": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{
								"config_source": "custom",
								"ldap_config": map[string]any{
									"host": "ldap.test",
									"port": 636,
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLDAP, Enabled: true},
			},
			ExpectedLDAPConfigs: []model.LDAPConfig{
				{Host: "ldap.test", Port: 636},
			},
		},
		"should not send LDAP change when LDAP config is nil": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{},
		},
		"should handle category with empty authentication": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id":             "cat1",
						"authentication": map[string]any{},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{},
		},
		"should broadcast initial Google provider and config for category": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"google": map[string]any{
								"config_source": "custom",
								"google_config": map[string]any{
									"client_id":     "test-client-id",
									"client_secret": "test-secret",
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderGoogle, Enabled: true},
			},
			ExpectedGoogleConfigs: []model.GoogleConfig{
				{ClientID: "test-client-id", ClientSecret: "test-secret"},
			},
		},
		"should handle multiple providers in a single category": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
							"ldap": map[string]any{
								"config_source": "custom",
								"ldap_config": map[string]any{
									"host": "ldap.test",
									"port": 636,
								},
							},
							"saml": map[string]any{
								"config_source": "custom",
								"saml_config": map[string]any{
									"metadata_url": "https://saml.test/metadata",
								},
							},
							"google": map[string]any{
								"config_source": "custom",
								"google_config": map[string]any{
									"client_id":     "test-client-id",
									"client_secret": "test-secret",
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLDAP, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderSAML, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderGoogle, Enabled: true},
			},
			ExpectedLDAPConfigs: []model.LDAPConfig{
				{Host: "ldap.test", Port: 636},
			},
			ExpectedSAMLConfigs: []model.SAMLConfig{
				{MetadataURL: "https://saml.test/metadata"},
			},
			ExpectedGoogleConfigs: []model.GoogleConfig{
				{ClientID: "test-client-id", ClientSecret: "test-secret"},
			},
		},
		"should detect category provider enable on reload": {
			PrepareDB: func(m *r.Mock) {
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
							"local": map[string]any{
								"config_source": "custom",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
			},
		},
		"should detect category provider disable on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
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
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: false},
			},
		},
		"should detect category LDAP config change on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{
								"config_source": "custom",
								"ldap_config": map[string]any{
									"host": "ldap.test",
									"port": 636,
								},
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{
								"config_source": "custom",
								"ldap_config": map[string]any{
									"host": "ldap2.test",
									"port": 389,
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLDAP, Enabled: true},
			},
			ExpectedLDAPConfigs: []model.LDAPConfig{
				{Host: "ldap.test", Port: 636},
				{Host: "ldap2.test", Port: 389},
			},
		},
		"should detect category Google config change on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"google": map[string]any{
								"config_source": "custom",
								"google_config": map[string]any{
									"client_id":     "old-client-id",
									"client_secret": "old-secret",
								},
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"google": map[string]any{
								"config_source": "custom",
								"google_config": map[string]any{
									"client_id":     "new-client-id",
									"client_secret": "new-secret",
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderGoogle, Enabled: true},
			},
			ExpectedGoogleConfigs: []model.GoogleConfig{
				{ClientID: "old-client-id", ClientSecret: "old-secret"},
				{ClientID: "new-client-id", ClientSecret: "new-secret"},
			},
		},
		"should detect category SAML config change on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"config_source": "custom",
								"saml_config": map[string]any{
									"metadata_url": "https://saml.test/metadata",
								},
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"config_source": "custom",
								"saml_config": map[string]any{
									"metadata_url": "https://saml2.test/metadata",
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderSAML, Enabled: true},
			},
			ExpectedSAMLConfigs: []model.SAMLConfig{
				{MetadataURL: "https://saml.test/metadata"},
				{MetadataURL: "https://saml2.test/metadata"},
			},
		},
		"should handle new category appearing on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat2",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat2"), Provider: types.ProviderLocal, Enabled: true},
			},
		},
		"should handle error during categories reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return(nil, errors.New("reload error"))
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
			},
		},
		"should stop when context is cancelled": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			ExpectedChanges: []providerChange{},
		},
		"should send disable events when category is deleted on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
							"ldap": map[string]any{
								"config_source": "custom",
								"ldap_config": map[string]any{
									"host": "ldap.test",
									"port": 636,
								},
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLDAP, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: false},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLDAP, Enabled: false},
			},
		},
		"should send disable events for all provider types when category is deleted": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
							"ldap": map[string]any{
								"config_source": "custom",
								"ldap_config": map[string]any{
									"host": "ldap.test",
									"port": 636,
								},
							},
							"saml": map[string]any{
								"config_source": "custom",
								"saml_config": map[string]any{
									"metadata_url": "https://saml.test/metadata",
								},
							},
							"google": map[string]any{
								"config_source": "custom",
								"google_config": map[string]any{
									"client_id":     "test-client-id",
									"client_secret": "test-secret",
								},
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLDAP, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderSAML, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderGoogle, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: false},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLDAP, Enabled: false},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderSAML, Enabled: false},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderGoogle, Enabled: false},
			},
		},
		"should clean up when category providers all disabled on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
							"ldap": map[string]any{
								"config_source": "custom",
								"ldap_config": map[string]any{
									"host": "ldap.test",
									"port": 636,
								},
							},
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
							"ldap": map[string]any{
								"disabled":      true,
								"config_source": "custom",
								"ldap_config": map[string]any{
									"host": "ldap.test",
									"port": 636,
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLDAP, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: false},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLDAP, Enabled: false},
			},
		},
		"should not send LDAP enable when LDAP config is nil on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{},
		},
		"should not send SAML enable when SAML config is nil on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{},
		},
		"should not send Google enable when Google config is nil on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"google": map[string]any{},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{},
		},
		"should enable LDAP with config_source custom and custom config": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{
								"config_source": "custom",
								"ldap_config": map[string]any{
									"host": "ldap.test",
									"port": 636,
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLDAP, Enabled: true},
			},
			ExpectedLDAPConfigs: []model.LDAPConfig{
				{Host: "ldap.test", Port: 636},
			},
		},
		"should not enable LDAP with config_source global": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{
								"config_source": "global",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{},
		},
		"should not enable SAML with config_source global": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"config_source": "global",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{},
		},
		"should not enable Google with config_source global": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"google": map[string]any{
								"config_source": "global",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{},
		},
		"should enable SAML with config_source custom": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"config_source": "custom",
								"saml_config": map[string]any{
									"metadata_url": "https://saml.test/metadata",
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderSAML, Enabled: true},
			},
			ExpectedSAMLConfigs: []model.SAMLConfig{
				{MetadataURL: "https://saml.test/metadata"},
			},
		},
		"should enable Google with config_source custom": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"google": map[string]any{
								"config_source": "custom",
								"google_config": map[string]any{
									"client_id":     "test-id",
									"client_secret": "test-secret",
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderGoogle, Enabled: true},
			},
			ExpectedGoogleConfigs: []model.GoogleConfig{
				{ClientID: "test-id", ClientSecret: "test-secret"},
			},
		},
		"should detect transition from custom to global on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{
								"config_source": "custom",
								"ldap_config": map[string]any{
									"host": "ldap.test",
									"port": 636,
								},
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{
								"config_source": "global",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLDAP, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLDAP, Enabled: false},
			},
		},
		"should enable LDAP and send config when transitioning from disabled to enabled on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{
								"disabled":      true,
								"config_source": "custom",
								"ldap_config": map[string]any{
									"host": "ldap.test",
									"port": 636,
								},
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{
								"config_source": "custom",
								"ldap_config": map[string]any{
									"host": "ldap.test",
									"port": 636,
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLDAP, Enabled: true},
			},
			ExpectedLDAPConfigs: []model.LDAPConfig{
				{Host: "ldap.test", Port: 636},
			},
			ExpectedDisabledChanges: []categoryDisabledProviderChange{
				{CategoryID: "cat1", Provider: types.ProviderLDAP, Disabled: true},
				{CategoryID: "cat1", Provider: types.ProviderLDAP, Disabled: false},
			},
		},
		"should enable SAML and send config when transitioning from disabled to enabled on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"disabled":      true,
								"config_source": "custom",
								"saml_config": map[string]any{
									"metadata_url": "https://saml.test/metadata",
								},
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"config_source": "custom",
								"saml_config": map[string]any{
									"metadata_url": "https://saml.test/metadata",
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderSAML, Enabled: true},
			},
			ExpectedSAMLConfigs: []model.SAMLConfig{
				{MetadataURL: "https://saml.test/metadata"},
			},
			ExpectedDisabledChanges: []categoryDisabledProviderChange{
				{CategoryID: "cat1", Provider: types.ProviderSAML, Disabled: true},
				{CategoryID: "cat1", Provider: types.ProviderSAML, Disabled: false},
			},
		},
		"should enable Google and send config when transitioning from disabled to enabled on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"google": map[string]any{
								"disabled":      true,
								"config_source": "custom",
								"google_config": map[string]any{
									"client_id":     "test-id",
									"client_secret": "test-secret",
								},
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"google": map[string]any{
								"config_source": "custom",
								"google_config": map[string]any{
									"client_id":     "test-id",
									"client_secret": "test-secret",
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderGoogle, Enabled: true},
			},
			ExpectedGoogleConfigs: []model.GoogleConfig{
				{ClientID: "test-id", ClientSecret: "test-secret"},
			},
			ExpectedDisabledChanges: []categoryDisabledProviderChange{
				{CategoryID: "cat1", Provider: types.ProviderGoogle, Disabled: true},
				{CategoryID: "cat1", Provider: types.ProviderGoogle, Disabled: false},
			},
		},
		"should send disabled event for local on initial load": {
			PrepareDB: func(m *r.Mock) {
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
			ExpectedChanges: []providerChange{},
			ExpectedDisabledChanges: []categoryDisabledProviderChange{
				{CategoryID: "cat1", Provider: types.ProviderLocal, Disabled: true},
			},
		},
		"should send disabled event for LDAP on initial load": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{
								"disabled":      true,
								"config_source": "custom",
								"ldap_config": map[string]any{
									"host": "ldap.test",
									"port": 636,
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{},
			ExpectedDisabledChanges: []categoryDisabledProviderChange{
				{CategoryID: "cat1", Provider: types.ProviderLDAP, Disabled: true},
			},
		},
		"should send disabled event for SAML on initial load": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"disabled":      true,
								"config_source": "custom",
								"saml_config": map[string]any{
									"metadata_url": "https://saml.test/metadata",
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{},
			ExpectedDisabledChanges: []categoryDisabledProviderChange{
				{CategoryID: "cat1", Provider: types.ProviderSAML, Disabled: true},
			},
		},
		"should send disabled event for Google on initial load": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"google": map[string]any{
								"disabled":      true,
								"config_source": "custom",
								"google_config": map[string]any{
									"client_id":     "test-id",
									"client_secret": "test-secret",
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{},
			ExpectedDisabledChanges: []categoryDisabledProviderChange{
				{CategoryID: "cat1", Provider: types.ProviderGoogle, Disabled: true},
			},
		},
		"should clear disabled event when provider becomes enabled on reload": {
			PrepareDB: func(m *r.Mock) {
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
							"local": map[string]any{
								"config_source": "custom",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
			},
			ExpectedDisabledChanges: []categoryDisabledProviderChange{
				{CategoryID: "cat1", Provider: types.ProviderLocal, Disabled: true},
				{CategoryID: "cat1", Provider: types.ProviderLocal, Disabled: false},
			},
		},
		"should set disabled event when provider becomes disabled on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
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
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: false},
			},
			ExpectedDisabledChanges: []categoryDisabledProviderChange{
				{CategoryID: "cat1", Provider: types.ProviderLocal, Disabled: true},
			},
		},
		"should clean up disabled events when category is deleted": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"disabled": true,
							},
							"saml": map[string]any{
								"config_source": "custom",
								"saml_config": map[string]any{
									"metadata_url": "https://saml.test/metadata",
								},
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderSAML, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderSAML, Enabled: false},
			},
			ExpectedDisabledChanges: []categoryDisabledProviderChange{
				{CategoryID: "cat1", Provider: types.ProviderLocal, Disabled: true},
				{CategoryID: "cat1", Provider: types.ProviderLocal, Disabled: false},
			},
		},
		"should clean up disabled LDAP event when category with disabled LDAP is deleted": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{
								"disabled": true,
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			ExpectedChanges: []providerChange{},
			ExpectedDisabledChanges: []categoryDisabledProviderChange{
				{CategoryID: "cat1", Provider: types.ProviderLDAP, Disabled: true},
				{CategoryID: "cat1", Provider: types.ProviderLDAP, Disabled: false},
			},
		},
		"should clean up disabled SAML event when category with disabled SAML is deleted": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"disabled": true,
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			ExpectedChanges: []providerChange{},
			ExpectedDisabledChanges: []categoryDisabledProviderChange{
				{CategoryID: "cat1", Provider: types.ProviderSAML, Disabled: true},
				{CategoryID: "cat1", Provider: types.ProviderSAML, Disabled: false},
			},
		},
		"should clean up disabled Google event when category with disabled Google is deleted": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"google": map[string]any{
								"disabled": true,
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			ExpectedChanges: []providerChange{},
			ExpectedDisabledChanges: []categoryDisabledProviderChange{
				{CategoryID: "cat1", Provider: types.ProviderGoogle, Disabled: true},
				{CategoryID: "cat1", Provider: types.ProviderGoogle, Disabled: false},
			},
		},
		"should not enable local with config_source global": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "global",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{},
		},
		"should not send SAML change when SAML config is nil": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"config_source": "custom",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{},
		},
		"should not send Google change when Google config is nil": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"google": map[string]any{
								"config_source": "custom",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{},
		},
		"should broadcast initial SAML provider and config for category": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"config_source": "custom",
								"saml_config": map[string]any{
									"metadata_url": "https://saml.test/metadata",
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderSAML, Enabled: true},
			},
			ExpectedSAMLConfigs: []model.SAMLConfig{
				{MetadataURL: "https://saml.test/metadata"},
			},
		},
		"should handle multiple categories on initial load": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
						},
					},
					map[string]any{
						"id": "cat2",
						"authentication": map[string]any{
							"ldap": map[string]any{
								"config_source": "custom",
								"ldap_config": map[string]any{
									"host": "ldap.test",
									"port": 636,
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
				{CategoryID: strPtr("cat2"), Provider: types.ProviderLDAP, Enabled: true},
			},
			ExpectedLDAPConfigs: []model.LDAPConfig{
				{Host: "ldap.test", Port: 636},
			},
		},
		"should not enable any provider when all have config_source global on initial load": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "global",
							},
							"ldap": map[string]any{
								"config_source": "global",
							},
							"saml": map[string]any{
								"config_source": "global",
							},
							"google": map[string]any{
								"config_source": "global",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{},
		},
		"should detect local transition from custom to global on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "global",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: false},
			},
		},
		"should detect SAML transition from custom to global on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"config_source": "custom",
								"saml_config": map[string]any{
									"metadata_url": "https://saml.test/metadata",
								},
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"config_source": "global",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderSAML, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderSAML, Enabled: false},
			},
		},
		"should detect Google transition from custom to global on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"google": map[string]any{
								"config_source": "custom",
								"google_config": map[string]any{
									"client_id":     "test-id",
									"client_secret": "test-secret",
								},
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"google": map[string]any{
								"config_source": "global",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderGoogle, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderGoogle, Enabled: false},
			},
		},
		"should detect LDAP transition from global to custom on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{
								"config_source": "global",
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{
								"config_source": "custom",
								"ldap_config": map[string]any{
									"host": "ldap.test",
									"port": 636,
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLDAP, Enabled: true},
			},
			ExpectedLDAPConfigs: []model.LDAPConfig{
				{Host: "ldap.test", Port: 636},
			},
		},
		"should detect SAML transition from global to custom on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"config_source": "global",
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"config_source": "custom",
								"saml_config": map[string]any{
									"metadata_url": "https://saml.test/metadata",
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderSAML, Enabled: true},
			},
			ExpectedSAMLConfigs: []model.SAMLConfig{
				{MetadataURL: "https://saml.test/metadata"},
			},
		},
		"should detect Google transition from global to custom on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"google": map[string]any{
								"config_source": "global",
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"google": map[string]any{
								"config_source": "custom",
								"google_config": map[string]any{
									"client_id":     "test-id",
									"client_secret": "test-secret",
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderGoogle, Enabled: true},
			},
			ExpectedGoogleConfigs: []model.GoogleConfig{
				{ClientID: "test-id", ClientSecret: "test-secret"},
			},
		},
		"should detect local transition from global to custom on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "global",
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
			},
		},
		"should not send changes when config is unchanged on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
							"ldap": map[string]any{
								"config_source": "custom",
								"ldap_config": map[string]any{
									"host": "ldap.test",
									"port": 636,
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLDAP, Enabled: true},
			},
			ExpectedLDAPConfigs: []model.LDAPConfig{
				{Host: "ldap.test", Port: 636},
			},
		},
		"should handle new category with LDAP appearing on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{
								"config_source": "custom",
								"ldap_config": map[string]any{
									"host": "ldap.test",
									"port": 636,
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLDAP, Enabled: true},
			},
			ExpectedLDAPConfigs: []model.LDAPConfig{
				{Host: "ldap.test", Port: 636},
			},
		},
		"should handle new category with multiple providers appearing on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
							"saml": map[string]any{
								"config_source": "custom",
								"saml_config": map[string]any{
									"metadata_url": "https://saml.test/metadata",
								},
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderSAML, Enabled: true},
			},
			ExpectedSAMLConfigs: []model.SAMLConfig{
				{MetadataURL: "https://saml.test/metadata"},
			},
		},
		"should not send disable for LDAP with config_source global when category is deleted": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{
								"config_source": "global",
								"ldap_config": map[string]any{
									"host": "ldap.test",
									"port": 636,
								},
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			ExpectedChanges: []providerChange{},
		},
		"should send disable for local but not LDAP global when category is deleted": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
							"ldap": map[string]any{
								"config_source": "global",
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: false},
			},
		},
		"should handle multiple categories deleted on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
						},
					},
					map[string]any{
						"id": "cat2",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
				{CategoryID: strPtr("cat2"), Provider: types.ProviderLocal, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: false},
				{CategoryID: strPtr("cat2"), Provider: types.ProviderLocal, Enabled: false},
			},
		},
		"should handle one category deleted and another added on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat2",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: false},
				{CategoryID: strPtr("cat2"), Provider: types.ProviderLocal, Enabled: true},
			},
		},
		"should send branding domain change on initial load": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
						},
						"branding": map[string]any{
							"domain": map[string]any{
								"enabled": true,
								"name":    "example.com",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
			},
			ExpectedBrandingChanges: []categoryBrandingDomainChange{
				{
					CategoryID: "cat1",
					Host:       strPtr("example.com"),
					Authentication: &model.CategoryAuthentication{
						Local: &model.CategoryAuthLocal{
							ConfigSource: model.CategoryAuthenticationConfigSourceCustom,
						},
					},
				},
			},
		},
		"should not send branding domain change when domain is disabled on initial load": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
						},
						"branding": map[string]any{
							"domain": map[string]any{
								"enabled": false,
								"name":    "example.com",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
			},
			ExpectedBrandingChanges: []categoryBrandingDomainChange{},
		},
		"should clear branding domain when category is deleted on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
						},
						"branding": map[string]any{
							"domain": map[string]any{
								"enabled": true,
								"name":    "example.com",
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: false},
			},
			ExpectedBrandingChanges: []categoryBrandingDomainChange{
				{
					CategoryID: "cat1",
					Host:       strPtr("example.com"),
					Authentication: &model.CategoryAuthentication{
						Local: &model.CategoryAuthLocal{
							ConfigSource: model.CategoryAuthenticationConfigSourceCustom,
						},
					},
				},
				{
					CategoryID: "cat1",
					Host:       nil,
					Authentication: &model.CategoryAuthentication{
						Local: &model.CategoryAuthLocal{
							ConfigSource: model.CategoryAuthenticationConfigSourceCustom,
						},
					},
				},
			},
		},
		"should detect branding domain change on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
						},
						"branding": map[string]any{
							"domain": map[string]any{
								"enabled": true,
								"name":    "old.example.com",
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
						},
						"branding": map[string]any{
							"domain": map[string]any{
								"enabled": true,
								"name":    "new.example.com",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
			},
			ExpectedBrandingChanges: []categoryBrandingDomainChange{
				{
					CategoryID: "cat1",
					Host:       strPtr("old.example.com"),
					Authentication: &model.CategoryAuthentication{
						Local: &model.CategoryAuthLocal{
							ConfigSource: model.CategoryAuthenticationConfigSourceCustom,
						},
					},
				},
				{
					CategoryID: "cat1",
					Host:       strPtr("new.example.com"),
					Authentication: &model.CategoryAuthentication{
						Local: &model.CategoryAuthLocal{
							ConfigSource: model.CategoryAuthenticationConfigSourceCustom,
						},
					},
				},
			},
		},
		"should detect branding domain disabled on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
						},
						"branding": map[string]any{
							"domain": map[string]any{
								"enabled": true,
								"name":    "example.com",
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "custom",
							},
						},
						"branding": map[string]any{
							"domain": map[string]any{
								"enabled": false,
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
			},
			ExpectedBrandingChanges: []categoryBrandingDomainChange{
				{
					CategoryID: "cat1",
					Host:       strPtr("example.com"),
					Authentication: &model.CategoryAuthentication{
						Local: &model.CategoryAuthLocal{
							ConfigSource: model.CategoryAuthenticationConfigSourceCustom,
						},
					},
				},
				{
					CategoryID: "cat1",
					Host:       nil,
					Authentication: &model.CategoryAuthentication{
						Local: &model.CategoryAuthLocal{
							ConfigSource: model.CategoryAuthenticationConfigSourceCustom,
						},
					},
				},
			},
		},
		"should not send LDAP enable when config is nil despite config_source custom on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{
								"config_source": "custom",
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{},
		},
		"should send local disable on delete even with config_source global": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"config_source": "global",
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: false},
			},
		},
		"should handle category with all providers disabled on initial load": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"disabled": true,
							},
							"ldap": map[string]any{
								"disabled": true,
							},
							"saml": map[string]any{
								"disabled": true,
							},
							"google": map[string]any{
								"disabled": true,
							},
						},
					},
				}, nil)
			},
			ExpectedChanges: []providerChange{},
			ExpectedDisabledChanges: []categoryDisabledProviderChange{
				{CategoryID: "cat1", Provider: types.ProviderLocal, Disabled: true},
				{CategoryID: "cat1", Provider: types.ProviderLDAP, Disabled: true},
				{CategoryID: "cat1", Provider: types.ProviderSAML, Disabled: true},
				{CategoryID: "cat1", Provider: types.ProviderGoogle, Disabled: true},
			},
		},
		"should handle category with all providers disabled then all deleted on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"disabled": true,
							},
							"ldap": map[string]any{
								"disabled": true,
							},
							"saml": map[string]any{
								"disabled": true,
							},
							"google": map[string]any{
								"disabled": true,
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			ExpectedChanges: []providerChange{},
			ExpectedDisabledChanges: []categoryDisabledProviderChange{
				{CategoryID: "cat1", Provider: types.ProviderLocal, Disabled: true},
				{CategoryID: "cat1", Provider: types.ProviderLDAP, Disabled: true},
				{CategoryID: "cat1", Provider: types.ProviderSAML, Disabled: true},
				{CategoryID: "cat1", Provider: types.ProviderGoogle, Disabled: true},
				{CategoryID: "cat1", Provider: types.ProviderLocal, Disabled: false},
				{CategoryID: "cat1", Provider: types.ProviderLDAP, Disabled: false},
				{CategoryID: "cat1", Provider: types.ProviderSAML, Disabled: false},
				{CategoryID: "cat1", Provider: types.ProviderGoogle, Disabled: false},
			},
		},
		"should handle empty categories on initial load": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication", map[string]any{"branding": map[string]any{"domain": true}})).Return([]any{}, nil)
			},
			ExpectedChanges: []providerChange{},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			synctest.Test(t, func(t *testing.T) {
				assert := assert.New(t)

				ctx, cancel := context.WithCancel(t.Context())
				defer cancel()

				dbMock := r.NewMock()
				tc.PrepareDB(dbMock)

				logger := log.New("test", "debug")
				watcher := initCfgWatcher(logger)
				watcher.reloadInterval = 10 * time.Millisecond

				var wg sync.WaitGroup
				watcher.watchCategories(ctx, &wg, dbMock)

				time.Sleep(watcher.reloadInterval + time.Millisecond)
				synctest.Wait()

				cancel()
				synctest.Wait()
				wg.Wait()

				// Drain and collect provider changes
				var changes []providerChange
			drainChanges:
				for {
					select {
					case c := <-watcher.providerChanges:
						changes = append(changes, c)
					default:
						break drainChanges
					}
				}

				if tc.ExpectedChanges == nil {
					tc.ExpectedChanges = []providerChange{}
				}

				assert.ElementsMatch(tc.ExpectedChanges, changes)

				// Drain and collect LDAP configs from all category channels
				var ldapConfigs []model.LDAPConfig
				for _, ch := range watcher.categoriesChanges {
				drainLDAP:
					for {
						select {
						case cfg := <-ch.ldapChanges:
							ldapConfigs = append(ldapConfigs, cfg)
						default:
							break drainLDAP
						}
					}
				}

				if tc.ExpectedLDAPConfigs != nil {
					assert.ElementsMatch(tc.ExpectedLDAPConfigs, ldapConfigs)
				}

				// Drain and collect SAML configs from all category channels
				var samlConfigs []model.SAMLConfig
				for _, ch := range watcher.categoriesChanges {
				drainSAML:
					for {
						select {
						case cfg := <-ch.samlChanges:
							samlConfigs = append(samlConfigs, cfg)
						default:
							break drainSAML
						}
					}
				}

				if tc.ExpectedSAMLConfigs != nil {
					assert.ElementsMatch(tc.ExpectedSAMLConfigs, samlConfigs)
				}

				// Drain and collect Google configs from all category channels
				var googleConfigs []model.GoogleConfig
				for _, ch := range watcher.categoriesChanges {
				drainGoogle:
					for {
						select {
						case cfg := <-ch.googleChanges:
							googleConfigs = append(googleConfigs, cfg)
						default:
							break drainGoogle
						}
					}
				}

				if tc.ExpectedGoogleConfigs != nil {
					assert.ElementsMatch(tc.ExpectedGoogleConfigs, googleConfigs)
				}

				// Drain and collect disabled provider changes.
				var categoriesDisabledChanges []categoryDisabledProviderChange
			drainDisabled:
				for {
					select {
					case c := <-watcher.categoriesDisabledProvidersChanges:
						categoriesDisabledChanges = append(categoriesDisabledChanges, c)
					default:
						break drainDisabled
					}
				}

				if tc.ExpectedDisabledChanges != nil {
					assert.ElementsMatch(tc.ExpectedDisabledChanges, categoriesDisabledChanges)
				}

				// Drain and collect branding domain changes.
				var brandingChanges []categoryBrandingDomainChange
			drainBranding:
				for {
					select {
					case c := <-watcher.categoriesBrandingDomainChanges:
						brandingChanges = append(brandingChanges, c)
					default:
						break drainBranding
					}
				}

				if tc.ExpectedBrandingChanges != nil {
					assert.ElementsMatch(tc.ExpectedBrandingChanges, brandingChanges)
				}

				dbMock.AssertExpectations(t)
			})
		})
	}
}
