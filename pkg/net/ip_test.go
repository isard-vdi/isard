package net_test

import (
	"net"
	"testing"

	pkgNet "gitlab.com/isard/isardvdi/pkg/net"

	"github.com/stretchr/testify/assert"
)

func TestIsLocalIP(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		IP       net.IP
		Expected bool
	}{
		"should return true for a loopback IPv4 address": {
			IP:       net.ParseIP("127.0.0.1"),
			Expected: true,
		},
		"should return true for a loopback IPv6 address": {
			IP:       net.ParseIP("::1"),
			Expected: true,
		},
		"should return true for the unspecified IPv4 address": {
			IP:       net.ParseIP("0.0.0.0"),
			Expected: true,
		},
		"should return true for the unspecified IPv6 address": {
			IP:       net.ParseIP("::"),
			Expected: true,
		},
		"should return true for a link-local unicast IPv4 address": {
			IP:       net.ParseIP("169.254.1.1"),
			Expected: true,
		},
		"should return true for a link-local unicast IPv6 address": {
			IP:       net.ParseIP("fe80::1"),
			Expected: true,
		},
		"should return true for a link-local multicast IPv4 address": {
			IP:       net.ParseIP("224.0.0.1"),
			Expected: true,
		},
		"should return true for a link-local multicast IPv6 address": {
			IP:       net.ParseIP("ff02::1"),
			Expected: true,
		},
		"should return false for a public IPv4 address": {
			// 203.0.113.1 is in TEST-NET-3 (RFC 5737), reserved for documentation.
			IP:       net.ParseIP("203.0.113.1"),
			Expected: false,
		},
		"should return false for a public IPv6 address": {
			// 2001:db8::/32 is reserved for documentation (RFC 3849).
			IP:       net.ParseIP("2001:db8::1"),
			Expected: false,
		},
		"should return false for a private IPv4 address that is not this server": {
			IP:       net.ParseIP("10.255.255.254"),
			Expected: false,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			local := pkgNet.IsLocalIP(tc.IP)

			assert.Equal(tc.Expected, local)
		})
	}
}
