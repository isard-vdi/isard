package model_test

import (
	"errors"
	"testing"

	"gitlab.com/isard/isardvdi/bastion/model"
	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/stretchr/testify/assert"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestDeploymentLoad(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareTest        func(*r.Mock)
		Deployment         *model.Deployment
		ExpectedDeployment *model.Deployment
		ExpectedErr        error
	}{
		"should work as expected": {
			PrepareTest: func(m *r.Mock) {
				// Only once, since the second load is served from the cache
				m.On(r.Table("deployments").Get("my awesome deployment")).Once().Return([]any{
					map[string]any{
						"id":        "my awesome deployment",
						"user":      "néfix",
						"co_owners": []string{"melina", "pau"},
					},
				}, nil)
			},
			Deployment: &model.Deployment{
				ID: "my awesome deployment",
			},
			ExpectedDeployment: &model.Deployment{
				ID:       "my awesome deployment",
				UserID:   "néfix",
				CoOwners: []string{"melina", "pau"},
			},
		},
		"should work as expected when there are no co owners": {
			PrepareTest: func(m *r.Mock) {
				m.On(r.Table("deployments").Get("my lonely deployment")).Once().Return([]any{
					map[string]any{
						"id":   "my lonely deployment",
						"user": "néfix",
					},
				}, nil)
			},
			Deployment: &model.Deployment{
				ID: "my lonely deployment",
			},
			ExpectedDeployment: &model.Deployment{
				ID:     "my lonely deployment",
				UserID: "néfix",
			},
		},
		"should return not found if the deployment doesn't exist": {
			PrepareTest: func(m *r.Mock) {
				// Twice, since a missing deployment isn't cached
				m.On(r.Table("deployments").Get("my missing deployment")).Twice().Return([]any{}, nil)
			},
			Deployment: &model.Deployment{
				ID: "my missing deployment",
			},
			ExpectedDeployment: &model.Deployment{
				ID: "my missing deployment",
			},
			ExpectedErr: db.ErrNotFound,
		},
		"should return an error if the db fails": {
			PrepareTest: func(m *r.Mock) {
				// Twice, since a failed load isn't cached
				m.On(r.Table("deployments").Get("my broken deployment")).Twice().Return(nil, errors.New("connection refused"))
			},
			Deployment: &model.Deployment{
				ID: "my broken deployment",
			},
			ExpectedDeployment: &model.Deployment{
				ID: "my broken deployment",
			},
			ExpectedErr: &db.Err{
				Err: errors.New("connection refused"),
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			mock := r.NewMock()

			tc.PrepareTest(mock)

			_ = tc.Deployment.Load(t.Context(), mock)
			// Load again to ensure the result is cached
			err := tc.Deployment.Load(t.Context(), mock)

			if tc.ExpectedErr != nil {
				assert.ErrorIs(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedDeployment, tc.Deployment)

			mock.AssertExpectations(t)
		})
	}
}
