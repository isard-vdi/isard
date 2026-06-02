package db

import (
	"errors"
	"testing"

	"github.com/stretchr/testify/assert"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestPing(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB   func(*r.Mock)
		ExpectedErr string
	}{
		"should return nil when the DB responds": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Expr(1)).Return(1, nil)
			},
		},
		"should return an error when Run fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Expr(1)).Return(nil, errors.New("connection refused"))
			},
			ExpectedErr: "ping the DB: connection refused",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			mock := r.NewMock()
			tc.PrepareDB(mock)

			err := Ping(t.Context(), mock)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			mock.AssertExpectations(t)
		})
	}
}
