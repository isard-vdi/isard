package provider

import (
	"context"
	"testing"

	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"

	"github.com/stretchr/testify/assert"
)

func TestGoogleInitGoogle(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Cfg            cfg.Authentication
		ExpectedScopes int
	}{
		"should create a Google provider with correct initial config": {
			Cfg: cfg.Authentication{
				Secret: "test-secret",
				Host:   "example.com",
			},
			ExpectedScopes: 2,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			g := InitGoogle(tc.Cfg)

			assert.NotNil(g)
			assert.NotNil(g.provider)
			assert.NotNil(g.provider.cfg)

			oauthCfg := g.provider.cfg.Cfg()
			assert.Len(oauthCfg.Scopes, tc.ExpectedScopes)
			assert.Equal("https://example.com/authentication/callback", oauthCfg.RedirectURL)
		})
	}
}

func TestGoogleLoadConfig(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Input          model.GoogleConfig
		ExpectedID     string
		ExpectedSecret string
	}{
		"should update client ID and client secret": {
			Input: model.GoogleConfig{
				ClientID:     "google-client-id",
				ClientSecret: "google-client-secret",
			},
			ExpectedID:     "google-client-id",
			ExpectedSecret: "google-client-secret",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			g := InitGoogle(cfg.Authentication{
				Secret: "test-secret",
				Host:   "example.com",
			})

			err := g.LoadConfig(context.Background(), tc.Input)

			assert.NoError(err)

			oauthCfg := g.provider.cfg.Cfg()
			assert.Equal(tc.ExpectedID, oauthCfg.ClientID)
			assert.Equal(tc.ExpectedSecret, oauthCfg.ClientSecret)
		})
	}
}

func TestGoogleString(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Expected string
	}{
		"should return the google provider type": {
			Expected: types.ProviderGoogle,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			g := &Google{}

			assert.Equal(tc.Expected, g.String())
		})
	}
}

func TestGoogleAutoRegister(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Expected bool
	}{
		"should return false": {
			Expected: false,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			g := Google{}

			assert.Equal(tc.Expected, g.AutoRegister(nil))
		})
	}
}

func TestGoogleSaveEmail(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Expected bool
	}{
		"should return true": {
			Expected: true,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			g := Google{}

			assert.Equal(tc.Expected, g.SaveEmail())
		})
	}
}

func TestGoogleGuessGroups(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		ExpectedErr error
	}{
		"should return ErrInvalidIDP": {
			ExpectedErr: ErrInvalidIDP,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			g := Google{}
			grp, secondary, err := g.GuessGroups(context.Background(), nil, nil)

			assert.Nil(grp)
			assert.Nil(secondary)
			assert.ErrorIs(err, tc.ExpectedErr)
		})
	}
}

func TestGoogleGuessRole(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		ExpectedErr error
	}{
		"should return ErrInvalidIDP": {
			ExpectedErr: ErrInvalidIDP,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			g := Google{}
			role, err := g.GuessRole(context.Background(), nil, nil)

			assert.Nil(role)
			assert.ErrorIs(err, tc.ExpectedErr)
		})
	}
}
