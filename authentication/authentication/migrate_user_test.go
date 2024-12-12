package authentication_test

import (
	"context"
	"testing"

	"gitlab.com/isard/isardvdi/authentication/authentication"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/token"
	apiJWT "gitlab.com/isard/isardvdi/pkg/jwt"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestMigrateUser(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareToken func() string
		UserID       string
		ExpectedErr  string
		CheckToken   func(string)
	}{
		"should work as expected": {
			PrepareToken: func() string {
				tkn, err := apiJWT.SignAPIJWT("")

				require.NoError(err)

				return tkn
			},
			UserID: "néfix",
			CheckToken: func(ss string) {
				claims, err := token.ParseUserMigrationToken("", ss)

				require.NoError(err)

				// Cleanup expiration time
				claims.ExpiresAt = nil
				claims.NotBefore = nil
				claims.IssuedAt = nil

				assert.Equal(&token.UserMigrationClaims{
					TypeClaims: token.TypeClaims{
						RegisteredClaims: &jwt.RegisteredClaims{
							Issuer: "isard-authentication",
						},
						KeyID: "isardvdi",
						Type:  token.TypeUserMigration,
					},
					UserID: "néfix",
				}, claims)
			},
		},
		"should return an error if there's an error parsing the token": {
			PrepareToken: func() string {
				return ""
			},
			ExpectedErr: "error parsing the JWT token: token is malformed: token contains an invalid number of segments",
			CheckToken: func(ss string) {
				assert.Equal("", ss)
			},
		},
		"should return an error if the JWT is an invalid type": {
			PrepareToken: func() string {
				tkn, err := token.SignPasswordResetRequiredToken("", "néfix")

				require.NoError(err)

				return tkn
			},
			UserID:      "néfix",
			ExpectedErr: "error parsing the JWT token: token has invalid claims: invalid token type",
			CheckToken: func(ss string) {
				assert.Equal("", ss)
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ctx := context.Background()

			cfg := cfg.New()
			log := log.New("authentication-test", "debug")

			a := authentication.Init(cfg, log, nil, nil, nil, nil)

			tkn, err := a.MigrateUser(ctx, tc.PrepareToken(), tc.UserID)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.CheckToken != nil {
				tc.CheckToken(tkn)
			} else {
				assert.Empty(tkn)
			}
		})
	}
}
