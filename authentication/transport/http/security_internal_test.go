package http

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestSafeRedirect(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Location string
		Expected string
	}{
		"should keep an empty redirect empty": {
			Location: "",
			Expected: "",
		},
		"should allow a rooted local path": {
			Location: "/frontend/desktops",
			Expected: "/frontend/desktops",
		},
		"should allow the notifications login path": {
			Location: "/notifications/login",
			Expected: "/notifications/login",
		},
		"should allow a rooted path with a query string": {
			Location: "/login?error=disabled",
			Expected: "/login?error=disabled",
		},
		"should reject an absolute http URL": {
			Location: "https://evil.example/phish",
			Expected: "/",
		},
		"should reject a protocol-relative URL": {
			Location: "//evil.example/phish",
			Expected: "/",
		},
		"should reject a backslash protocol-relative trick": {
			Location: "/\\evil.example/phish",
			Expected: "/",
		},
		"should reject a percent-encoded backslash trick": {
			Location: "/%5Cevil.example/phish",
			Expected: "/",
		},
		"should reject a percent-encoded protocol-relative trick": {
			Location: "/%2F%2Fevil.example/phish",
			Expected: "/",
		},
		"should reject a javascript scheme": {
			Location: "javascript:alert(1)",
			Expected: "/",
		},
		"should reject a non-rooted relative path": {
			Location: "evil.example",
			Expected: "/",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			assert.Equal(tc.Expected, safeRedirect(tc.Location))
		})
	}
}
