package provider_test

import (
	"context"
	"fmt"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestLogin(t *testing.T) {
	assert := assert.New(t)
	now := float64(time.Now().Unix())

	cases := map[string]struct {
		PrepareDB func(*r.Mock)

		CategoryID  string
		PrepareArgs func() provider.LoginArgs

		CheckToken        func(string)
		ExpectedGroup     *model.Group
		ExpectedSecondary []*model.Group
		ExpectedUser      *types.ProviderUserData
		ExpectedRedirect  string
		ExpectedErr       string
	}{
		"should work as expected": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "pau"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				), r.FilterOpts{})).Return([]interface{}{
					map[string]interface{}{
						"id":                      "905d7714-df00-499a-8b0a-7d7a0a40191f",
						"username":                "pau",
						"uid":                     "pau",
						"password":                "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
						"password_reset_token":    "",
						"provider":                "local",
						"active":                  true,
						"category":                "default",
						"role":                    "user",
						"group":                   "default-default",
						"name":                    "Pau Abril",
						"email":                   "pau@example.org",
						"email_verified":          &now,
						"disclaimer_acknowledged": true,
					},
				}, nil)
			},
			CategoryID: "default",
			PrepareArgs: func() provider.LoginArgs {
				username := "pau"
				password := "f0kt3Rf$"

				return provider.LoginArgs{
					FormUsername: &username,
					FormPassword: &password,
				}
			},
			ExpectedGroup:     nil,
			ExpectedSecondary: []*model.Group{},
			ExpectedUser: &types.ProviderUserData{
				Provider: "local",
				Category: "default",
				UID:      "pau",
				Role:     func() *model.Role { r := model.RoleUser; return &r }(),
				Group:    &[]string{"default-default"}[0],
				Username: &[]string{"pau"}[0],
				Name:     &[]string{"Pau Abril"}[0],
				Email:    &[]string{"pau@example.org"}[0],
				Photo:    nil,
			},
			ExpectedRedirect: "",
		},
		"should return an error if user is not found": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "pau"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				), r.FilterOpts{})).Return([]interface{}{}, nil)
			},
			CategoryID: "default",
			PrepareArgs: func() provider.LoginArgs {
				username := "pau"
				password := "f0kt3Rf$"

				return provider.LoginArgs{
					FormUsername: &username,
					FormPassword: &password,
				}
			},
			ExpectedGroup:     nil,
			ExpectedSecondary: nil,
			ExpectedUser:      nil,
			ExpectedRedirect:  "",
			ExpectedErr:       "invalid credentials: user not found",
		},
		"should return an internal error if DB load fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "pau"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				), r.FilterOpts{})).Return(nil, fmt.Errorf("DB error :("))
			},
			CategoryID: "default",
			PrepareArgs: func() provider.LoginArgs {
				username := "pau"
				password := "f0kt3Rf$"

				return provider.LoginArgs{
					FormUsername: &username,
					FormPassword: &password,
				}
			},
			ExpectedGroup:     nil,
			ExpectedSecondary: nil,
			ExpectedUser:      nil,
			ExpectedRedirect:  "",
			ExpectedErr:       "internal server error: load user from DB: DB error :(",
		},
		"should return an error if the password doesn't match": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("uid"), "pau"),
					r.Eq(r.Row.Field("provider"), "local"),
					r.Eq(r.Row.Field("category"), "default"),
				), r.FilterOpts{})).Return([]interface{}{
					map[string]interface{}{
						"id":                      "905d7714-df00-499a-8b0a-7d7a0a40191f",
						"username":                "pau",
						"password":                "$2y$14$hXX69rADE4XwS6kzW9u5IezINOw65rLntuBeEt8K5g2LqrZw3zTfm", // dQw4w9WgXcQ
						"password_reset_token":    "",
						"provider":                "local",
						"active":                  true,
						"category":                "default",
						"role":                    "user",
						"group":                   "default-default",
						"name":                    "Pau Abril",
						"email":                   "pau@example.org",
						"email_verified":          &now,
						"disclaimer_acknowledged": true,
					},
				}, nil)
			},
			CategoryID: "default",
			PrepareArgs: func() provider.LoginArgs {
				username := "pau"
				password := "f0kt3Rf$"

				return provider.LoginArgs{
					FormUsername: &username,
					FormPassword: &password,
				}
			},
			ExpectedGroup:     nil,
			ExpectedSecondary: nil,
			ExpectedUser:      nil,
			ExpectedRedirect:  "",
			ExpectedErr:       "invalid credentials: invalid password",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ctx := context.Background()

			dbMock := r.NewMock()
			tc.PrepareDB(dbMock)

			p := provider.InitLocal(dbMock)
			g, secondary, u, redirect, tkn, err := p.Login(ctx, tc.CategoryID, tc.PrepareArgs())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.Nil(err)
			}

			assert.Equal(tc.ExpectedGroup, g)
			assert.Equal(tc.ExpectedSecondary, secondary)
			assert.Equal(tc.ExpectedUser, u)

			if tc.CheckToken == nil {
				assert.Empty(tkn)
			} else {
				tc.CheckToken(tkn)
			}
			assert.Equal(tc.ExpectedRedirect, redirect)

			dbMock.AssertExpectations(t)
		})
	}
}
func TestCallback(t *testing.T) {
	assert := assert.New(t)

	p := provider.InitLocal(nil)
	group, secondary, user, redirect, token, err := p.Callback(context.Background(), nil, provider.CallbackArgs{})

	assert.Nil(group)
	assert.Nil(secondary)
	assert.Nil(user)
	assert.Empty(redirect)
	assert.Empty(token)
	assert.EqualError(err, "invalid identity provider for this operation: the local provider doesn't support the callback operation")
}

func TestAutoRegister(t *testing.T) {
	assert := assert.New(t)

	p := provider.InitLocal(nil)
	result := p.AutoRegister(nil)

	assert.False(result)
}

func TestString(t *testing.T) {
	assert := assert.New(t)

	p := provider.InitLocal(nil)
	result := p.String()

	assert.Equal(result, types.ProviderLocal)
}

func TestHealthcheck(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB func(*r.Mock)

		ExpectedErr string
	}{
		"should be healthy and not return any error": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Status()).Return([]interface{}{}, nil)
			},
			ExpectedErr: "",
		},
		"should return an error if it can't connect to db": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Status()).Return([]interface{}{}, fmt.Errorf("No DB :("))
			},
			ExpectedErr: "unable to connect to the DB: No DB :(",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {

			dbMock := r.NewMock()
			tc.PrepareDB(dbMock)

			p := provider.InitLocal(dbMock)
			err := p.Healthcheck()

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			dbMock.AssertExpectations(t)
		})
	}
}
