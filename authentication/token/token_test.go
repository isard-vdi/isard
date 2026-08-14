package token_test

import (
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/token"
	pkgJWT "gitlab.com/isard/isardvdi/pkg/jwt"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestGetTokenExpiration(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareToken func() string
		Expected     time.Time
		ExpectedErr  string
	}{
		"should work as expected": {
			PrepareToken: func() string {
				expiration := time.Date(2026, 8, 13, 12, 0, 0, 0, time.UTC)

				ss, err := token.SignLoginToken("", expiration, "ThoJuroQueEsUnID", &model.User{
					ID: "local-default-admin-admin",
				})
				require.NoError(err)

				return ss
			},
			Expected: time.Date(2026, 8, 13, 12, 0, 0, 0, time.UTC),
		},
		"should return an error if the token can't be parsed": {
			PrepareToken: func() string {
				return "notatoken"
			},
			ExpectedErr: "parse the JWT token: token is malformed: token contains an invalid number of segments",
		},
		"should return an error if the token doesn't have an expiration": {
			PrepareToken: func() string {
				ss, err := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.MapClaims{}).SignedString([]byte(""))
				require.NoError(err)

				return ss
			},
			ExpectedErr: token.ErrTokenWithoutExpiration.Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			exp, err := token.GetTokenExpiration(tc.PrepareToken())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.Expected, exp.UTC())
		})
	}
}

func TestMigrateUser(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareToken func() string
		ExpectedErr  string
	}{
		"should work as expected by using jwt.SignAPIJWT": {
			PrepareToken: func() string {
				tkn, err := pkgJWT.SignAPIJWT("")

				require.NoError(err)

				return tkn
			},
		},
		"should work as expected by using a custom token with 'isardvdi-service' as session ID": {
			PrepareToken: func() string {
				tkn, err := token.SignLoginToken("", time.Now().Add(time.Hour), "isardvdi-service", &model.User{
					ID: "local-default-admin-admin",
				})

				require.NoError(err)

				return tkn
			},
		},
		"should return an error if the token is not from 'isardvdi-service'": {
			PrepareToken: func() string {
				tkn, err := token.SignLoginToken("", time.Now().Add(time.Hour), "1234567890", &model.User{
					ID: "local-default-admin-admin",
				})

				require.NoError(err)

				return tkn
			},
			ExpectedErr: token.ErrInvalidTokenType.Error(),
		},
		"should return an error if there's an error parsing the token": {
			PrepareToken: func() string {
				return ""
			},
			ExpectedErr: "invalid JWT token: token is malformed: token contains an invalid number of segments",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			err := token.TokenIsIsardvdiService("", tc.PrepareToken())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}
		})
	}
}
