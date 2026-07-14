package http

import (
	"context"
	"net/url"
	"strings"

	oasAuthentication "gitlab.com/isard/isardvdi/pkg/gen/oas/authentication"
)

type tokenCtxKeyType string

const tokenCtxKey tokenCtxKeyType = "token"

// safeRedirect validates a user-controlled post-login redirect target to
// prevent open-redirect attacks (e.g. ?redirect=https://evil.example). It only
// permits same-origin local paths: a value starting with a single "/" that is
// not protocol-relative ("//host") nor a backslash trick ("/\host", which some
// browsers normalise to protocol-relative), and that parses without a scheme or
// host. An empty input is returned unchanged so callers keep their
// "no redirect requested" semantics; any other unsafe value is replaced with
// the safe default "/".
func safeRedirect(location string) string {
	if location == "" {
		return ""
	}
	if location[0] != '/' || (len(location) > 1 && (location[1] == '/' || location[1] == '\\')) {
		return "/"
	}
	u, err := url.Parse(location)
	if err != nil || u.Scheme != "" || u.Host != "" {
		return "/"
	}
	// Also reject the percent-encoded variants: after decoding, the path must
	// not be protocol-relative ("//host") nor contain a backslash, both of
	// which a browser can normalise toward an external origin.
	if strings.HasPrefix(u.Path, "//") || strings.Contains(u.Path, "\\") {
		return "/"
	}
	return location
}

type SecurityHandler struct{}

func (SecurityHandler) HandleBearerAuth(ctx context.Context, operationName string, t oasAuthentication.BearerAuth) (context.Context, error) {
	return context.WithValue(ctx, tokenCtxKey, t.Token), nil
}
