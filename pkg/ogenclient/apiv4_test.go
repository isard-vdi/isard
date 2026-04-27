package ogenclient_test

import (
	"errors"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	"gitlab.com/isard/isardvdi/pkg/ogenclient"
)

var (
	_ apiv4.SecuritySource = ogenclient.APIv4Source{}
	_ apiv4.SecuritySource = ogenclient.APIv4Static{}
)

func TestAPIv4Source_HTTPBearer(t *testing.T) {
	t.Parallel()

	const secret = "test-secret"

	src := ogenclient.APIv4Source{Secret: secret}
	bearer, err := src.HTTPBearer(t.Context(), "TestOp")
	require.NoError(t, err)
	assert.NotEmpty(t, bearer.Token)

	parsed, parseErr := jwt.Parse(bearer.Token, func(tok *jwt.Token) (any, error) {
		_, ok := tok.Method.(*jwt.SigningMethodHMAC)
		if !ok {
			return nil, errors.New("expected HMAC signing method")
		}
		return []byte(secret), nil
	})
	require.NoError(t, parseErr)

	claims, ok := parsed.Claims.(jwt.MapClaims)
	require.True(t, ok)

	assert.Equal(t, "isardvdi", claims["kid"])
	assert.Equal(t, "isardvdi-service", claims["session_id"])

	data, ok := claims["data"].(map[string]any)
	require.True(t, ok, "data claim should be a map")
	assert.Equal(t, "admin", data["role_id"])
	assert.Equal(t, "local-default-admin-admin", data["user_id"])
	assert.Equal(t, "default", data["category_id"])

	expClaim, expErr := claims.GetExpirationTime()
	require.NoError(t, expErr)
	assert.True(t, expClaim.After(time.Now()), "token should not be expired")
	assert.WithinDuration(t, time.Now().Add(20*time.Second), expClaim.Time, 5*time.Second)
}

func TestAPIv4Static_HTTPBearer(t *testing.T) {
	t.Parallel()

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
			assert.Equal(t, tc.Token, bearer.Token)
		})
	}
}
