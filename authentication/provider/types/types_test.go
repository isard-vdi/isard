package types_test

import (
	"testing"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"

	"github.com/stretchr/testify/assert"
)

func TestProviderUserDataFromUser(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		User         *model.User
		ExpectedUser types.ProviderUserData
	}{
		"should populate all fields correctly": {
			User: &model.User{
				Provider: "local",
				Category: "default",
				UID:      "pau",
				Role:     "admin",
				Group:    "default-default",
				Username: "pau",
				Name:     "Pau Abril",
				Email:    "pau@example.org",
				Photo:    "https://example.org/photo.jpg",
			},
			ExpectedUser: types.ProviderUserData{
				Provider: "local",
				Category: "default",
				UID:      "pau",
				Role:     rolePointer(model.RoleAdmin),
				Group:    stringPointer("default-default"),
				Username: stringPointer("pau"),
				Name:     stringPointer("Pau Abril"),
				Email:    stringPointer("pau@example.org"),
				Photo:    stringPointer("https://example.org/photo.jpg"),
			},
		},
		"should use zero values if only some fileds are populated": {
			User: &model.User{
				Provider: "ldap",
				Category: "default",
				UID:      "pau",
				Role:     "user",
				Group:    "",
				Username: "pau",
				Name:     "",
				Email:    "pau@example.org",
				Photo:    "",
			},
			ExpectedUser: types.ProviderUserData{
				Provider: "ldap",
				Category: "default",
				UID:      "pau",
				Role:     rolePointer(model.RoleUser),
				Username: stringPointer("pau"),
				Email:    stringPointer("pau@example.org"),
			},
		},
		"should use zero values if all fields are empty": {
			User: &model.User{},
			ExpectedUser: types.ProviderUserData{
				Role:  nil,
				Group: nil,
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			var u types.ProviderUserData
			u.FromUser(tc.User)

			assert.Equal(tc.ExpectedUser, u)
		})
	}
}

func TestProviderUserDataToUser(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		User         types.ProviderUserData
		ExpectedUser *model.User
	}{
		"should transform all fields correctly": {
			User: types.ProviderUserData{
				Provider: "local",
				Category: "default",
				UID:      "pau",
				Role:     rolePointer(model.RoleAdmin),
				Group:    stringPointer("default-default"),
				Username: stringPointer("pau"),
				Name:     stringPointer("Pau Abril"),
				Email:    stringPointer("pau@example.org"),
				Photo:    stringPointer("https://example.org/photo.jpg"),
			},
			ExpectedUser: &model.User{
				Provider: "local",
				Category: "default",
				UID:      "pau",
				Role:     "admin",
				Group:    "default-default",
				Username: "pau",
				Name:     "Pau Abril",
				Email:    "pau@example.org",
				Photo:    "https://example.org/photo.jpg",
			},
		},
		"should use zero values if only some fileds are populated": {
			User: types.ProviderUserData{
				Provider: "ldap",
				Category: "default",
				UID:      "pau",
				Role:     rolePointer(model.RoleUser),
				Username: stringPointer("pau"),
				Email:    stringPointer("pau@example.org"),
			},
			ExpectedUser: &model.User{
				Provider: "ldap",
				Category: "default",
				UID:      "pau",
				Role:     "user",
				Username: "pau",
				Email:    "pau@example.org",
			},
		},
		"should use zero values if all fields are empty": {
			User: types.ProviderUserData{},
			ExpectedUser: &model.User{
				Provider: "",
				Category: "",
				UID:      "",
				Role:     "",
				Group:    "",
				Username: "",
				Name:     "",
				Email:    "",
				Photo:    "",
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			u := tc.User.ToUser()

			assert.Equal(tc.ExpectedUser, u)
		})
	}
}

func stringPointer(s string) *string {
	return &s
}

func rolePointer(r model.Role) *model.Role {
	return &r
}
