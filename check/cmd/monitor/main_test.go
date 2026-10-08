package main

import (
	"testing"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	checkv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/check/v1"
)

func TestHandleInstance(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		Rsp         *checkv1.CheckIsardVDIResponse
		ExpectedMsg string
	}{
		"should include the commit when the installation reports it": {
			Rsp: &checkv1.CheckIsardVDIResponse{
				IsardvdiVersion: "17.0.1 2026-09-30",
				IsardvdiCommit:  "ab2ca84017",
				HypervisorNum:   2,
			},
			ExpectedMsg: "OK (2/2) isard.example.com - 17.0.1 2026-09-30 (ab2ca84017)",
		},
		"should show only the version when the installation reports no commit": {
			Rsp: &checkv1.CheckIsardVDIResponse{
				IsardvdiVersion: "17.0.1 2026-09-30",
				HypervisorNum:   2,
			},
			ExpectedMsg: "OK (2/2) isard.example.com - 17.0.1 2026-09-30",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			log := zerolog.Nop()

			msg, failed := handleInstance(&log, &MonitorInstance{
				Host:      "isard.example.com",
				HypersNum: 2,
				Rsp:       tc.Rsp,
			})

			assert.Equal(tc.ExpectedMsg, msg)
			assert.False(failed)
		})
	}
}
