package providermanager

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider"

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

			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()

			dbMock := r.NewMock()
			tc.PrepareDB(dbMock)

			logger := zerolog.Nop()
			watcher := InitCfgWatcher(&logger)

			ldapMock := provider.NewMockConfigurableProvider[model.LDAPConfig](t)
			samlMock := provider.NewMockConfigurableProvider[model.SAMLConfig](t)
			googleMock := provider.NewMockConfigurableProvider[model.GoogleConfig](t)

			if tc.PrepareProviders != nil {
				tc.PrepareProviders(ctx, ldapMock, samlMock, googleMock)
			}

			var watcherWg sync.WaitGroup
			watcher.AddLDAPWatcher(ctx, &watcherWg, ldapMock)
			watcher.AddSAMLWatcher(ctx, &watcherWg, samlMock)
			watcher.AddGoogleWatcher(ctx, &watcherWg, googleMock)

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

			notifyProviderChangeIfNeeded(ch, "test-provider", tc.Enabled, tc.NewEnabled)

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

			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()

			logger := zerolog.Nop()
			watcher := InitCfgWatcher(&logger)

			mock := provider.NewMockConfigurableProvider[model.LDAPConfig](t)
			if tc.PrepareMock != nil {
				tc.PrepareMock(ctx, mock)
			}

			var wg sync.WaitGroup
			watcher.AddLDAPWatcher(ctx, &wg, mock)

			if tc.Config != nil {
				watcher.ldapChanges <- *tc.Config
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

			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()

			logger := zerolog.Nop()
			watcher := InitCfgWatcher(&logger)

			mock := provider.NewMockConfigurableProvider[model.SAMLConfig](t)
			if tc.PrepareMock != nil {
				tc.PrepareMock(ctx, mock)
			}

			var wg sync.WaitGroup
			watcher.AddSAMLWatcher(ctx, &wg, mock)

			if tc.Config != nil {
				watcher.samlChanges <- *tc.Config
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

			ctx, cancel := context.WithCancel(context.Background())
			defer cancel()

			logger := zerolog.Nop()
			watcher := InitCfgWatcher(&logger)

			mock := provider.NewMockConfigurableProvider[model.GoogleConfig](t)
			if tc.PrepareMock != nil {
				tc.PrepareMock(ctx, mock)
			}

			var wg sync.WaitGroup
			watcher.AddGoogleWatcher(ctx, &wg, mock)

			if tc.Config != nil {
				watcher.googleChanges <- *tc.Config
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
