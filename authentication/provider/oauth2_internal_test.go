package provider

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"golang.org/x/oauth2"
)

func TestOauth2ProviderLoadConfig(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		InitialConfig  oauth2.Config
		Input          oauth2ProviderConfig
		ExpectedID     string
		ExpectedSecret string
	}{
		"should update client ID and client secret": {
			InitialConfig: oauth2.Config{
				Scopes: []string{"scope1"},
			},
			Input: oauth2ProviderConfig{
				clientID:     "my-client-id",
				clientSecret: "my-client-secret",
			},
			ExpectedID:     "my-client-id",
			ExpectedSecret: "my-client-secret",
		},
		"should overwrite existing values": {
			InitialConfig: oauth2.Config{
				ClientID:     "old-id",
				ClientSecret: "old-secret",
			},
			Input: oauth2ProviderConfig{
				clientID:     "new-id",
				clientSecret: "new-secret",
			},
			ExpectedID:     "new-id",
			ExpectedSecret: "new-secret",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			o := &oauth2Provider{
				cfg: &cfgManager[oauth2.Config]{cfg: &tc.InitialConfig},
			}

			o.loadConfig(tc.Input)

			cfg := o.cfg.Cfg()
			assert.Equal(tc.ExpectedID, cfg.ClientID)
			assert.Equal(tc.ExpectedSecret, cfg.ClientSecret)
		})
	}
}
