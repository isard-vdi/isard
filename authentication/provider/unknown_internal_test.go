package provider

import (
	"context"
	"testing"

	"gitlab.com/isard/isardvdi/authentication/provider/types"

	"github.com/stretchr/testify/assert"
)

func TestUnknownString(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Expected string
	}{
		"should return the unknown provider type": {
			Expected: types.ProviderUnknown,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			u := Unknown{}

			assert.Equal(tc.Expected, u.String())
		})
	}
}

func TestUnknownLogin(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		ExpectedErr error
	}{
		"should return ErrUnknownIDP": {
			ExpectedErr: ErrUnknownIDP,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			u := Unknown{}
			g, secondary, usr, redirect, tkn, err := u.Login(context.Background(), "default", LoginArgs{Host: "example.com"})

			assert.Nil(g)
			assert.Nil(secondary)
			assert.Nil(usr)
			assert.Empty(redirect)
			assert.Empty(tkn)
			assert.ErrorIs(err, tc.ExpectedErr)
		})
	}
}

func TestUnknownCallback(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		ExpectedErr error
	}{
		"should return ErrUnknownIDP": {
			ExpectedErr: ErrUnknownIDP,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			u := Unknown{}
			g, secondary, usr, redirect, tkn, err := u.Callback(context.Background(), nil, CallbackArgs{Host: "example.com"})

			assert.Nil(g)
			assert.Nil(secondary)
			assert.Nil(usr)
			assert.Empty(redirect)
			assert.Empty(tkn)
			assert.ErrorIs(err, tc.ExpectedErr)
		})
	}
}

func TestUnknownAutoRegister(t *testing.T) {
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

			u := Unknown{}

			assert.Equal(tc.Expected, u.AutoRegister(nil))
		})
	}
}

func TestUnknownSaveEmail(t *testing.T) {
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

			u := Unknown{}

			assert.Equal(tc.Expected, u.SaveEmail())
		})
	}
}

func TestUnknownGuessGroups(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		ExpectedErr error
	}{
		"should return ErrUnknownIDP": {
			ExpectedErr: ErrUnknownIDP,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			u := Unknown{}
			g, secondary, err := u.GuessGroups(context.Background(), nil, nil)

			assert.Nil(g)
			assert.Nil(secondary)
			assert.ErrorIs(err, tc.ExpectedErr)
		})
	}
}

func TestUnknownGuessRole(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		ExpectedErr error
	}{
		"should return ErrUnknownIDP": {
			ExpectedErr: ErrUnknownIDP,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			u := Unknown{}
			role, err := u.GuessRole(context.Background(), nil, nil)

			assert.Nil(role)
			assert.ErrorIs(err, tc.ExpectedErr)
		})
	}
}
