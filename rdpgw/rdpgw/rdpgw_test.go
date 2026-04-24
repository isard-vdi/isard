// SPDX-License-Identifier: AGPL-3.0-or-later

// Internal test so we can reach the package-level `c` token cache and
// the unexported verifyToken / verifyServer helpers.
package rdpgw

import (
	"context"
	"testing"
	"time"

	"github.com/bolkedebruin/rdpgw/protocol"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"gitlab.com/isard/isardvdi/rdpgw/cfg"
)

// --- Init ----------------------------------------------------------------

func TestInitReturnsGatewayWithRedirectFlagsEnabled(t *testing.T) {
	gw := Init(cfg.Cfg{IdleTimeout: 30 * time.Minute})
	require.NotNil(t, gw)
	require.NotNil(t, gw.ServerConf)

	// Redirect flags the IsardVDI gateway MUST expose. Each one gates a
	// specific RDP feature that downstream viewers rely on. Pin them so
	// a bump of the upstream protocol library doesn't silently flip a
	// default.
	assert.True(t, gw.ServerConf.RedirectFlags.Clipboard, "clipboard redirection must be enabled")
	assert.True(t, gw.ServerConf.RedirectFlags.Drive, "drive redirection must be enabled")
	assert.True(t, gw.ServerConf.RedirectFlags.Printer, "printer redirection must be enabled")
	assert.True(t, gw.ServerConf.RedirectFlags.Port, "port redirection must be enabled")
	assert.True(t, gw.ServerConf.RedirectFlags.Pnp, "plug-and-play redirection must be enabled")

	// TokenAuth is the IsardVDI-specific guard — rdpgw won't open a
	// tunnel without a JWT that the Gateway has verified.
	assert.True(t, gw.ServerConf.TokenAuth)

	// Hooks must be wired up; their behaviour is tested below.
	assert.NotNil(t, gw.ServerConf.VerifyTunnelCreate)
	assert.NotNil(t, gw.ServerConf.VerifyServerFunc)
}

func TestInitIdleTimeoutIsMinutesFloor(t *testing.T) {
	// Init stores the idle timeout as int-minutes (dropping sub-minute
	// precision). Pin that contract so a future refactor to seconds
	// has to update this test.
	gw := Init(cfg.Cfg{IdleTimeout: 90 * time.Second}) // 1.5 minutes
	assert.Equal(t, 1, gw.ServerConf.IdleTimeout,
		"IdleTimeout is stored as int-minutes; fractional minutes are dropped")

	gw = Init(cfg.Cfg{IdleTimeout: 30 * time.Minute})
	assert.Equal(t, 30, gw.ServerConf.IdleTimeout)
}

// --- verifyToken ---------------------------------------------------------

func TestVerifyTokenStoresTokenInCacheKeyedByConnID(t *testing.T) {
	// Clear any state from a previous run.
	c.Flush()

	info := &protocol.SessionInfo{ConnId: "conn-alpha"}
	ctx := context.WithValue(context.Background(), "SessionInfo", info)

	ok, err := verifyToken(ctx, "my-jwt")
	require.NoError(t, err)
	assert.True(t, ok)

	// The next hook (verifyServer) looks up the JWT by ConnId; pin that
	// contract.
	stored, found := c.Get("conn-alpha")
	require.True(t, found, "token must be cached under the SessionInfo.ConnId key")
	assert.Equal(t, "my-jwt", stored)
}

func TestVerifyTokenOverwritesExistingEntry(t *testing.T) {
	c.Flush()

	info := &protocol.SessionInfo{ConnId: "conn-beta"}
	ctx := context.WithValue(context.Background(), "SessionInfo", info)

	_, _ = verifyToken(ctx, "first-jwt")
	_, _ = verifyToken(ctx, "second-jwt")

	stored, found := c.Get("conn-beta")
	require.True(t, found)
	assert.Equal(t, "second-jwt", stored,
		"repeat verifyToken on the same ConnId must replace the prior JWT")
}

func TestVerifyTokenPanicsWithoutSessionInfo(t *testing.T) {
	// The upstream rdpgw library always supplies a SessionInfo in the
	// context; a missing one is a programmer error. The current
	// implementation type-asserts without the comma-ok idiom, so it
	// panics. Pin that behaviour — if a future refactor wants to be
	// defensive, this test must be updated alongside the change.
	defer func() {
		assert.NotNil(t, recover(), "verifyToken must panic on missing SessionInfo")
	}()
	_, _ = verifyToken(context.Background(), "any-jwt")
}

// --- verifyServer --------------------------------------------------------

func TestVerifyServerFailsWhenTokenMissing(t *testing.T) {
	c.Flush()
	fn := verifyServer("does-not-matter:5000")

	info := &protocol.SessionInfo{ConnId: "conn-no-token"}
	ctx := context.WithValue(context.Background(), "SessionInfo", info)

	// No prior verifyToken → cache miss → error.
	ok, err := fn(ctx, "10.0.0.1:3389")
	assert.False(t, ok)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "missing token")
}

func TestVerifyServerFailsOnMalformedHost(t *testing.T) {
	c.Flush()
	info := &protocol.SessionInfo{ConnId: "conn-bad-host"}
	ctx := context.WithValue(context.Background(), "SessionInfo", info)
	_, _ = verifyToken(ctx, "my-jwt") // seed the cache so we pass the first guard

	fn := verifyServer("does-not-matter:5000")
	ok, err := fn(ctx, "not-a-host-port")
	assert.False(t, ok)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "split host ip and port",
		"should wrap net.SplitHostPort error")
}
