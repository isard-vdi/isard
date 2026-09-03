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

	"github.com/stretchr/testify/assert"
)

func TestProviderLoaderWatch(t *testing.T) {
	t.Parallel()

	cases := map[string]struct {
		PrepareMock  func(context.Context, *provider.MockConfigurableProvider[model.SAMLConfig])
		Config       *model.SAMLConfig
		ReloadConfig *model.SAMLConfig
		Retries      int
		ExpectedErr  string
	}{
		"should load the configuration when it changes": {
			PrepareMock: func(ctx context.Context, m *provider.MockConfigurableProvider[model.SAMLConfig]) {
				m.On("String").Return(types.ProviderSAML)
				m.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}).Return(nil).Once()
			},
			Config: &model.SAMLConfig{MetadataURL: "https://saml.test/metadata"},
		},
		"should not retry the load if it succeeded": {
			PrepareMock: func(ctx context.Context, m *provider.MockConfigurableProvider[model.SAMLConfig]) {
				m.On("String").Return(types.ProviderSAML)
				m.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}).Return(nil).Once()
			},
			Config:  &model.SAMLConfig{MetadataURL: "https://saml.test/metadata"},
			Retries: 2,
		},
		"should retry a reload that failed after a successful load": {
			PrepareMock: func(ctx context.Context, m *provider.MockConfigurableProvider[model.SAMLConfig]) {
				m.On("String").Return(types.ProviderSAML)
				m.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}).Return(nil).Once()
				m.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "https://saml.test/new-metadata"}).Return(errors.New("connection reset by peer")).Times(3)
			},
			Config:       &model.SAMLConfig{MetadataURL: "https://saml.test/metadata"},
			ReloadConfig: &model.SAMLConfig{MetadataURL: "https://saml.test/new-metadata"},
			Retries:      2,
			ExpectedErr:  "connection reset by peer",
		},
		"should retry the load if it failed": {
			PrepareMock: func(ctx context.Context, m *provider.MockConfigurableProvider[model.SAMLConfig]) {
				m.On("String").Return(types.ProviderSAML)
				m.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}).Return(errors.New("connection reset by peer")).Once()
				m.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}).Return(nil).Once()
			},
			Config:  &model.SAMLConfig{MetadataURL: "https://saml.test/metadata"},
			Retries: 1,
		},
		"should keep retrying if the load keeps failing": {
			PrepareMock: func(ctx context.Context, m *provider.MockConfigurableProvider[model.SAMLConfig]) {
				m.On("String").Return(types.ProviderSAML)
				m.On("LoadConfig", ctx, model.SAMLConfig{MetadataURL: "https://saml.test/metadata"}).Return(errors.New("connection reset by peer")).Times(3)
			},
			Config:      &model.SAMLConfig{MetadataURL: "https://saml.test/metadata"},
			Retries:     2,
			ExpectedErr: "connection reset by peer",
		},
		"should not load anything if it never received a configuration": {
			Retries: 2,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			synctest.Test(t, func(t *testing.T) {
				assert := assert.New(t)

				ctx, cancel := context.WithCancel(t.Context())
				defer cancel()

				logger := log.New("test", "debug")

				prv := provider.NewMockConfigurableProvider[model.SAMLConfig](t)
				if tc.PrepareMock != nil {
					tc.PrepareMock(ctx, prv)
				}

				changes := make(chan model.SAMLConfig, 1024)

				loader := newProviderLoader(prv, changes)

				var wg sync.WaitGroup
				wg.Go(func() {
					loader.Watch(ctx, logger)
				})
				synctest.Wait()

				if tc.Config != nil {
					changes <- *tc.Config
					synctest.Wait()
				}

				if tc.ReloadConfig != nil {
					changes <- *tc.ReloadConfig
					synctest.Wait()
				}

				for range tc.Retries {
					time.Sleep(providerLoadRetryInterval + time.Millisecond)
					synctest.Wait()
				}

				loader.mux.RLock()
				prvErr := loader.prvErr
				loader.mux.RUnlock()

				if tc.ExpectedErr != "" {
					assert.EqualError(prvErr, tc.ExpectedErr)
				} else {
					assert.Nil(prvErr)
				}

				cancel()
				synctest.Wait()
				wg.Wait()

				prv.AssertExpectations(t)
			})
		})
	}
}
