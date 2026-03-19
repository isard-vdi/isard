package authentication

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestValidateRedirect(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Input    string
		Expected string
	}{
		"should return empty for empty string": {
			Input:    "",
			Expected: "",
		},
		"should allow simple relative path": {
			Input:    "/dashboard",
			Expected: "/dashboard",
		},
		"should allow root path": {
			Input:    "/",
			Expected: "/",
		},
		"should allow relative path with query": {
			Input:    "/desktops?id=123",
			Expected: "/desktops?id=123",
		},
		"should allow relative path with fragment": {
			Input:    "/page#section",
			Expected: "/page#section",
		},
		"should allow nested relative path": {
			Input:    "/admin/users/edit",
			Expected: "/admin/users/edit",
		},
		"should allow path without leading slash": {
			Input:    "relative",
			Expected: "relative",
		},
		"should allow notifications login path": {
			Input:    "/notifications/login",
			Expected: "/notifications/login",
		},
		"should allow query-only redirect": {
			Input:    "?next=/dashboard",
			Expected: "?next=/dashboard",
		},
		"should allow fragment-only redirect": {
			Input:    "#section",
			Expected: "#section",
		},
		"should url-encode backslashes and treat as safe path": {
			Input:    "\\\\evil.com",
			Expected: "%5C%5Cevil.com",
		},
		"should block absolute URL with http scheme": {
			Input:    "http://evil.com/steal",
			Expected: "/",
		},
		"should block absolute URL with https scheme": {
			Input:    "https://evil.com/steal",
			Expected: "/",
		},
		"should block protocol-relative URL": {
			Input:    "//evil.com/steal",
			Expected: "/",
		},
		"should block protocol-relative URL without path": {
			Input:    "//attacker.com",
			Expected: "/",
		},
		"should block javascript scheme": {
			Input:    "javascript:alert(1)",
			Expected: "/",
		},
		"should block data scheme": {
			Input:    "data:text/html,<script>alert(1)</script>",
			Expected: "/",
		},
		"should block ftp scheme": {
			Input:    "ftp://evil.com/file",
			Expected: "/",
		},
		"should block http URL with credentials": {
			Input:    "http://user:pass@evil.com/path",
			Expected: "/",
		},
		"should allow triple-slash path as relative": {
			Input:    "///evil.com",
			Expected: "///evil.com",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			assert.Equal(tc.Expected, validateRedirect(tc.Input))
		})
	}
}
