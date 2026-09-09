package http

import (
	"context"
	"net"
	"sync"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/bastion/model"
	"gitlab.com/isard/isardvdi/pkg/db"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/stretchr/testify/require"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestBastionHandleProxy(t *testing.T) {
	t.Parallel()

	cases := map[string]struct {
		Enabled   bool
		PrepareDB func(*r.Mock)
		Target    string
	}{
		"should refuse the connection if the bastion is disabled": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("targets").Get("target-bastion-disabled")).Once().Return([]any{
					map[string]any{
						"id":      "target-bastion-disabled",
						"user_id": "user-bastion-disabled",
						"http": map[string]any{
							"enabled": true,
						},
					},
				}, nil)
			},
			Target: "target-bastion-disabled",
		},
		"should keep serving if the bastion is enabled, so the guard is not just always false": {
			Enabled: true,
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("targets").Get("target-bastion-enabled")).Once().Return([]any{
					map[string]any{
						"id":      "target-bastion-enabled",
						"user_id": "user-bastion-enabled",
						"http": map[string]any{
							"enabled": true,
						},
					},
				}, nil)

				m.On(r.Table("users").Get("user-bastion-enabled")).Once().Return([]any{}, nil)
			},
			Target: "target-bastion-enabled",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			mock := r.NewMock()
			tc.PrepareDB(mock)

			logger := log.New("test", "debug")

			var wg sync.WaitGroup

			cfgWatcher := db.NewWatcher(logger, time.Hour, 0, func(context.Context) (model.Config, error) {
				return model.Config{
					Bastion: model.Bastion{Enabled: tc.Enabled},
				}, nil
			})
			require.NoError(t, cfgWatcher.Start(t.Context(), &wg))

			b := &bastion{
				log:        logger,
				db:         mock,
				cfgWatcher: cfgWatcher,
			}

			conn, _ := net.Pipe()

			b.handleProxy(t.Context(), conn, nil, false, tc.Target, "bastion.example.org", "", 0)

			mock.AssertExpectations(t)
		})
	}
}
