package token_test

import (
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestParseLoginToken(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)
	now := float64(time.Now().Unix())

	cases := map[string]struct {
		PrepareToken func() string
		ExpectedErr  string
		ExpectedErrs []error
		CheckToken   func(jwt.Claims)
	}{
		"should work if the token is a valid login token": {
			PrepareToken: func() string {
				ss, err := token.SignLoginToken("", time.Now().Add(time.Hour), "ThoJuroQueEsUnID", &model.User{
					ID:                     "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					UID:                    "nefix",
					Username:               "nefix",
					Password:               "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
					Provider:               "local",
					Active:                 true,
					Category:               "default",
					Role:                   "user",
					Group:                  "default-default",
					Name:                   "Néfix Estrada",
					Email:                  "nefix@example.org",
					EmailVerified:          &now,
					DisclaimerAcknowledged: true,
				})
				require.NoError(err)

				return ss
			},
			CheckToken: func(c jwt.Claims) {
				claims, ok := c.(*token.LoginClaims)

				assert.True(ok)

				claims.ExpiresAt = nil
				claims.IssuedAt = nil
				claims.NotBefore = nil

				assert.Equal(&token.LoginClaims{
					RegisteredClaims: &jwt.RegisteredClaims{
						Issuer:  "isard-authentication",
						Subject: "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					},
					KeyID:     "isardvdi",
					SessionID: "ThoJuroQueEsUnID",
					Data: token.LoginClaimsData{
						Provider:   "local",
						ID:         "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
						RoleID:     "user",
						CategoryID: "default",
						GroupID:    "default-default",
						Name:       "Néfix Estrada",
					},
				}, claims)
			},
		},
		"should return an invalid token error if the token is malformed": {
			PrepareToken: func() string {
				return "HOLA MELINA :D"
			},
			ExpectedErr:  "invalid JWT token: token is malformed: token contains an invalid number of segments",
			ExpectedErrs: []error{token.ErrInvalidToken, jwt.ErrTokenMalformed},
		},
		"should return an invalid token error if the token is signed with another secret": {
			PrepareToken: func() string {
				ss, err := token.SignLoginToken("melina's secret", time.Now().Add(time.Hour), "ThoJuroQueEsUnID", &model.User{
					ID: "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
				})
				require.NoError(err)

				return ss
			},
			ExpectedErr:  "invalid JWT token: token signature is invalid: signature is invalid",
			ExpectedErrs: []error{token.ErrInvalidToken, jwt.ErrTokenSignatureInvalid},
		},
		"should return an invalid token error if the token is expired": {
			PrepareToken: func() string {
				ss, err := token.SignLoginToken("", time.Now().Add(-time.Hour), "ThoJuroQueEsUnID", &model.User{
					ID:                     "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					UID:                    "nefix",
					Username:               "nefix",
					Password:               "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
					Provider:               "local",
					Active:                 true,
					Category:               "default",
					Role:                   "user",
					Group:                  "default-default",
					Name:                   "Néfix Estrada",
					Email:                  "nefix@example.org",
					EmailVerified:          &now,
					DisclaimerAcknowledged: true,
				})
				require.NoError(err)

				return ss
			},
			ExpectedErr:  "invalid JWT token: token has invalid claims: token is expired",
			ExpectedErrs: []error{token.ErrInvalidToken, jwt.ErrTokenExpired},
		},
		"should return an invalid token error if the token is not of type login": {
			PrepareToken: func() string {
				ss, err := token.SignDisclaimerAcknowledgementRequiredToken("", "néfix :D")
				require.NoError(err)

				return ss
			},
			ExpectedErr:  "invalid JWT token: token has invalid claims: invalid token type",
			ExpectedErrs: []error{token.ErrInvalidToken, token.ErrInvalidTokenType},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			claims, err := token.ParseLoginToken("", tc.PrepareToken())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			for _, expectedErr := range tc.ExpectedErrs {
				assert.ErrorIs(err, expectedErr)
			}

			if tc.CheckToken != nil {
				tc.CheckToken(claims)
			}
		})
	}
}

func TestParseCallbackToken(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareToken func() string
		ExpectedErr  string
		CheckToken   func(jwt.Claims)
	}{
		"should work if the token is a valid callback token": {
			PrepareToken: func() string {
				ss, err := token.SignCallbackToken("", "local", "default", "/")
				require.NoError(err)

				return ss
			},
			CheckToken: func(c jwt.Claims) {
				claims, ok := c.(*token.CallbackClaims)

				assert.True(ok)

				claims.ExpiresAt = nil
				claims.IssuedAt = nil
				claims.NotBefore = nil

				assert.Equal(&token.CallbackClaims{
					TypeClaims: token.TypeClaims{
						RegisteredClaims: &jwt.RegisteredClaims{
							Issuer: "isard-authentication",
						},
						KeyID: "isardvdi",
						Type:  token.TypeCallback,
					},
					Provider:   "local",
					CategoryID: "default",
					Redirect:   "/",
				}, claims)
			},
		},
		"should return an error if the token is not of type callback": {
			PrepareToken: func() string {
				ss, err := token.SignDisclaimerAcknowledgementRequiredToken("", "néfix :D")
				require.NoError(err)

				return ss
			},
			ExpectedErr: "invalid JWT token: token has invalid claims: invalid token type",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			claims, err := token.ParseCallbackToken("", tc.PrepareToken())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.CheckToken != nil {
				tc.CheckToken(claims)
			}
		})
	}
}

func TestParsePasswordResetToken(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareToken func() string
		ExpectedErr  string
		CheckToken   func(jwt.Claims)
	}{
		"should work if the token is a valid password-reset token": {
			PrepareToken: func() string {
				ss, err := token.SignPasswordResetToken("", "néfix! :D")
				require.NoError(err)

				return ss
			},
			CheckToken: func(c jwt.Claims) {
				claims, ok := c.(*token.PasswordResetClaims)

				assert.True(ok)

				claims.ExpiresAt = nil
				claims.IssuedAt = nil
				claims.NotBefore = nil

				assert.Equal(&token.PasswordResetClaims{
					TypeClaims: token.TypeClaims{
						RegisteredClaims: &jwt.RegisteredClaims{
							Issuer: "isard-authentication",
						},
						KeyID: "isardvdi",
						Type:  token.TypePasswordReset,
					},
					UserID: "néfix! :D",
				}, claims)
			},
		},
		"should return an error if the token is not of type password-reset": {
			PrepareToken: func() string {
				ss, err := token.SignDisclaimerAcknowledgementRequiredToken("", "néfix :D")
				require.NoError(err)

				return ss
			},
			ExpectedErr: "invalid JWT token: token has invalid claims: invalid token type",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			claims, err := token.ParsePasswordResetToken("", tc.PrepareToken())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.CheckToken != nil {
				tc.CheckToken(claims)
			}
		})
	}
}

func TestParseCategorySelectToken(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareToken func() string
		ExpectedErr  string
		CheckToken   func(jwt.Claims)
	}{
		"should work if the token is a valid category-select token": {
			PrepareToken: func() string {
				rawRoles := []string{"admin", "melina", "potato"}

				ss, err := token.SignCategorySelectToken("", []*model.Category{{
					ID:          "Nefics",
					Name:        "Nefix :D",
					Description: "Don't cry Nefics",
				}}, nil, &rawRoles, &types.ProviderUserData{
					Provider: "SAML",
					Category: "Test cat",
					UID:      "0000000",
				})
				require.NoError(err)

				return ss
			},
			CheckToken: func(c jwt.Claims) {
				claims, ok := c.(*token.CategorySelectClaims)

				assert.True(ok)

				claims.ExpiresAt = nil
				claims.IssuedAt = nil
				claims.NotBefore = nil

				rawRoles := []string{"admin", "melina", "potato"}

				assert.Equal(&token.CategorySelectClaims{
					TypeClaims: token.TypeClaims{
						RegisteredClaims: &jwt.RegisteredClaims{
							Issuer: "isard-authentication",
						},
						KeyID: "isardvdi",
						Type:  token.TypeCategorySelect,
					},
					Categories: []token.CategorySelectClaimsCategory{{
						ID:    "Nefics",
						Name:  "Nefix :D",
						Photo: "",
					}},
					RawRoles: &rawRoles,
					User: types.ProviderUserData{
						Provider: "SAML",
						Category: "Test cat",
						UID:      "0000000",
					},
				}, claims)
			},
		},
		"should return an error if the token is not of type category-select": {
			PrepareToken: func() string {
				ss, err := token.SignDisclaimerAcknowledgementRequiredToken("", "néfix :D")
				require.NoError(err)

				return ss
			},
			ExpectedErr: "invalid JWT token: token has invalid claims: invalid token type",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			claims, err := token.ParseCategorySelectToken("", tc.PrepareToken())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.CheckToken != nil {
				tc.CheckToken(claims)
			}
		})
	}
}

func TestParseUserMigrationRequiredToken(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareToken func() string
		ExpectedErr  string
		CheckToken   func(jwt.Claims)
	}{
		"should work if the token is a valid user-migration-required token": {
			PrepareToken: func() string {
				ss, err := token.SignUserMigrationRequiredToken("", "néfix! :D")
				require.NoError(err)

				return ss
			},
			CheckToken: func(c jwt.Claims) {
				claims, ok := c.(*token.UserMigrationRequiredClaims)

				assert.True(ok)

				claims.ExpiresAt = nil
				claims.IssuedAt = nil
				claims.NotBefore = nil

				assert.Equal(&token.UserMigrationRequiredClaims{
					TypeClaims: token.TypeClaims{
						RegisteredClaims: &jwt.RegisteredClaims{
							Issuer: "isard-authentication",
						},
						KeyID: "isardvdi",
						Type:  token.TypeUserMigrationRequired,
					},
					UserID: "néfix! :D",
				}, claims)
			},
		},
		"should return an error if the token is not of type user-migration-required": {
			PrepareToken: func() string {
				ss, err := token.SignDisclaimerAcknowledgementRequiredToken("", "néfix :D")
				require.NoError(err)

				return ss
			},
			ExpectedErr: "invalid JWT token: token has invalid claims: invalid token type",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			claims, err := token.ParseUserMigrationRequiredToken("", tc.PrepareToken())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.CheckToken != nil {
				tc.CheckToken(claims)
			}
		})
	}
}

func TestParseReRegisterToken(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareToken func() string
		ExpectedErr  string
		CheckToken   func(jwt.Claims)
	}{
		"should work if the token is a valid re-register token": {
			PrepareToken: func() string {
				ss, err := token.SignReRegisterToken("", &model.User{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
					Role:     model.RoleManager,
				})
				require.NoError(err)

				return ss
			},
			CheckToken: func(c jwt.Claims) {
				claims, ok := c.(*token.ReRegisterClaims)

				assert.True(ok)

				claims.ExpiresAt = nil
				claims.IssuedAt = nil
				claims.NotBefore = nil

				assert.Equal(&token.ReRegisterClaims{
					TypeClaims: token.TypeClaims{
						RegisteredClaims: &jwt.RegisteredClaims{
							Issuer: "isard-authentication",
						},
						KeyID: "isardvdi",
						Type:  token.TypeReRegister,
					},
					Provider:   "saml",
					UserID:     "nefix-uid",
					CategoryID: "default",
					RoleID:     "manager",
				}, claims)
			},
		},
		"should return an error if the token is not of type re-register": {
			PrepareToken: func() string {
				ss, err := token.SignRegisterToken("", &model.User{
					Provider: "saml",
					Category: "default",
					UID:      "nefix-uid",
				})
				require.NoError(err)

				return ss
			},
			ExpectedErr: "invalid JWT token: token has invalid claims: invalid token type",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			claims, err := token.ParseReRegisterToken("", tc.PrepareToken())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.CheckToken != nil {
				tc.CheckToken(claims)
			}
		})
	}
}

func TestParseUserMigrationToken(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareToken func() string
		ExpectedErr  string
		CheckToken   func(jwt.Claims)
	}{
		"should work if the token is a valid user-migration token": {
			PrepareToken: func() string {
				ss, err := token.SignUserMigrationToken("", "néfix! :D")
				require.NoError(err)

				return ss
			},
			CheckToken: func(c jwt.Claims) {
				claims, ok := c.(*token.UserMigrationClaims)

				assert.True(ok)

				claims.ExpiresAt = nil
				claims.IssuedAt = nil
				claims.NotBefore = nil

				assert.Equal(&token.UserMigrationClaims{
					TypeClaims: token.TypeClaims{
						RegisteredClaims: &jwt.RegisteredClaims{
							Issuer: "isard-authentication",
						},
						KeyID: "isardvdi",
						Type:  token.TypeUserMigration,
					},
					UserID: "néfix! :D",
				}, claims)
			},
		},
		"should return an error if the token is not of type user-migration": {
			PrepareToken: func() string {
				ss, err := token.SignDisclaimerAcknowledgementRequiredToken("", "néfix :D")
				require.NoError(err)

				return ss
			},
			ExpectedErr: "invalid JWT token: token has invalid claims: invalid token type",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			claims, err := token.ParseUserMigrationToken("", tc.PrepareToken())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.CheckToken != nil {
				tc.CheckToken(claims)
			}
		})
	}
}
