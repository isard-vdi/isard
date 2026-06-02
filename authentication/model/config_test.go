package model_test

import (
	"errors"
	"testing"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/stretchr/testify/assert"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestConfigLoad(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB      func(*r.Mock)
		ExpectedConfig *model.Config
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(map[string]any{
					"local": map[string]any{
						"enabled": true,
					},
					"ldap": map[string]any{
						"enabled": false,
						"ldap_config": map[string]any{
							"host": "ldap.example.org",
							"port": 636,
						},
					},
				}, nil)
			},
			ExpectedConfig: &model.Config{
				Local: model.Local{Enabled: true},
				LDAP: model.LDAP{
					Enabled:    false,
					LDAPConfig: model.LDAPConfig{Host: "ldap.example.org", Port: 636},
				},
			},
		},
		"should return ErrNotFound if the config does not exist": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(nil, nil)
			},
			ExpectedErr: db.ErrNotFound.Error(),
		},
		"should return an error if the DB query fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return(nil, errors.New("connection refused"))
			},
			ExpectedErr: "connection refused",
		},
		"should return an error if decoding the result fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("auth")).Return("not a map", nil)
			},
			ExpectedErr: "read db response: rethinkdb: could not decode type string into Go value of type model.Config",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			dbMock := r.NewMock()
			tc.PrepareDB(dbMock)

			c := &model.Config{}
			err := c.Load(t.Context(), dbMock)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
				assert.Equal(tc.ExpectedConfig, c)
			}

			dbMock.AssertExpectations(t)
		})
	}
}

func TestSaveProviderStatus(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Provider    string
		Healthy     bool
		Msg         string
		PrepareDB   func(*r.Mock)
		ExpectedErr string
	}{
		"should work as expected": {
			Provider: "local",
			Healthy:  true,
			Msg:      "",
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Update(map[string]any{
					"auth": map[string]any{
						"local": map[string]any{
							"status": map[string]any{
								"healthy":      true,
								"msg":          "",
								"last_updated": r.Now(),
							},
						},
					},
				})).Return(r.WriteResponse{Replaced: 1}, nil)
			},
		},
		"should write the error message if the provider is unhealthy": {
			Provider: "ldap",
			Healthy:  false,
			Msg:      "dial tcp: i/o timeout",
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Update(map[string]any{
					"auth": map[string]any{
						"ldap": map[string]any{
							"status": map[string]any{
								"healthy":      false,
								"msg":          "dial tcp: i/o timeout",
								"last_updated": r.Now(),
							},
						},
					},
				})).Return(r.WriteResponse{Replaced: 1}, nil)
			},
		},
		"should return an error if the DB update fails": {
			Provider: "saml",
			Healthy:  true,
			Msg:      "",
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Update(map[string]any{
					"auth": map[string]any{
						"saml": map[string]any{
							"status": map[string]any{
								"healthy":      true,
								"msg":          "",
								"last_updated": r.Now(),
							},
						},
					},
				})).Return(nil, errors.New("connection refused"))
			},
			ExpectedErr: "update provider status: connection refused",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			dbMock := r.NewMock()
			tc.PrepareDB(dbMock)

			err := model.SaveProviderStatus(t.Context(), dbMock, tc.Provider, tc.Healthy, tc.Msg)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)

				var dbErr *db.Err
				assert.ErrorAs(err, &dbErr)
			} else {
				assert.NoError(err)
			}

			dbMock.AssertExpectations(t)
		})
	}
}
