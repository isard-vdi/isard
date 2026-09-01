package ogenclient_test

import (
	"context"
	"errors"
	"testing"
	"time"

	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	"gitlab.com/isard/isardvdi/pkg/ogenclient"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

var (
	_ apiv4.SecuritySource = ogenclient.APIv4Source{}
	_ apiv4.SecuritySource = ogenclient.APIv4Static{}
	_ apiv4.SecuritySource = ogenclient.APIv4Context{}
)

func TestAPIv4SourceHTTPBearer(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Secret string
	}{
		"should sign a token the configured secret verifies": {
			Secret: "test-secret",
		},
		"should sign with whatever secret the source carries": {
			Secret: "another-secret",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			src := ogenclient.APIv4Source{Secret: tc.Secret}

			bearer, err := src.HTTPBearer(t.Context(), "TestOp")
			require.NoError(t, err)
			assert.NotEmpty(bearer.Token)

			keyFunc := func(tok *jwt.Token) (any, error) {
				if _, ok := tok.Method.(*jwt.SigningMethodHMAC); !ok {
					return nil, errors.New("expected HMAC signing method")
				}

				return []byte(tc.Secret), nil
			}

			parsed, err := jwt.Parse(bearer.Token, keyFunc)
			require.NoError(t, err)

			claims, ok := parsed.Claims.(jwt.MapClaims)
			require.True(t, ok)

			assert.Equal("isardvdi", claims["kid"])
			assert.Equal("isardvdi-service", claims["session_id"])

			data, ok := claims["data"].(map[string]any)
			require.True(t, ok, "data claim should be a map")
			assert.Equal("admin", data["role_id"])
			assert.Equal("local-default-admin-admin", data["user_id"])
			assert.Equal("default", data["category_id"])

			exp, err := claims.GetExpirationTime()
			require.NoError(t, err)
			assert.True(exp.After(time.Now()), "token should not be expired")
			assert.WithinDuration(time.Now().Add(20*time.Second), exp.Time, 5*time.Second)
		})
	}
}

func TestAPIv4StaticHTTPBearer(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Token string
	}{
		"should return the exact configured token":                    {Token: "my-static-token"},
		"should return empty token when configured with empty string": {Token: ""},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			src := ogenclient.APIv4Static{Token: tc.Token}

			bearer, err := src.HTTPBearer(t.Context(), "TestOp")
			require.NoError(t, err)
			assert.Equal(tc.Token, bearer.Token)
		})
	}
}

func TestAPIv4ContextHTTPBearer(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareCtx    func(context.Context) context.Context
		ExpectedToken string
		ExpectedErr   string
	}{
		"should return the token carried by the context": {
			PrepareCtx: func(ctx context.Context) context.Context {
				return ogenclient.ContextWithAPIv4Token(ctx, "my-request-token")
			},
			ExpectedToken: "my-request-token",
		},
		"should return an error if the context carries no token": {
			PrepareCtx: func(ctx context.Context) context.Context {
				return ctx
			},
			ExpectedErr: "no apiv4 token in the context",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			ctx := tc.PrepareCtx(t.Context())

			src := ogenclient.APIv4Context{}
			bearer, err := src.HTTPBearer(ctx, "TestOp")

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
				assert.ErrorIs(err, ogenclient.ErrMissingToken)
			} else {
				assert.Nil(err)
				assert.Equal(tc.ExpectedToken, bearer.Token)
			}
		})
	}
}
