package haproxysync_test

import (
	"context"
	"errors"
	"testing"

	"gitlab.com/isard/isardvdi/haproxy-sync/cfg"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy-sync"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/stretchr/testify/assert"
)

func TestCheck(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareHAProxy func(*haproxy.MockHaproxy)
		ExpectedErr    string
	}{
		"should work as expected": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowVersion").Return("3.0.0", nil)
			},
		},
		"should return an error if HAProxy returns an error": {
			PrepareHAProxy: func(m *haproxy.MockHaproxy) {
				m.On("ShowVersion").Return("", errors.New("connection refused"))
			},
			ExpectedErr: "get HAProxy version: connection refused",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			haproxyMock := &haproxy.MockHaproxy{}
			tc.PrepareHAProxy(haproxyMock)

			svc := haproxysync.Init(log.New("test", "debug"), cfg.HAProxy{}, haproxyMock, nil)

			err := svc.Check(context.Background())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			haproxyMock.AssertExpectations(t)
		})
	}
}
