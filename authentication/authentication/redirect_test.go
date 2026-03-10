package authentication

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestValidateRedirect(t *testing.T) {
	cases := map[string]struct {
		Input    string
		Expected string
	}{
		"empty string returns empty": {
			Input:    "",
			Expected: "",
		},
		"simple relative path": {
			Input:    "/dashboard",
			Expected: "/dashboard",
		},
		"root path": {
			Input:    "/",
			Expected: "/",
		},
		"relative path with query": {
			Input:    "/desktops?id=123",
			Expected: "/desktops?id=123",
		},
		"relative path with fragment": {
			Input:    "/page#section",
			Expected: "/page#section",
		},
		"nested relative path": {
			Input:    "/admin/users/edit",
			Expected: "/admin/users/edit",
		},
		"absolute URL with http scheme is blocked": {
			Input:    "http://evil.com/steal",
			Expected: "/",
		},
		"absolute URL with https scheme is blocked": {
			Input:    "https://evil.com/steal",
			Expected: "/",
		},
		"protocol-relative URL is blocked": {
			Input:    "//evil.com/steal",
			Expected: "/",
		},
		"javascript scheme is blocked": {
			Input:    "javascript:alert(1)",
			Expected: "/",
		},
		"data scheme is blocked": {
			Input:    "data:text/html,<script>alert(1)</script>",
			Expected: "/",
		},
		"ftp scheme is blocked": {
			Input:    "ftp://evil.com/file",
			Expected: "/",
		},
		"absolute URL with host but no scheme is blocked": {
			Input:    "//attacker.com",
			Expected: "/",
		},
		"backslash is URL-encoded and safe": {
			Input:    "\\\\evil.com",
			Expected: "%5C%5Cevil.com",
		},
		"notifications login path": {
			Input:    "/notifications/login",
			Expected: "/notifications/login",
		},
		"path without leading slash": {
			Input:    "relative",
			Expected: "relative",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			assert.Equal(t, tc.Expected, ValidateRedirect(tc.Input))
		})
	}
}
