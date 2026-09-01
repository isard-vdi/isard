package haproxysync

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestIsBaseDomain(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		BaseDomain string
		Domain     string
		Expected   bool
	}{
		"should match the deployment's own domain": {
			BaseDomain: "portal.example.com",
			Domain:     "portal.example.com",
			Expected:   true,
		},
		"should match whatever the case, as dns names are case insensitive": {
			BaseDomain: "portal.example.com",
			Domain:     "PORTAL.Example.COM",
			Expected:   true,
		},
		"should not match a different domain": {
			BaseDomain: "portal.example.com",
			Domain:     "aula.example.com",
			Expected:   false,
		},
		"should not match anything if the deployment has no domain": {
			BaseDomain: "",
			Domain:     "portal.example.com",
			Expected:   false,
		},
		"should not match an empty domain against an empty base domain": {
			BaseDomain: "",
			Domain:     "",
			Expected:   false,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			h := &HAproxySync{
				Domains: &HAProxySyncDomains{
					BaseDomain: tc.BaseDomain,
				},
			}

			assert.Equal(tc.Expected, h.isBaseDomain(tc.Domain))
		})
	}
}
