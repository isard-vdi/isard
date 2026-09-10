package ogenclient_test

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
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

// A client per token would keep TestAPIv4ContextHTTPBearer green and break this.
func TestOneClientServesEveryViewerToken(t *testing.T) {
	t.Parallel()

	const viewers = 12

	var opened atomic.Int64
	var mu sync.Mutex
	seen := map[string]int{}

	srv := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		seen[r.Header.Get("Authorization")]++
		mu.Unlock()

		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{}`))
	}))
	srv.Config.ConnState = func(_ net.Conn, state http.ConnState) {
		if state == http.StateNew {
			opened.Add(1)
		}
	}
	srv.Start()
	defer srv.Close()

	cli, err := apiv4.NewClient(
		srv.URL,
		ogenclient.APIv4Context{},
		apiv4.WithClient(ogenclient.NewHTTPClient()),
	)
	require.NoError(t, err)

	round := func() {
		var wg sync.WaitGroup
		for i := range viewers {
			wg.Go(func() {
				ctx := ogenclient.ContextWithAPIv4Token(t.Context(), fmt.Sprintf("viewer-%d", i))
				rsp, err := cli.UserOwnsDesktop(ctx, &apiv4.UserOwnsDesktopRequest{
					ProxyVideo:     apiv4.NewOptNilString("isard-video"),
					ProxyHyperHost: apiv4.NewOptNilString("isard-hypervisor"),
					Port:           apiv4.NewOptNilInt(5900 + i),
				})
				if !assert.NoError(t, err) {
					return
				}
				assert.IsType(t, &apiv4.EmptyResponse{}, rsp)
			})
		}
		wg.Wait()
	}

	round()
	afterFirst := opened.Load()

	round()

	// No token leaked across requests: the reason one client can replace many.
	require.Len(t, seen, viewers, "each viewer must reach the server with its own token")
	for i := range viewers {
		assert.Equal(t, 2, seen[fmt.Sprintf("Bearer viewer-%d", i)],
			"viewer-%d must be seen once per round", i)
	}

	// A client rebuilt per request would open one connection per request, so
	// twice this. The pool may still dial in the second round when the first
	// left fewer idle connections than the concurrency, which is why the bound
	// is over both rounds rather than an equality between them.
	assert.LessOrEqual(t, opened.Load(), int64(viewers),
		"two rounds of %d viewers must not open more than %d connections", viewers, viewers)
	assert.Positive(t, afterFirst, "the first round must actually connect")
}

// A Timeout on the http.Client would be global to the process, so the deadline
// has to stay on the request.
func TestTheSharedClientKeepsDeadlinesPerRequest(t *testing.T) {
	t.Parallel()

	require.Zero(t, ogenclient.NewHTTPClient().Timeout,
		"a global client Timeout would cap every caller at one value")

	release := make(chan struct{})
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		<-release
	}))
	defer srv.Close()
	defer close(release)

	cli, err := apiv4.NewClient(
		srv.URL,
		ogenclient.APIv4Context{},
		apiv4.WithClient(ogenclient.NewHTTPClient()),
	)
	require.NoError(t, err)

	ctx, cancel := context.WithTimeout(t.Context(), 50*time.Millisecond)
	defer cancel()
	ctx = ogenclient.ContextWithAPIv4Token(ctx, "viewer-slow")

	_, err = cli.UserOwnsDesktop(ctx, &apiv4.UserOwnsDesktopRequest{
		ProxyHyperHost: apiv4.NewOptNilString("isard-hypervisor"),
		Port:           apiv4.NewOptNilInt(5900),
	})

	// The request's own deadline is what stopped it, not a client-wide one.
	require.Error(t, err)
	assert.ErrorIs(t, err, context.DeadlineExceeded)
}
