package main

import (
	"testing"

	"github.com/stretchr/testify/assert"
)

func TestFlavourPredicates(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	cases := map[string]struct {
		Flavour            string
		ExpectedWeb        bool
		ExpectedHypervisor bool
	}{
		"should detect both web and hypervisor in all-in-one": {
			Flavour:            "all-in-one",
			ExpectedWeb:        true,
			ExpectedHypervisor: true,
		},
		"should detect only hypervisor in hypervisor": {
			Flavour:            "hypervisor",
			ExpectedHypervisor: true,
		},
		"should detect only hypervisor in hypervisor-standalone": {
			Flavour:            "hypervisor-standalone",
			ExpectedHypervisor: true,
		},
		"should detect only web in web": {
			Flavour:     "web",
			ExpectedWeb: true,
		},
		"should detect only web in web+monitor": {
			Flavour:     "web+monitor",
			ExpectedWeb: true,
		},
		"should detect only web in web+storage": {
			Flavour:     "web+storage",
			ExpectedWeb: true,
		},
		"should detect only web in web+storage+video": {
			Flavour:     "web+storage+video",
			ExpectedWeb: true,
		},
		"should detect only web in web+storage+monitor": {
			Flavour:     "web+storage+monitor",
			ExpectedWeb: true,
		},
		"should detect only web in web+storage+video+monitor": {
			Flavour:     "web+storage+video+monitor",
			ExpectedWeb: true,
		},
		"should detect neither in storage": {
			Flavour: "storage",
		},
		"should detect neither in monitor": {
			Flavour: "monitor",
		},
		"should detect neither in video-standalone": {
			Flavour: "video-standalone",
		},
		"should detect neither in backupninja": {
			Flavour: "backupninja",
		},
		"should detect neither in check": {
			Flavour: "check",
		},
		"should detect neither in haproxy": {
			Flavour: "haproxy",
		},
		"should detect neither in an empty flavour": {
			Flavour: "",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			assert.Equal(tc.ExpectedWeb, hasWeb(tc.Flavour))
			assert.Equal(tc.ExpectedHypervisor, hasHypervisor(tc.Flavour))
		})
	}
}
