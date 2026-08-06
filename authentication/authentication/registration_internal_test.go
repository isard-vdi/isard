package authentication

import (
	"fmt"
	"testing"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/token"
	apiv4 "gitlab.com/isard/isardvdi/pkg/gen/oas/apiv4"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestRegisterUser(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareAPI func(*apiv4.MockInvoker)
		User       *model.User

		ExpectedID  string
		ExpectedErr string
	}{
		"should work as expected": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminAutoRegister", mock.AnythingOfType("*context.cancelCtx"), mock.MatchedBy(func(req *apiv4.AutoRegisterRequest) bool {
					return req.RoleID == "user" && req.GroupID == "group-id" &&
						req.SecondaryGroups.Set && len(req.SecondaryGroups.Value) == 1 &&
						req.SecondaryGroups.Value[0] == "secondary-id"
				}), mock.MatchedBy(func(params apiv4.AdminAutoRegisterParams) bool {
					claims, err := token.ParseRegisterToken("", params.RegisterClaims)
					return err == nil && claims.UserID == "nefix-uid"
				})).Return(&apiv4.AutoRegisterResponse{ID: "registered-id"}, nil)
			},
			User: &model.User{
				Provider: "ldap",
				Category: "default",
				UID:      "nefix-uid",
				Username: "nefix",

				Role:            model.RoleUser,
				Group:           "group-id",
				SecondaryGroups: []string{"secondary-id"},
			},

			ExpectedID: "registered-id",
		},
		"should not send the secondary groups when the user has none": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminAutoRegister", mock.AnythingOfType("*context.cancelCtx"), mock.MatchedBy(func(req *apiv4.AutoRegisterRequest) bool {
					return req.RoleID == "user" && req.GroupID == "group-id" && !req.SecondaryGroups.Set
				}), mock.AnythingOfType("apiv4.AdminAutoRegisterParams")).Return(&apiv4.AutoRegisterResponse{ID: "registered-id"}, nil)
			},
			User: &model.User{
				Provider: "ldap",
				Category: "default",
				UID:      "nefix-uid",
				Username: "nefix",

				Role:  model.RoleUser,
				Group: "group-id",
			},

			ExpectedID: "registered-id",
		},
		"should return an error if the API call fails": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminAutoRegister", mock.AnythingOfType("*context.cancelCtx"), mock.MatchedBy(func(req *apiv4.AutoRegisterRequest) bool {
					return req.RoleID == "user" && req.GroupID == "group-id"
				}), mock.AnythingOfType("apiv4.AdminAutoRegisterParams")).Return(nil, fmt.Errorf("register error"))
			},
			User: &model.User{
				Provider: "ldap",
				Category: "default",
				UID:      "nefix-uid",
				Username: "nefix",

				Role:  model.RoleUser,
				Group: "group-id",
			},

			ExpectedErr: "register the user: register error",
		},
		"should return an error if the API returns an unexpected response": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminAutoRegister", mock.AnythingOfType("*context.cancelCtx"), mock.MatchedBy(func(req *apiv4.AutoRegisterRequest) bool {
					return req.RoleID == "user" && req.GroupID == "group-id"
				}), mock.AnythingOfType("apiv4.AdminAutoRegisterParams")).Return(&apiv4.AdminAutoRegisterConflict{
					Error:       "conflict",
					Description: "user already exists",
				}, nil)
			},
			User: &model.User{
				Provider: "ldap",
				Category: "default",
				UID:      "nefix-uid",
				Username: "nefix",

				Role:  model.RoleUser,
				Group: "group-id",
			},

			ExpectedErr: "register the user: ogen 409 conflict: user already exists []",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			apiMock := apiv4.NewMockInvoker(t)
			tc.PrepareAPI(apiMock)

			a := &Authentication{
				Log:    log.New("authentication-test", "debug"),
				Secret: "",
				API:    apiMock,
			}

			err := a.registerUser(t.Context(), tc.User)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
				assert.Equal(tc.ExpectedID, tc.User.ID)
				assert.True(tc.User.Active)
			}

			apiMock.AssertExpectations(t)
		})
	}
}

func TestRegisterGroup(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareAPI func(*apiv4.MockInvoker)

		ExpectedID  string
		ExpectedUID string
		ExpectedErr string
	}{
		"should work as expected": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCreateGroup", mock.AnythingOfType("*context.cancelCtx"), mock.MatchedBy(func(req *apiv4.AdminGroupCreateData) bool {
					return req.UID.Value == "primary group" && req.Name == "primary group" &&
						req.Description.Value == "some description" && req.ParentCategory.Value == "default" &&
						req.ExternalAppID.Value == "provider-test" && req.ExternalGid.Value == "primary-group"
				})).Return(&apiv4.AdminGroup{
					ID:  "created-id",
					UID: "created-uid",
				}, nil)
			},

			ExpectedID:  "created-id",
			ExpectedUID: "created-uid",
		},
		"should return an error if the API call fails": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCreateGroup", mock.AnythingOfType("*context.cancelCtx"), mock.MatchedBy(func(req *apiv4.AdminGroupCreateData) bool {
					return req.Name == "primary group" && req.ExternalGid.Value == "primary-group"
				})).Return(nil, fmt.Errorf("create error"))
			},

			ExpectedErr: "register the group: create error",
		},
		"should return an error if the API returns an unexpected response": {
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCreateGroup", mock.AnythingOfType("*context.cancelCtx"), mock.MatchedBy(func(req *apiv4.AdminGroupCreateData) bool {
					return req.Name == "primary group" && req.ExternalGid.Value == "primary-group"
				})).Return(&apiv4.AdminCreateGroupConflict{
					Error:       "conflict",
					Description: "group already exists",
				}, nil)
			},

			ExpectedErr: "register the group: ogen 409 conflict: group already exists []",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			apiMock := apiv4.NewMockInvoker(t)
			tc.PrepareAPI(apiMock)

			a := &Authentication{
				Log: log.New("authentication-test", "debug"),
				API: apiMock,
			}

			g := &model.Group{
				Category:      "default",
				ExternalAppID: "provider-test",
				ExternalGID:   "primary-group",
				Name:          "primary group",
				Description:   "some description",
			}

			err := a.registerGroup(t.Context(), g)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
				assert.Equal(tc.ExpectedID, g.ID)
				assert.Equal(tc.ExpectedUID, g.UID)
			}

			apiMock.AssertExpectations(t)
		})
	}
}

func TestRegisterGroups(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB  func(*r.Mock)
		PrepareAPI func(*apiv4.MockInvoker)

		ExpectedPrimaryID   string
		ExpectedSecondaryID string
		ExpectedErr         string
	}{
		"should work as expected": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-test"),
					r.Eq(r.Row.Field("external_gid"), "secondary-group"),
				))).Return([]any{
					map[string]any{
						"id": "secondary-id",
					},
				}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-test"),
					r.Eq(r.Row.Field("external_gid"), "primary-group"),
				))).Return([]any{
					map[string]any{
						"id": "primary-id",
					},
				}, nil)
			},

			ExpectedPrimaryID:   "primary-id",
			ExpectedSecondaryID: "secondary-id",
		},
		"should register the groups that do not exist yet": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-test"),
					r.Eq(r.Row.Field("external_gid"), "secondary-group"),
				))).Return([]any{
					map[string]any{
						"id": "secondary-id",
					},
				}, nil)

				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-test"),
					r.Eq(r.Row.Field("external_gid"), "primary-group"),
				))).Return([]any{}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCreateGroup", mock.AnythingOfType("*context.cancelCtx"), mock.MatchedBy(func(req *apiv4.AdminGroupCreateData) bool {
					return req.Name == "primary group" && req.ExternalGid.Value == "primary-group"
				})).Return(&apiv4.AdminGroup{
					ID:  "created-id",
					UID: "created-id",
				}, nil)
			},

			ExpectedPrimaryID:   "created-id",
			ExpectedSecondaryID: "secondary-id",
		},
		"should return an error if checking if a group exists fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-test"),
					r.Eq(r.Row.Field("external_gid"), "secondary-group"),
				))).Return(nil, fmt.Errorf("group error"))
			},

			ExpectedErr: "check if group exists: group error",
		},
		"should return an error if registering a group fails": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("groups").GetAllByIndex("parent_category", "default").Filter(r.And(
					r.Eq(r.Row.Field("external_app_id"), "provider-test"),
					r.Eq(r.Row.Field("external_gid"), "secondary-group"),
				))).Return([]any{}, nil)
			},
			PrepareAPI: func(c *apiv4.MockInvoker) {
				c.On("AdminCreateGroup", mock.AnythingOfType("*context.cancelCtx"), mock.MatchedBy(func(req *apiv4.AdminGroupCreateData) bool {
					return req.Name == "secondary group" && req.ExternalGid.Value == "secondary-group"
				})).Return(nil, fmt.Errorf("create error"))
			},

			ExpectedErr: "auto register group: register the group: create error",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			dbMock := r.NewMock()
			tc.PrepareDB(dbMock)

			apiMock := apiv4.NewMockInvoker(t)
			if tc.PrepareAPI != nil {
				tc.PrepareAPI(apiMock)
			}

			a := &Authentication{
				Log: log.New("authentication-test", "debug"),
				DB:  dbMock,
				API: apiMock,
			}

			g := &model.Group{
				Category:      "default",
				ExternalAppID: "provider-test",
				ExternalGID:   "primary-group",
				Name:          "primary group",
			}
			secondary := []*model.Group{{
				Category:      "default",
				ExternalAppID: "provider-test",
				ExternalGID:   "secondary-group",
				Name:          "secondary group",
			}}

			err := a.registerGroups(t.Context(), g, secondary)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
				assert.Equal(tc.ExpectedPrimaryID, g.ID)
				assert.Equal(tc.ExpectedSecondaryID, secondary[0].ID)
			}

			dbMock.AssertExpectations(t)
			apiMock.AssertExpectations(t)
		})
	}
}
