package token_test

import (
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/token"
	"gitlab.com/isard/isardvdi/pkg/jwt"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestMigrateUser(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareToken func() string
		ExpectedErr  string
	}{
		"should work as expected by using jwt.SignAPIJWT": {
			PrepareToken: func() string {
				tkn, err := jwt.SignAPIJWT("")

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
			ExpectedErr: "error parsing the JWT token: token is malformed: token contains an invalid number of segments",
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
