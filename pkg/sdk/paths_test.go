// SPDX-License-Identifier: AGPL-3.0-or-later

// Path-contract regression guard. Every SDK method must send the exact
// HTTP method + URL path that matches a real apiv4 route. If a route
// gets renamed on the apiv4 side, whichever call site below breaks
// tells you exactly which client consumer (webapp-flask, check, etc.)
// is about to 404 at runtime.

package sdk_test

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"gitlab.com/isard/isardvdi/pkg/sdk"
)

// captureServer records every request; response is a 200 with an
// empty JSON array/object so the SDK's do() doesn't error on decode.
type captureServer struct {
	mu      sync.Mutex
	method  string
	path    string
	rawPath string
	body    string
}

func newCaptureServer(t *testing.T) (*captureServer, *httptest.Server) {
	t.Helper()
	cap := &captureServer{}
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		cap.mu.Lock()
		defer cap.mu.Unlock()
		cap.method = r.Method
		// Strip the /api/v4/ prefix the SDK adds so assertions stay focused
		// on the per-method path the SDK chose.
		cap.path = strings.TrimPrefix(r.URL.Path, "/api/v4/")
		cap.rawPath = r.URL.RawQuery
		if r.Body != nil {
			b, _ := io.ReadAll(r.Body)
			cap.body = string(b)
			_ = r.Body.Close()
		}
		// Return a permissive response so the SDK's JSON decode
		// doesn't fail before we can inspect the captured request.
		w.Header().Set("Content-Type", "application/json")
		if r.Method == http.MethodGet {
			// Handles both list endpoints (which decode into []T) and
			// single-resource endpoints (which decode into T).
			// `null` parses into any type without error.
			_, _ = w.Write([]byte(`null`))
		} else {
			_, _ = w.Write([]byte(`{}`))
		}
	}))
	t.Cleanup(srv.Close)
	return cap, srv
}

func newClient(t *testing.T, srv *httptest.Server) *sdk.Client {
	t.Helper()
	c, err := sdk.NewClient(&sdk.Cfg{Host: srv.URL, Token: "test-token"})
	require.NoError(t, err)
	return c
}

// --- main path-contract table --------------------------------------------

func TestSDKPaths(t *testing.T) {
	ctx := context.Background()

	cases := []struct {
		name       string
		method     string
		path       string
		invoke     func(c *sdk.Client) error
		rawQuery   string // optional — if set, assert URL.RawQuery matches
		assertBody func(t *testing.T, body string)
	}{
		// --- desktop (item_router) -----------------------------------
		{
			name:   "DesktopList",
			method: http.MethodGet,
			path:   "item/user/desktops",
			invoke: func(c *sdk.Client) error { _, err := c.DesktopList(ctx); return err },
		},
		{
			name:   "DesktopGet",
			method: http.MethodGet,
			path:   "item/user/desktop/desk-1",
			invoke: func(c *sdk.Client) error { _, err := c.DesktopGet(ctx, "desk-1"); return err },
		},
		{
			name:   "DesktopCreate",
			method: http.MethodPost,
			path:   "item/desktop",
			invoke: func(c *sdk.Client) error {
				_, err := c.DesktopCreate(ctx, "desk-1", "tpl-1")
				return err
			},
			assertBody: func(t *testing.T, body string) {
				assert.Contains(t, body, `"name":"desk-1"`)
				assert.Contains(t, body, `"template_id":"tpl-1"`)
			},
		},
		{
			name:   "DesktopDelete",
			method: http.MethodDelete,
			path:   "item/desktop/desk-1",
			invoke: func(c *sdk.Client) error { return c.DesktopDelete(ctx, "desk-1") },
		},
		{
			name:   "DesktopStart",
			method: http.MethodPut,
			path:   "item/desktop/desk-1/start",
			invoke: func(c *sdk.Client) error { return c.DesktopStart(ctx, "desk-1") },
		},
		{
			name:   "DesktopStop",
			method: http.MethodPut,
			path:   "item/desktop/desk-1/stop",
			invoke: func(c *sdk.Client) error { return c.DesktopStop(ctx, "desk-1") },
		},
		{
			name:   "DesktopViewer",
			method: http.MethodGet,
			path:   "item/desktop/desk-1/get-viewer/browser-rdp",
			invoke: func(c *sdk.Client) error {
				_, err := c.DesktopViewer(ctx, sdk.DesktopViewerRdpBrowser, "desk-1")
				return err
			},
		},
		// --- template (item_router) ----------------------------------
		{
			name:   "TemplateList",
			method: http.MethodGet,
			path:   "items/templates",
			invoke: func(c *sdk.Client) error { _, err := c.TemplateList(ctx); return err },
		},
		{
			name:   "TemplateCreateFromDesktop",
			method: http.MethodPost,
			path:   "item/template",
			invoke: func(c *sdk.Client) error {
				_, err := c.TemplateCreateFromDesktop(ctx, "tpl-1", "desk-1")
				return err
			},
		},
		// --- hypervisor (admin_router) -------------------------------
		{
			name:   "HypervisorList",
			method: http.MethodGet,
			path:   "admin/hypervisors",
			invoke: func(c *sdk.Client) error { _, err := c.HypervisorList(ctx); return err },
		},
		{
			name:   "HypervisorGet",
			method: http.MethodGet,
			path:   "admin/hypervisor/h1",
			invoke: func(c *sdk.Client) error { _, err := c.HypervisorGet(ctx, "h1"); return err },
		},
		{
			name:   "HypervisorDelete",
			method: http.MethodDelete,
			path:   "admin/hypervisor/h1",
			invoke: func(c *sdk.Client) error { return c.HypervisorDelete(ctx, "h1") },
		},
		// --- orchestrator (admin_router) -----------------------------
		{
			name:   "OrchestratorHypervisorList",
			method: http.MethodGet,
			path:   "admin/orchestrator/hypervisors",
			invoke: func(c *sdk.Client) error { _, err := c.OrchestratorHypervisorList(ctx); return err },
		},
		{
			name:   "OrchestratorHypervisorGet",
			method: http.MethodGet,
			path:   "admin/orchestrator/hypervisor/h1",
			invoke: func(c *sdk.Client) error { _, err := c.OrchestratorHypervisorGet(ctx, "h1"); return err },
		},
		{
			name:   "OrchestratorHypervisorManage",
			method: http.MethodPost,
			path:   "admin/orchestrator/hypervisor/h1/manage",
			invoke: func(c *sdk.Client) error { return c.OrchestratorHypervisorManage(ctx, "h1") },
		},
		{
			name:   "OrchestratorHypervisorUnmanage",
			method: http.MethodDelete,
			path:   "admin/orchestrator/hypervisor/h1/manage",
			invoke: func(c *sdk.Client) error { return c.OrchestratorHypervisorUnmanage(ctx, "h1") },
		},
		{
			name:   "OrchestratorGPUBookingList",
			method: http.MethodGet,
			path:   "items/bookings/gpu",
			invoke: func(c *sdk.Client) error { _, err := c.OrchestratorGPUBookingList(ctx); return err },
		},
		// --- admin_user / admin -------------------------------------
		{
			name:   "AdminUserList",
			method: http.MethodGet,
			path:   "admin/users",
			invoke: func(c *sdk.Client) error { _, err := c.AdminUserList(ctx); return err },
		},
		{
			name:   "AdminUserDelete",
			method: http.MethodDelete,
			path:   "admin/user/u1",
			invoke: func(c *sdk.Client) error { return c.AdminUserDelete(ctx, "u1") },
		},
		{
			name:   "AdminDesktopList",
			method: http.MethodGet,
			path:   "admin/domains",
			// rawQuery separately verified because URL.Path strips query
			rawQuery: "kind=desktop",
			invoke:   func(c *sdk.Client) error { _, err := c.AdminDesktopList(ctx); return err },
		},
		{
			name:     "AdminTemplateList",
			method:   http.MethodGet,
			path:     "admin/domains",
			rawQuery: "kind=template",
			invoke:   func(c *sdk.Client) error { _, err := c.AdminTemplateList(ctx); return err },
		},
		// --- user (token_router) -------------------------------------
		{
			name:   "UserVPN",
			method: http.MethodGet,
			path:   "item/user/vpn/config",
			invoke: func(c *sdk.Client) error { _, err := c.UserVPN(ctx); return err },
		},
		// --- top-level -----------------------------------------------
		{
			name:   "Maintenance",
			method: http.MethodGet,
			path:   "maintenance",
			invoke: func(c *sdk.Client) error { _, err := c.Maintenance(ctx); return err },
		},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			cap, srv := newCaptureServer(t)
			cli := newClient(t, srv)
			_ = tc.invoke(cli) // ignore SDK decode errors; we only care about the request it sent
			assert.Equal(t, tc.method, cap.method, "HTTP method mismatch")
			assert.Equal(t, tc.path, cap.path, "URL path mismatch")
			if tc.rawQuery != "" {
				assert.Equal(t, tc.rawQuery, cap.rawPath, "query string mismatch")
			}
			if tc.assertBody != nil {
				tc.assertBody(t, cap.body)
			}
		})
	}
}

// --- specific gap + security pins ----------------------------------------

// TestDesktopUpdateForcedHyp pins the wire contract: pkg/sdk DesktopUpdate
// sends a `forced_hyp` body to `PUT item/desktop/{id}/edit`, and the v4
// DesktopEditRequest schema accepts the field for admin/manager callers
// (component/_common/isardvdi_common/lib/domains/desktops/desktops.py
// applies it only when admin_or_manager is true).
func TestDesktopUpdateForcedHyp(t *testing.T) {
	cap, srv := newCaptureServer(t)
	cli := newClient(t, srv)

	_ = cli.DesktopUpdate(context.Background(), "desk-1", sdk.DesktopUpdateOptions{
		ForcedHyp: []string{"h1", "h2"},
	})

	assert.Equal(t, http.MethodPut, cap.method)
	assert.Equal(t, "item/desktop/desk-1/edit", cap.path)

	var body map[string]interface{}
	require.NoError(t, json.Unmarshal([]byte(cap.body), &body))
	fh, ok := body["forced_hyp"].([]interface{})
	require.True(t, ok, "DesktopUpdate must send forced_hyp array")
	assert.Equal(t, []interface{}{"h1", "h2"}, fh)
}

// TestAllSDKPathsAreV4Shaped is a coarse safety net: grep the captured
// URL for any v3-shaped pattern (e.g. leading /api/v3, `desktop/start/`
// verb-first form, raw `desktops/from/` scratch path). This catches a
// future hand-rolled SDK method that slips past the per-method table.
func TestAllSDKPathsAreV4Shaped(t *testing.T) {
	// Invoke a cross-section of methods and ensure each request's URL
	// starts with /api/v4/ (added by the Client) and never contains
	// legacy verb-first segments.
	victims := []struct {
		name   string
		invoke func(c *sdk.Client) error
	}{
		{"DesktopList", func(c *sdk.Client) error { _, err := c.DesktopList(context.Background()); return err }},
		{"DesktopStart", func(c *sdk.Client) error { return c.DesktopStart(context.Background(), "d1") }},
		{"DesktopStop", func(c *sdk.Client) error { return c.DesktopStop(context.Background(), "d1") }},
		{"TemplateList", func(c *sdk.Client) error { _, err := c.TemplateList(context.Background()); return err }},
	}

	forbidden := []string{
		"/api/v3/",
		"desktop/start/", // legacy verb-first
		"desktop/stop/",
		"desktop/from/scratch",
		"user/owns_desktop", // underscore verb — should be hyphenated
	}

	for _, v := range victims {
		v := v
		t.Run(v.name, func(t *testing.T) {
			var captured string
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				captured = r.URL.Path
				w.Header().Set("Content-Type", "application/json")
				_, _ = w.Write([]byte("null"))
			}))
			defer srv.Close()
			cli := newClient(t, srv)
			_ = v.invoke(cli)
			require.True(t, strings.HasPrefix(captured, "/api/v4/"),
				"path must live under /api/v4/, got %q", captured)
			for _, bad := range forbidden {
				assert.NotContains(t, captured, bad,
					fmt.Sprintf("path %q contains legacy/forbidden segment %q", captured, bad))
			}
		})
	}
}
