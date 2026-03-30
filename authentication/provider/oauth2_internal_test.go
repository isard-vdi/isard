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

func TestOauth2ProviderIsAllowedHost(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Host          string
		BrandingHosts map[string]string
		Input         string
		Expected      bool
	}{
		"should allow the main host": {
			Host:          "example.com",
			BrandingHosts: map[string]string{},
			Input:         "example.com",
			Expected:      true,
		},
		"should allow a branding host": {
			Host: "example.com",
			BrandingHosts: map[string]string{
				"cat1": "branding1.example.com",
			},
			Input:    "branding1.example.com",
			Expected: true,
		},
		"should reject an unknown host": {
			Host: "example.com",
			BrandingHosts: map[string]string{
				"cat1": "branding1.example.com",
			},
			Input:    "evil.example.com",
			Expected: false,
		},
		"should reject when no branding hosts configured": {
			Host:          "example.com",
			BrandingHosts: map[string]string{},
			Input:         "other.example.com",
			Expected:      false,
		},
		"should allow any of multiple branding hosts": {
			Host: "example.com",
			BrandingHosts: map[string]string{
				"cat1": "branding1.example.com",
				"cat2": "branding2.example.com",
			},
			Input:    "branding2.example.com",
			Expected: true,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			o := &oauth2Provider{
				host:          tc.Host,
				brandingHosts: tc.BrandingHosts,
			}

			assert.Equal(tc.Expected, o.isAllowedHost(tc.Input))
		})
	}
}

func TestOauth2ProviderSetBrandingHost(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		ExistingHosts map[string]string
		CategoryID    string
		Host          *string
		ExpectedHosts map[string]string
	}{
		"should add a branding host": {
			ExistingHosts: map[string]string{},
			CategoryID:    "cat1",
			Host:          strPtr("branding1.example.com"),
			ExpectedHosts: map[string]string{
				"cat1": "branding1.example.com",
			},
		},
		"should remove a branding host": {
			ExistingHosts: map[string]string{
				"cat1": "branding1.example.com",
			},
			CategoryID:    "cat1",
			Host:          nil,
			ExpectedHosts: map[string]string{},
		},
		"should overwrite an existing branding host": {
			ExistingHosts: map[string]string{
				"cat1": "old.example.com",
			},
			CategoryID: "cat1",
			Host:       strPtr("new.example.com"),
			ExpectedHosts: map[string]string{
				"cat1": "new.example.com",
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			o := &oauth2Provider{
				brandingHosts: tc.ExistingHosts,
			}

			o.setBrandingHost(tc.CategoryID, tc.Host)

			assert.Equal(tc.ExpectedHosts, o.brandingHosts)
		})
	}
}
