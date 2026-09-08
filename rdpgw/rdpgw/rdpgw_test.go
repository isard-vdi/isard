// SPDX-License-Identifier: AGPL-3.0-or-later

// Internal test so we can reach the package-level `c` token cache and
// the unexported verifyToken / verifyServer helpers.
package rdpgw

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	"gitlab.com/isard/isardvdi/pkg/ogenclient"
	"gitlab.com/isard/isardvdi/rdpgw/cfg"

	"github.com/bolkedebruin/rdpgw/protocol"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
)

func TestInit(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		IdleTimeout         time.Duration
		ExpectedIdleTimeout int
		// Set by the case that drives the gateway's verify hook to read
		// the user agent off the wire: the client Init builds is
		// reachable no other way, and without one the API logs every Go
		// service as "Go-http-client/1.1".
		ExpectedUserAgent string
	}{
		"should keep the idle timeout in minutes": {
			IdleTimeout:         30 * time.Minute,
			ExpectedIdleTimeout: 30,
		},
		// It is stored as int-minutes, so anything finer is dropped.
		"should drop the fraction if the idle timeout is not whole minutes": {
			IdleTimeout:         90 * time.Second,
			ExpectedIdleTimeout: 1,
		},
		"should identify itself to the api": {
			IdleTimeout:         30 * time.Minute,
			ExpectedIdleTimeout: 30,
			ExpectedUserAgent:   "isardvdi-rdpgw",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			received := make(chan string, 1)
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				received <- r.UserAgent()
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusOK)
				_, _ = w.Write([]byte("{}"))
			}))
			defer srv.Close()

			gwCfg := cfg.Cfg{
				IdleTimeout: tc.IdleTimeout,
				APIAddr:     strings.TrimPrefix(srv.URL, "http://"),
			}

			gw, err := Init(gwCfg)
			require.NoError(t, err)
			require.NotNil(t, gw.ServerConf)

			assert.Equal(tc.ExpectedIdleTimeout, gw.ServerConf.IdleTimeout)

			// Each flag gates an RDP feature downstream viewers rely on;
			// pin them so a bump of the upstream protocol library cannot
			// silently flip a default.
			assert.True(gw.ServerConf.RedirectFlags.Clipboard)
			assert.True(gw.ServerConf.RedirectFlags.Drive)
			assert.True(gw.ServerConf.RedirectFlags.Printer)
			assert.True(gw.ServerConf.RedirectFlags.Port)
			assert.True(gw.ServerConf.RedirectFlags.Pnp)

			// rdpgw opens no tunnel without a JWT the gateway verified.
			assert.True(gw.ServerConf.TokenAuth)
			assert.NotNil(gw.ServerConf.VerifyTunnelCreate)
			assert.NotNil(gw.ServerConf.VerifyServerFunc)

			if tc.ExpectedUserAgent == "" {
				return
			}

			info := &protocol.SessionInfo{ConnId: "conn-" + tc.ExpectedUserAgent}
			ctx := context.WithValue(t.Context(), "SessionInfo", info)

			ok, err := verifyToken(ctx, "the-viewers-jwt")
			require.NoError(t, err)
			assert.True(ok)

			ok, err = gw.ServerConf.VerifyServerFunc(ctx, "10.0.0.1:3389")
			require.NoError(t, err)
			assert.True(ok)

			assert.Equal(tc.ExpectedUserAgent, <-received)
		})
	}
}

func TestVerifyToken(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		ConnID        string
		Tokens        []string
		ExpectedToken string
		ExpectedPanic bool
	}{
		"should cache the token under the connection id": {
			ConnID:        "conn-alpha",
			Tokens:        []string{"my-jwt"},
			ExpectedToken: "my-jwt",
		},
		"should replace the token if the connection sends a second one": {
			ConnID:        "conn-beta",
			Tokens:        []string{"first-jwt", "second-jwt"},
			ExpectedToken: "second-jwt",
		},
		// The upstream library always supplies a SessionInfo, so the
		// bare type assertion is deliberate: a missing one is a
		// programmer error rather than something to handle.
		"should panic if the context carries no session info": {
			ExpectedPanic: true,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			if tc.ExpectedPanic {
				assert.Panics(func() {
					_, _ = verifyToken(t.Context(), "any-jwt")
				})

				return
			}

			info := &protocol.SessionInfo{ConnId: tc.ConnID}
			ctx := context.WithValue(t.Context(), "SessionInfo", info)

			for _, tkn := range tc.Tokens {
				ok, err := verifyToken(ctx, tkn)
				require.NoError(t, err)
				assert.True(ok)
			}

			stored, found := c.Get(tc.ConnID)
			require.True(t, found, "the token must be cached under the connection id")
			assert.Equal(tc.ExpectedToken, stored)
		})
	}
}

func TestVerifyServer(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	// A mock with no expectations proves the API is never reached.
	noAPICall := func(t *testing.T) apiv4.Invoker {
		return apiv4.NewMockInvoker(t)
	}

	// answers builds a mock returning res and err for the request rdpgw
	// should make, authenticated with the connection's own token.
	answers := func(tkn string, res apiv4.UserOwnsDesktopRes, err error) func(*testing.T) apiv4.Invoker {
		return func(t *testing.T) apiv4.Invoker {
			cli := apiv4.NewMockInvoker(t)
			cli.On("UserOwnsDesktop",
				mock.MatchedBy(func(ctx context.Context) bool {
					bearer, bearerErr := ogenclient.APIv4Context{}.HTTPBearer(ctx, "UserOwnsDesktop")
					return bearerErr == nil && bearer.Token == tkn
				}),
				&apiv4.UserOwnsDesktopRequest{IP: apiv4.NewOptNilString("10.0.0.1")},
			).Return(res, err)

			return cli
		}
	}

	cases := map[string]struct {
		ConnID      string
		Token       string
		Host        string
		PrepareMock func(*testing.T) apiv4.Invoker
		ExpectedErr string
	}{
		"should authorize the host the cached token owns": {
			ConnID:      "conn-owned",
			Token:       "the-viewers-jwt",
			Host:        "10.0.0.1:3389",
			PrepareMock: answers("the-viewers-jwt", &apiv4.EmptyResponse{}, nil),
		},
		"should return an error if no token was cached for the connection": {
			ConnID:      "conn-no-token",
			Host:        "10.0.0.1:3389",
			PrepareMock: noAPICall,
			ExpectedErr: "missing token",
		},
		"should return an error if the host carries no port": {
			ConnID:      "conn-bad-host",
			Token:       "my-jwt",
			Host:        "not-a-host-port",
			PrepareMock: noAPICall,
			ExpectedErr: "split host ip and port",
		},
		"should deny if the token does not own the host": {
			ConnID:      "conn-forbidden",
			Token:       "someone-elses-jwt",
			Host:        "10.0.0.1:3389",
			PrepareMock: answers("someone-elses-jwt", &apiv4.UserOwnsDesktopForbidden{}, nil),
			ExpectedErr: "unauthorized",
		},
		"should deny if the API answers something unexpected": {
			ConnID:      "conn-not-found",
			Token:       "orphan-jwt",
			Host:        "10.0.0.1:3389",
			PrepareMock: answers("orphan-jwt", &apiv4.UserOwnsDesktopNotFound{}, nil),
			ExpectedErr: "unexpected API response",
		},
		// The API being unreachable must deny, never open the tunnel.
		"should deny if the API cannot be reached": {
			ConnID:      "conn-api-down",
			Token:       "unlucky-jwt",
			Host:        "10.0.0.1:3389",
			PrepareMock: answers("unlucky-jwt", nil, errors.New("connection refused")),
			ExpectedErr: "unknown error",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			info := &protocol.SessionInfo{ConnId: tc.ConnID}
			ctx := context.WithValue(t.Context(), "SessionInfo", info)

			if tc.Token != "" {
				_, _ = verifyToken(ctx, tc.Token)
			}

			cli := tc.PrepareMock(t)

			ok, err := verifyServer(cli)(ctx, tc.Host)

			if tc.ExpectedErr != "" {
				assert.False(ok)
				assert.ErrorContains(err, tc.ExpectedErr)

				return
			}

			assert.Nil(err)
			assert.True(ok)
		})
	}
}
