package provider

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type testCfg struct {
	Name  string
	Value int
}

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

func TestCfgManagerCfg(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Initial  testCfg
		Expected testCfg
	}{
		"should return the stored value": {
			Initial:  testCfg{Name: "hello", Value: 42},
			Expected: testCfg{Name: "hello", Value: 42},
		},
		"should return zero value if initialized empty": {
			Initial:  testCfg{},
			Expected: testCfg{},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			m := &cfgManager[testCfg]{cfg: &tc.Initial}

			assert.Equal(tc.Expected, m.Cfg())
		})
	}
}

func TestCfgManagerLoadCfg(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Initial  testCfg
		Update   testCfg
		Expected testCfg
	}{
		"should update the stored value": {
			Initial:  testCfg{},
			Update:   testCfg{Name: "updated", Value: 42},
			Expected: testCfg{Name: "updated", Value: 42},
		},
		"should overwrite a previous value": {
			Initial:  testCfg{Name: "old", Value: 1},
			Update:   testCfg{Name: "new", Value: 99},
			Expected: testCfg{Name: "new", Value: 99},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			m := &cfgManager[testCfg]{cfg: &tc.Initial}
			m.LoadCfg(tc.Update)

			assert.Equal(tc.Expected, m.Cfg())
		})
	}
}

func TestCfgManagerConcurrency(t *testing.T) {
	t.Parallel()

	cases := map[string]struct {
		Iterations int
	}{
		"should handle concurrent reads and writes safely": {
			Iterations: 100,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			m := &cfgManager[testCfg]{cfg: &testCfg{}}

			var wg sync.WaitGroup

			for i := 0; i < tc.Iterations; i++ {
				wg.Add(1)
				go func(v int) {
					defer wg.Done()
					m.LoadCfg(testCfg{Value: v})
				}(i)
			}

			for i := 0; i < tc.Iterations; i++ {
				wg.Add(1)
				go func() {
					defer wg.Done()
					_ = m.Cfg()
				}()
			}

			wg.Wait()
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
			ldap *MockConfigurableProvider[model.LDAPConfig],
			saml *MockConfigurableProvider[model.SAMLConfig],
			google *MockConfigurableProvider[model.GoogleConfig],
		)
		ExpectPollingGoroutine bool
	}{
		"should broadcast initial config to all watchers": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					LDAP:   model.LDAP{LDAPConfig: model.LDAPConfig{Host: "ldap.test", Port: 636}},
					SAML:   model.SAML{SAMLConfig: model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}},
					Google: model.Google{GoogleConfig: model.GoogleConfig{ClientID: "test-client-id"}},
				}, nil)
			},
			PrepareProviders: func(ctx context.Context, ldap *MockConfigurableProvider[model.LDAPConfig], saml *MockConfigurableProvider[model.SAMLConfig], google *MockConfigurableProvider[model.GoogleConfig]) {
				ldap.On("LoadConfig", ctx, model.LDAPConfig{Host: "ldap.test", Port: 636}).Return(nil)
				saml.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}).Return(nil)
				google.On("LoadConfig", ctx, model.GoogleConfig{ClientID: "test-client-id"}).Return(nil)
			},
			ExpectPollingGoroutine: true,
		},
		"should return early when DB load fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(nil, errors.New("db error"))
			},
			ExpectPollingGoroutine: false,
		},
		"should notify watchers when config changes on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					LDAP:   model.LDAP{LDAPConfig: model.LDAPConfig{Host: "ldap.test", Port: 636}},
					SAML:   model.SAML{SAMLConfig: model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}},
					Google: model.Google{GoogleConfig: model.GoogleConfig{ClientID: "test-client-id"}},
				}, nil).Once()
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					LDAP:   model.LDAP{LDAPConfig: model.LDAPConfig{Host: "ldap2.test", Port: 389}},
					SAML:   model.SAML{SAMLConfig: model.SAMLConfig{MetadataURL: "https://saml2.test/metadata"}},
					Google: model.Google{GoogleConfig: model.GoogleConfig{ClientID: "new-client-id"}},
				}, nil)
			},
			PrepareProviders: func(ctx context.Context, ldap *MockConfigurableProvider[model.LDAPConfig], saml *MockConfigurableProvider[model.SAMLConfig], google *MockConfigurableProvider[model.GoogleConfig]) {
				ldap.On("LoadConfig", ctx, model.LDAPConfig{Host: "ldap.test", Port: 636}).Return(nil)
				ldap.On("LoadConfig", ctx, model.LDAPConfig{Host: "ldap2.test", Port: 389}).Return(nil)
				saml.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}).Return(nil)
				saml.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "https://saml2.test/metadata"}).Return(nil)
				google.On("LoadConfig", ctx, model.GoogleConfig{ClientID: "test-client-id"}).Return(nil)
				google.On("LoadConfig", ctx, model.GoogleConfig{ClientID: "new-client-id"}).Return(nil)
			},
			ExpectPollingGoroutine: true,
		},
		"should not notify watchers when config has not changed on reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					LDAP:   model.LDAP{LDAPConfig: model.LDAPConfig{Host: "ldap.test", Port: 636}},
					SAML:   model.SAML{SAMLConfig: model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}},
					Google: model.Google{GoogleConfig: model.GoogleConfig{ClientID: "test-client-id"}},
				}, nil)
			},
			PrepareProviders: func(ctx context.Context, ldap *MockConfigurableProvider[model.LDAPConfig], saml *MockConfigurableProvider[model.SAMLConfig], google *MockConfigurableProvider[model.GoogleConfig]) {
				ldap.On("LoadConfig", ctx, model.LDAPConfig{Host: "ldap.test", Port: 636}).Return(nil)
				saml.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}).Return(nil)
				google.On("LoadConfig", ctx, model.GoogleConfig{ClientID: "test-client-id"}).Return(nil)
			},
			ExpectPollingGoroutine: true,
		},
		"should handle error during config reload": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(model.Config{
					LDAP:   model.LDAP{LDAPConfig: model.LDAPConfig{Host: "ldap.test", Port: 636}},
					SAML:   model.SAML{SAMLConfig: model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}},
					Google: model.Google{GoogleConfig: model.GoogleConfig{ClientID: "test-client-id"}},
				}, nil).Once()
				m.On(r.Table("config").Get(1).Field("auth")).Return(nil, errors.New("reload error"))
			},
			PrepareProviders: func(ctx context.Context, ldap *MockConfigurableProvider[model.LDAPConfig], saml *MockConfigurableProvider[model.SAMLConfig], google *MockConfigurableProvider[model.GoogleConfig]) {
				ldap.On("LoadConfig", ctx, model.LDAPConfig{Host: "ldap.test", Port: 636}).Return(nil)
				saml.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}).Return(nil)
				google.On("LoadConfig", ctx, model.GoogleConfig{ClientID: "test-client-id"}).Return(nil)
			},
			ExpectPollingGoroutine: true,
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

			ldapMock := NewMockConfigurableProvider[model.LDAPConfig](t)
			samlMock := NewMockConfigurableProvider[model.SAMLConfig](t)
			googleMock := NewMockConfigurableProvider[model.GoogleConfig](t)

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

			watcherDone := make(chan struct{})
			go func() {
				watcherWg.Wait()
				close(watcherDone)
			}()

			select {
			case <-watcherDone:
			case <-time.After(1 * time.Second):
				assert.Fail("watcher goroutines did not stop after context cancellation")
			}

			if !tc.ExpectPollingGoroutine {
				watchDone := make(chan struct{})
				go func() {
					watchWg.Wait()
					close(watchDone)
				}()

				select {
				case <-watchDone:
				case <-time.After(1 * time.Second):
					assert.Fail("Watch should not start polling goroutine on DB error")
				}
			}

			dbMock.AssertExpectations(t)
		})
	}
}
