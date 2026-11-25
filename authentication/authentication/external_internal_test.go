package authentication

import (
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/token"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestExternalUser(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB func(*r.Mock)
		UserID    string

		ExpectedUserID string
		ExpectedErr    string
	}{
		"should return the stored user ID if the user already exists": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("secrets").Get("app-key")).Return([]any{
					map[string]any{
						"id":          "app-key",
						"secret":      "app-secret",
						"domain":      "localhost",
						"category_id": "default",
						"role_id":     "manager",
					},
				}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "app-key"),
					r.Eq(r.Row.Field("external_gid"), "external_app-key"),
				))).Return([]any{
					map[string]any{
						"id": "group-1",
					},
				}, nil)

				m.On(r.Table("users").GetAllByIndex("uid_category_provider", []any{
					"ext-user",
					"default",
					"external_app-key",
				})).Return([]any{
					map[string]any{
						"id": "user-1",
					},
				}, nil)

				m.On(r.Table("users").Get("user-1")).Return([]any{
					map[string]any{
						"id": "user-1",
					},
				}, nil)
			},
			UserID: "ext-user",

			ExpectedUserID: "user-1",
			ExpectedErr:    ErrUserAlreadyExists.Error(),
		},
		"should return ErrEmptyUserUID if the user ID is empty": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("secrets").Get("app-key")).Return([]any{
					map[string]any{
						"id":          "app-key",
						"secret":      "app-secret",
						"domain":      "localhost",
						"category_id": "default",
						"role_id":     "manager",
					},
				}, nil)
			},
			UserID: "",

			ExpectedErr: "provider external_app-key, category default: empty user uid",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			dbMock := r.NewMock()
			tc.PrepareDB(dbMock)

			a := &Authentication{
				Log: log.New("authentication-test", "debug"),
				DB:  dbMock,
			}

			claims := &token.ExternalClaims{
				TypeClaims: token.TypeClaims{
					RegisteredClaims: &jwt.RegisteredClaims{
						ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
						IssuedAt:  jwt.NewNumericDate(time.Now()),
					},
					KeyID: "app-key",
					Type:  token.TypeExternal,
				},
				Role:       "manager",
				Domain:     "localhost",
				CategoryID: "default",
			}

			tkn, err := jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString([]byte("app-secret"))
			require.NoError(t, err)

			userID, err := a.ExternalUser(t.Context(), tkn, tc.UserID, "user", "nefix", "Néfix Estrada", "", "")

			assert.EqualError(err, tc.ExpectedErr)
			assert.Equal(tc.ExpectedUserID, userID)

			dbMock.AssertExpectations(t)
		})
	}
}
