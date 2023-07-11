package model_test

import (
	"context"
	"errors"
	"testing"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/stretchr/testify/assert"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestUserLoad(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareTest  func(*r.Mock)
		User         *model.User
		ExpectedUser *model.User
		ExpectedErr  string
	}{
		"should work as expected": {
			PrepareTest: func(m *r.Mock) {
				m.On(r.Table("users").Get("local-default-admin-admin")).Return([]interface{}{
					map[string]interface{}{
						"id":       "local-default-admin-admin",
						"uid":      "admin",
						"username": "admin",
						"password": "f0ckt3Rf$",
						"provider": "local",
						"category": "default",
						"role":     "default",
						"group":    "default",
						"name":     "Administrator",
						"email":    "admin@isardvdi.com",
						"photo":    "https://isardvdi.com/path/to/photo.jpg",
					},
				}, nil)
			},
			User: &model.User{
				ID: "local-default-admin-admin",
			},
			ExpectedUser: &model.User{
				ID:       "local-default-admin-admin",
				UID:      "admin",
				Username: "admin",
				Password: "f0ckt3Rf$",
				Provider: "local",
				Category: "default",
				Role:     "default",
				Group:    "default",
				Name:     "Administrator",
				Email:    "admin@isardvdi.com",
				Photo:    "https://isardvdi.com/path/to/foto.jpg",
			},
		},
		"should return an error if there's an error querying the DB": {
			PrepareTest: func(m *r.Mock) {
				m.On(r.Table("users").Get("")).Return(nil, errors.New(":)"))
			},
			User: &model.User{
				Provider: "local",
				Category: "default",
				UID:      "admin",
				Username: "admin",
			},
			ExpectedErr: ":)",
		},
		"should return not found if the user is not found": {
			PrepareTest: func(m *r.Mock) {
				m.On(r.Table("users").Get("local-default-fakeuser-fakeuser")).Return([]interface{}{}, nil)
			},
			User: &model.User{
				ID: "local-default-fakeuser-fakeuser",
			},
			ExpectedUser: &model.User{},
			ExpectedErr:  db.ErrNotFound.Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			mock := r.NewMock()

			tc.PrepareTest(mock)

			err := tc.User.Load(context.Background(), mock)

			if tc.ExpectedErr == "" {
				assert.NoError(err)
			} else {
				assert.EqualError(err, tc.ExpectedErr)
			}

			mock.AssertExpectations(t)
		})
	}
}
