package authentication

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"gitlab.com/isard/isardvdi/authentication/model"
)

func TestNormalizeIdentity(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		Group         *model.Group
		User          *model.User
		ExpectedGroup *model.Group
		ExpectedUser  *model.User
	}{
		"should normalize the identities correctly": {
			Group: &model.Group{
				Name:        "hello wörld \xF0 hola hola 123",
				Description: "hello wörld \xF0 hola hola 123",
			},
			User: &model.User{
				Name: "hello wörld \xF0 hola hola 123",
			},
			ExpectedGroup: &model.Group{
				Name:        "hello wörld  hola hola 123",
				Description: "hello wörld  hola hola 123",
			},
			ExpectedUser: &model.User{
				Name: "hello wörld  hola hola 123",
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			normalizeIdentity(tc.Group, tc.User)

			assert.Equal(tc.ExpectedGroup, tc.Group)
			assert.Equal(tc.ExpectedUser, tc.User)
		})
	}
}

func TestNormalizeString(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		String   string
		Expected string
	}{
		"should remove non UTF-8 characters correctly": {
			String:   "hello wörld \xF0 hola hola 123",
			Expected: "hello wörld  hola hola 123",
		},
		"should not remove anything else": {
			String:   "hola :D çççéééé:D",
			Expected: "hola :D çççéééé:D",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			assert.Equal(tc.Expected, normalizeString(tc.String))
		})
	}
}
