package model_test

import (
	"errors"
	"testing"

	"gitlab.com/isard/isardvdi/orchestrator/model"
	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/stretchr/testify/assert"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestConfigLoad(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	// RethinkDB errors on Field over an absent key, it doesn't return an empty result.
	missingKeyErr := errors.New("rethinkdb: No attribute `orchestrator` in object:\n{\n\t\"bastion\":\t{\n\t\t\"enabled\":\ttrue\n\t},\n\t\"id\":\t1\n} in:\nr.Table(\"config\").Get(1).Field(\"orchestrator\")")

	cases := map[string]struct {
		PrepareDB   func(*r.Mock)
		Expected    model.Config
		ExpectedErr string
	}{
		"should load the configuration as expected": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("orchestrator")).Return(map[string]any{
					"enabled": true,
				}, nil)
			},
			Expected: model.Config{
				Orchestrator: model.Orchestrator{Enabled: true},
			},
		},
		"should return a not found error if there is no configuration": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("orchestrator")).Return(nil, nil)
			},
			ExpectedErr: db.ErrNotFound.Error(),
		},
		"should return an error if the orchestrator key is missing": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("orchestrator")).Return(nil, missingKeyErr)
			},
			ExpectedErr: missingKeyErr.Error(),
		},
		"should return an error if there's an error loading the configuration": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("config").Get(1).Field("orchestrator")).Return(nil, errors.New("connection refused"))
			},
			ExpectedErr: "connection refused",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			dbMock := r.NewMock()
			tc.PrepareDB(dbMock)

			cfg := &model.Config{}
			err := cfg.Load(t.Context(), dbMock)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
				assert.Equal(tc.Expected, *cfg)
			}

			dbMock.AssertExpectations(t)
		})
	}
}
