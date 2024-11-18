package model_test

import (
	"context"
	"strings"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/bastion/model"

	"github.com/stretchr/testify/assert"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestTargetLoad(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareTest    func(*r.Mock)
		Target         *model.Target
		ExpectedTarget *model.Target
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareTest: func(m *r.Mock) {
				m.On(r.Table("targets").Get("my awesome target")).Once().Return([]interface{}{
					map[string]interface{}{
						"id":         "my awesome target",
						"user_id":    "néfix",
						"desktop_id": "my awesome desktop",
						"http": map[string]interface{}{
							"enabled":    true,
							"http_port":  80,
							"https_port": 443,
						},
						"ssh": map[string]interface{}{
							"enabled":         true,
							"port":            22,
							"authorized_keys": []string{"my SSH key"},
						},
					},
				}, nil)

				// This is run after cache eviction
				m.On(r.Table("targets").Get("my awesome target")).Once().Return([]interface{}{
					map[string]interface{}{
						"id":         "my awesome target",
						"user_id":    "néfix",
						"desktop_id": "my awesome desktop",
						"http": map[string]interface{}{
							"enabled":    true,
							"http_port":  80,
							"https_port": 443,
						},
						"ssh": map[string]interface{}{
							"enabled":         true,
							"port":            22,
							"authorized_keys": []string{"my SSH key"},
						},
					},
				}, nil)
			},
			Target: &model.Target{
				ID: "my awesome target",
			},
			ExpectedTarget: &model.Target{
				ID:        "my awesome target",
				UserID:    "néfix",
				DesktopID: "my awesome desktop",
				HTTP: model.TargetHTTP{
					Enabled:   true,
					HTTPPort:  80,
					HTTPSPort: 443,
				},
				SSH: model.TargetSSH{
					Enabled:        true,
					Port:           22,
					AuthorizedKeys: []string{"my SSH key"},
				},
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			mock := r.NewMock()

			tc.PrepareTest(mock)

			_ = tc.Target.Load(context.Background(), mock)
			// Load again to ensure the result is cached
			_ = tc.Target.Load(context.Background(), mock)
			// Wait 11 seconds to ensure the cache is evicted
			time.Sleep(11 * time.Second)
			err := tc.Target.Load(context.Background(), mock)

			if tc.ExpectedErr != "" {
				assert.True(strings.HasPrefix(err.Error(), tc.ExpectedErr))
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedTarget, tc.Target)

			mock.AssertExpectations(t)
		})
	}
}
