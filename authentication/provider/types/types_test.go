package types_test

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
)

func TestFromUser(t *testing.T) {
	tests := []struct {
		name     string
		user     *model.User
		expected types.ProviderUserData
	}{
		{
			name: "all fields populated",
			user: &model.User{
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
			expected: types.ProviderUserData{
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
		{
			name: "some fields empty",
			user: &model.User{
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
			expected: types.ProviderUserData{
				Provider: "ldap",
				Category: "default",
				UID:      "pau",
				Role:     rolePointer(model.RoleUser),
				Username: stringPointer("pau"),
				Email:    stringPointer("pau@example.org"),
			},
		},
		{
			name: "all fields empty",
			user: &model.User{},
			expected: types.ProviderUserData{
				Role:  nil,
				Group: nil,
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			var pUser types.ProviderUserData
			pUser.FromUser(tt.user)
			assert.Equal(t, tt.expected, pUser)
		})
	}
}

func TestToUser(t *testing.T) {
	tests := []struct {
		name     string
		pUser    types.ProviderUserData
		expected *model.User
	}{
		{
			name: "all fields populated",
			pUser: types.ProviderUserData{
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
			expected: &model.User{
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
		{
			name: "some fields empty",
			pUser: types.ProviderUserData{
				Provider: "ldap",
				Category: "default",
				UID:      "pau",
				Role:     rolePointer(model.RoleUser),
				Username: stringPointer("pau"),
				Email:    stringPointer("pau@example.org"),
			},
			expected: &model.User{
				Provider: "ldap",
				Category: "default",
				UID:      "pau",
				Role:     "user",
				Username: "pau",
				Email:    "pau@example.org",
			},
		},
		{
			name:  "all fields empty",
			pUser: types.ProviderUserData{},
			expected: &model.User{
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

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			user := tt.pUser.ToUser()
			assert.Equal(t, tt.expected, user)
		})
	}
}

func stringPointer(s string) *string {
	return &s
}

func rolePointer(r model.Role) *model.Role {
	return &r
}
