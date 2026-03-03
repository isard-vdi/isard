package provider_test

import (
	"errors"
	"testing"

	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/stretchr/testify/assert"
)

func TestFormEnableProvider(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		ExistingProviders func(*testing.T) []provider.Provider
		PrepareProviders  func(*testing.T) []provider.Provider
		Expected          []string
	}{
		"should enable a new provider": {
			PrepareProviders: func(t *testing.T) []provider.Provider {
				m := provider.NewMockProvider(t)
				m.On("String").Return("local")
				return []provider.Provider{m}
			},
			Expected: []string{"local"},
		},
		"should not enable a provider that already exists": {
			ExistingProviders: func(t *testing.T) []provider.Provider {
				m := provider.NewMockProvider(t)
				m.On("String").Return("local")
				return []provider.Provider{m}
			},
			PrepareProviders: func(t *testing.T) []provider.Provider {
				m := provider.NewMockProvider(t)
				m.On("String").Return("local")
				return []provider.Provider{m}
			},
			Expected: []string{"local"},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			f := provider.InitForm(cfg.Authentication{}, log.New("test", "debug"), nil, nil)

			if tc.ExistingProviders != nil {
				for _, p := range tc.ExistingProviders(t) {
					f.EnableProvider(p)
				}
			}

			for _, p := range tc.PrepareProviders(t) {
				f.EnableProvider(p)
			}

			assert.ElementsMatch(tc.Expected, f.Providers())
		})
	}
}

func TestFormDisableProvider(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		ExistingProviders func(*testing.T) []provider.Provider
		DisableName       string
		Expected          []string
	}{
		"should disable an existing provider": {
			ExistingProviders: func(t *testing.T) []provider.Provider {
				m := provider.NewMockProvider(t)
				m.On("String").Return("local")
				return []provider.Provider{m}
			},
			DisableName: "local",
			Expected:    []string{},
		},
		"should not disable a nonexistent provider": {
			DisableName: "nonexistent",
			Expected:    []string{},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			f := provider.InitForm(cfg.Authentication{}, log.New("test", "debug"), nil, nil)

			if tc.ExistingProviders != nil {
				for _, p := range tc.ExistingProviders(t) {
					f.EnableProvider(p)
				}
			}

			f.DisableProvider(tc.DisableName)

			assert.ElementsMatch(tc.Expected, f.Providers())
		})
	}
}

func TestFormProviders(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareForm func() *provider.Form
		Expected    []string
	}{
		"should return empty list when no sub-providers": {
			PrepareForm: func() *provider.Form {
				log := log.New("test", "debug")

				return provider.InitForm(cfg.Authentication{}, log, nil, nil)
			},
			Expected: []string{},
		},
		"should return local when only local enabled": {
			PrepareForm: func() *provider.Form {
				log := log.New("test", "debug")

				local := provider.InitLocal(nil)

				return provider.InitForm(cfg.Authentication{}, log, local, nil)
			},
			Expected: []string{"local"},
		},
		"should return both local and ldap when both enabled": {
			PrepareForm: func() *provider.Form {
				log := log.New("test", "debug")

				local := provider.InitLocal(nil)
				ldap := provider.InitLDAP("", log, nil)

				return provider.InitForm(cfg.Authentication{}, log, local, ldap)
			},
			Expected: []string{"local", "ldap"},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			f := tc.PrepareForm()

			assert.ElementsMatch(tc.Expected, f.Providers())
		})
	}
}

func TestFormProvider(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareForm  func() *provider.Form
		LookupName   string
		ExpectedName string
	}{
		"should return provider when it exists": {
			PrepareForm: func() *provider.Form {
				log := log.New("test", "debug")

				local := provider.InitLocal(nil)

				return provider.InitForm(cfg.Authentication{}, log, local, nil)
			},
			LookupName:   "local",
			ExpectedName: "local",
		},
		"should return nil when provider not found": {
			PrepareForm: func() *provider.Form {
				log := log.New("test", "debug")

				local := provider.InitLocal(nil)

				return provider.InitForm(cfg.Authentication{}, log, local, nil)
			},
			LookupName: "nonexistent",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			f := tc.PrepareForm()

			p := f.Provider(tc.LookupName)

			if tc.ExpectedName != "" {
				assert.Equal(tc.ExpectedName, p.String())
			} else {
				assert.Nil(p)
			}
		})
	}
}

func TestFormHealthcheck(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareProviders func(*testing.T) []provider.Provider
		ExpectedErr      string
	}{
		"should return nil when no sub-providers": {
			PrepareProviders: func(_ *testing.T) []provider.Provider {
				return nil
			},
		},
		"should return nil when all sub-providers healthy": {
			PrepareProviders: func(t *testing.T) []provider.Provider {
				m := provider.NewMockProvider(t)
				m.On("String").Return("mock")
				m.On("Healthcheck").Return(nil)

				return []provider.Provider{m}
			},
		},
		"should return error when a sub-provider is unhealthy": {
			PrepareProviders: func(t *testing.T) []provider.Provider {
				m := provider.NewMockProvider(t)
				m.On("String").Return("mock")
				m.On("Healthcheck").Return(errors.New("connection refused"))

				return []provider.Provider{m}
			},
			ExpectedErr: "error in provider 'mock': connection refused ",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			log := log.New("test", "debug")

			f := provider.InitForm(cfg.Authentication{}, log, nil, nil)

			for _, p := range tc.PrepareProviders(t) {
				f.EnableProvider(p)
			}

			err := f.Healthcheck()

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}
		})
	}
}
