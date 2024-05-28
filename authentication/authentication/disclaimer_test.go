package authentication_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/authentication"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/token"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestAcknowledgeDisclaimer(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareDB    func(*r.Mock)
		PrepareToken func() string
		ExpectedErr  string
	}{
		"should work as expected": {
			PrepareToken: func() string {
				ss, err := token.SignDisclaimerAcknowledgementRequiredToken("", "néfix :3")
				require.NoError(err)

				return ss
			},
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("néfix :3").Update(map[string]interface{}{
					"disclaimer_acknowledged": true,
				})).Return(r.WriteResponse{
					Updated: 1,
				}, nil)
			},
		},
		"should return an error if the JWT is invalid": {
			PrepareToken: func() string {
				tkn := jwt.NewWithClaims(jwt.SigningMethodHS256, &token.DisclaimerAcknowledgementRequiredClaims{
					TypeClaims: token.TypeClaims{
						RegisteredClaims: &jwt.RegisteredClaims{
							ExpiresAt: jwt.NewNumericDate(time.Now().Add(-60 * time.Minute)), // This token is expired!
							IssuedAt:  jwt.NewNumericDate(time.Now()),
							NotBefore: jwt.NewNumericDate(time.Now()),
							Issuer:    "isard-authentication",
						},
						KeyID: "isardvdi",
						Type:  token.TypeDisclaimerAcknowledgementRequired,
					},
					UserID: "néfix néfix imagine this is an UUID",
				})

				ss, err := tkn.SignedString([]byte(""))
				require.NoError(err)

				return ss
			},
			ExpectedErr: "error parsing the JWT token: token has invalid claims: token is expired",
		},
		"should return an error if the JWT is not of disclaimer-acknowledgementrequired": {
			PrepareToken: func() string {
				ss, err := token.SignCallbackToken("", "local", "default", "")
				require.NoError(err)

				return ss
			},
			ExpectedErr: "error parsing the JWT token: token has invalid claims: invalid token type",
		},
		"should return an error if there's an error updating the DB": {
			PrepareToken: func() string {
				ss, err := token.SignDisclaimerAcknowledgementRequiredToken("", "néfix :3")
				require.NoError(err)

				return ss
			},
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Get("néfix :3").Update(map[string]interface{}{
					"disclaimer_acknowledged": true,
				})).Return(nil, errors.New("hello there!"))
			},
			ExpectedErr: "error updating the DB: hello there!",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			cfg := cfg.New()
			log := log.New("authentication-test", "debug")
			mock := r.NewMock()

			if tc.PrepareDB != nil {
				tc.PrepareDB(mock)
			}

			a := authentication.Init(cfg, log, mock, nil, nil, nil)

			err := a.AcknowledgeDisclaimer(context.Background(), tc.PrepareToken())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			mock.AssertExpectations(t)
		})
	}
}
