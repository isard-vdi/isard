package providermanager

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/pkg/log"

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
				case <-time.After(100 * time.Millisecond):
					t.Fatal("expected value on channel but got none")
				}

			} else {
				select {
				case <-ch:
					t.Fatal("expected no value on channel but got one")
				case <-time.After(100 * time.Millisecond):
				}
			}
		})
	}
}

func TestCfgWatcherWatch(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{}, nil)
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{}, nil)
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{}, nil)
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{}, nil)
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

			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()

			dbMock := r.NewMock()
			tc.PrepareDB(dbMock)

			logger := log.New("test", "debug")
			watcher := initCfgWatcher(logger)

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

			time.Sleep(100 * time.Millisecond)
			cancel()

			done := make(chan struct{})
			go func() {
				watcherWg.Wait()
				watchWg.Wait()
				close(done)
			}()

			select {
			case <-done:
			case <-time.After(1 * time.Second):
				assert.Fail("goroutines did not stop after context cancellation")
			}

			dbMock.AssertExpectations(t)
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

			notifyProviderChangeIfNeeded(ch, nil, "test-provider", tc.Enabled, tc.NewEnabled)

			if tc.ExpectSend {
				select {
				case v := <-ch:
					assert.Equal("test-provider", v.Provider)
					assert.Equal(tc.NewEnabled, v.Enabled)
				case <-time.After(100 * time.Millisecond):
					t.Fatal("expected value on channel but got none")
				}
			} else {
				select {
				case <-ch:
					t.Fatal("expected no value on channel but got one")
				case <-time.After(100 * time.Millisecond):
				}
			}
		})
	}
}

func TestCfgWatcherAddLDAPWatcher(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

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

			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()

			logger := log.New("test", "debug")
			watcher := initCfgWatcher(logger)

			mock := provider.NewMockConfigurableProvider[model.LDAPConfig](t)
			if tc.PrepareMock != nil {
				tc.PrepareMock(ctx, mock)
			}

			var wg sync.WaitGroup
			addLDAPWatcher(ctx, &wg, logger, watcher.globalChanges.ldapChanges, mock)

			if tc.Config != nil {
				watcher.globalChanges.ldapChanges <- *tc.Config
				time.Sleep(100 * time.Millisecond)
			}

			cancel()

			done := make(chan struct{})
			go func() {
				wg.Wait()
				close(done)
			}()

			select {
			case <-done:
			case <-time.After(1 * time.Second):
				assert.Fail("watcher goroutine did not stop after context cancellation")
			}
		})
	}
}

func TestCfgWatcherAddSAMLWatcher(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

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

			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()

			logger := log.New("test", "debug")
			watcher := initCfgWatcher(logger)

			mock := provider.NewMockConfigurableProvider[model.SAMLConfig](t)
			if tc.PrepareMock != nil {
				tc.PrepareMock(ctx, mock)
			}

			var wg sync.WaitGroup
			addSAMLWatcher(ctx, &wg, logger, watcher.globalChanges.samlChanges, mock)

			if tc.Config != nil {
				watcher.globalChanges.samlChanges <- *tc.Config
				time.Sleep(100 * time.Millisecond)
			}

			cancel()

			done := make(chan struct{})
			go func() {
				wg.Wait()
				close(done)
			}()

			select {
			case <-done:
			case <-time.After(1 * time.Second):
				assert.Fail("watcher goroutine did not stop after context cancellation")
			}
		})
	}
}

func TestCfgWatcherAddGoogleWatcher(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

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

			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()

			logger := log.New("test", "debug")
			watcher := initCfgWatcher(logger)

			mock := provider.NewMockConfigurableProvider[model.GoogleConfig](t)
			if tc.PrepareMock != nil {
				tc.PrepareMock(ctx, mock)
			}

			var wg sync.WaitGroup
			addGoogleWatcher(ctx, &wg, logger, watcher.globalChanges.googleChanges, mock)

			if tc.Config != nil {
				watcher.globalChanges.googleChanges <- *tc.Config
				time.Sleep(100 * time.Millisecond)
			}

			cancel()

			done := make(chan struct{})
			go func() {
				wg.Wait()
				close(done)
			}()

			select {
			case <-done:
			case <-time.After(1 * time.Second):
				assert.Fail("watcher goroutine did not stop after context cancellation")
			}
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

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB               func(*r.Mock)
		ExpectedChanges         []providerChange
		ExpectedDisabledChanges []categoryDisabledProviderChange
		ExpectedLDAPConfigs     []model.LDAPConfig
		ExpectedSAMLConfigs     []model.SAMLConfig
		ExpectedGoogleConfigs   []model.GoogleConfig
	}{
		"should broadcast initial local provider for category": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{},
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{},
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"disabled": true,
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{},
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
					map[string]any{
						"id": "cat2",
						"authentication": map[string]any{
							"local": map[string]any{},
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication")).Return(nil, errors.New("reload error"))
			},
			ExpectedChanges: []providerChange{
				{CategoryID: strPtr("cat1"), Provider: types.ProviderLocal, Enabled: true},
			},
		},
		"should stop when context is cancelled": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{}, nil)
			},
			ExpectedChanges: []providerChange{},
		},
		"should send disable events when category is deleted on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{},
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{}, nil)
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{},
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{}, nil)
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{},
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"disabled": true,
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{},
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{}, nil)
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
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"ldap": map[string]any{
								"disabled": true,
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{}, nil)
			},
			ExpectedChanges: []providerChange{},
			ExpectedDisabledChanges: []categoryDisabledProviderChange{
				{CategoryID: "cat1", Provider: types.ProviderLDAP, Disabled: true},
				{CategoryID: "cat1", Provider: types.ProviderLDAP, Disabled: false},
			},
		},
		"should clean up disabled SAML event when category with disabled SAML is deleted": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"saml": map[string]any{
								"disabled": true,
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{}, nil)
			},
			ExpectedChanges: []providerChange{},
			ExpectedDisabledChanges: []categoryDisabledProviderChange{
				{CategoryID: "cat1", Provider: types.ProviderSAML, Disabled: true},
				{CategoryID: "cat1", Provider: types.ProviderSAML, Disabled: false},
			},
		},
		"should clean up disabled Google event when category with disabled Google is deleted": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"google": map[string]any{
								"disabled": true,
							},
						},
					},
				}, nil).Once()
				m.On(r.Table("categories").Pluck("id", "authentication")).Return([]any{}, nil)
			},
			ExpectedChanges: []providerChange{},
			ExpectedDisabledChanges: []categoryDisabledProviderChange{
				{CategoryID: "cat1", Provider: types.ProviderGoogle, Disabled: true},
				{CategoryID: "cat1", Provider: types.ProviderGoogle, Disabled: false},
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctx, cancel := context.WithCancel(t.Context())
			defer cancel()

			dbMock := r.NewMock()
			tc.PrepareDB(dbMock)

			logger := log.New("test", "debug")
			watcher := initCfgWatcher(logger)

			var wg sync.WaitGroup
			watcher.watchCategories(ctx, &wg, dbMock)

			time.Sleep(100 * time.Millisecond)
			cancel()

			done := make(chan struct{})
			go func() {
				wg.Wait()
				close(done)
			}()

			select {
			case <-done:
			case <-time.After(1 * time.Second):
				assert.Fail("goroutines did not stop after context cancellation")
			}

			// Drain and collect provider changes
			var changes []providerChange
			for {
				select {
				case c := <-watcher.providerChanges:
					changes = append(changes, c)
				default:
					goto doneChanges
				}
			}
		doneChanges:

			if tc.ExpectedChanges == nil {
				tc.ExpectedChanges = []providerChange{}
			}

			assert.ElementsMatch(tc.ExpectedChanges, changes)

			// Drain and collect LDAP configs from all category channels
			var ldapConfigs []model.LDAPConfig
			for _, ch := range watcher.categoriesChanges {
				for {
					select {
					case cfg := <-ch.ldapChanges:
						ldapConfigs = append(ldapConfigs, cfg)
					default:
						goto doneLDAP
					}
				}
			doneLDAP:
			}

			if tc.ExpectedLDAPConfigs != nil {
				assert.ElementsMatch(tc.ExpectedLDAPConfigs, ldapConfigs)
			}

			// Drain and collect SAML configs from all category channels
			var samlConfigs []model.SAMLConfig
			for _, ch := range watcher.categoriesChanges {
				for {
					select {
					case cfg := <-ch.samlChanges:
						samlConfigs = append(samlConfigs, cfg)
					default:
						goto doneSAML
					}
				}
			doneSAML:
			}

			if tc.ExpectedSAMLConfigs != nil {
				assert.ElementsMatch(tc.ExpectedSAMLConfigs, samlConfigs)
			}

			// Drain and collect Google configs from all category channels
			var googleConfigs []model.GoogleConfig
			for _, ch := range watcher.categoriesChanges {
				for {
					select {
					case cfg := <-ch.googleChanges:
						googleConfigs = append(googleConfigs, cfg)
					default:
						goto doneGoogle
					}
				}
			doneGoogle:
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

			dbMock.AssertExpectations(t)
		})
	}
}
