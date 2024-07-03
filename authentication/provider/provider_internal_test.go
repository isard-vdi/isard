package provider

import (
	"context"
	"errors"
	"regexp"
	"testing"

	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestGuessCategory(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareDB       func(*r.Mock)
		Secret          string
		PrepareRegexp   func() *regexp.Regexp
		RawCategories   []string
		PrepareUserData func() *types.ProviderUserData

		ExpectedErr   string
		CheckToken    func(string)
		CheckUserData func(*types.ProviderUserData)
	}{
		"should work as expected": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Filter(r.Eq(r.Row.Field("uid"), "categoria1"))).Return([]interface{}{
					map[string]interface{}{
						"id":          "categoria1",
						"uid":         "categoria1",
						"name":        "Categoria 1",
						"description": "Descripció de categoria 1",
						"photo":       "https://clipground.com/images/potato-emoji-clipart-9.jpg",
					},
				}, nil)
				m.On(r.Table("categories").Filter(r.Eq(r.Row.Field("uid"), "categoria2"))).Return([]interface{}{
					map[string]interface{}{
						"id":          "categoria2",
						"uid":         "categoria2",
						"name":        "Categoria 2",
						"description": "Descripció de categoria 2",
						"photo":       "https://clipground.com/images/potato-emoji-clipart-9.jpg",
					},
				}, nil)
				m.On(r.Table("categories").Filter(r.Eq(r.Row.Field("uid"), "categoria3"))).Return([]interface{}{
					map[string]interface{}{
						"id":          "categoria3",
						"uid":         "categoria3",
						"name":        "Categoria 3",
						"description": "Descripció de categoria 3",
						"photo":       "https://clipground.com/images/potato-emoji-clipart-9.jpg",
					},
				}, nil)
			},
			Secret: "Nodigasna",
			PrepareRegexp: func() *regexp.Regexp {
				re, err := regexp.Compile(".*")
				require.NoError(err)

				return re
			},
			RawCategories: []string{"categoria1", "categoria2", "categoria3"},
			PrepareUserData: func() *types.ProviderUserData {
				name := "Néfix Estrada"
				return &types.ProviderUserData{
					Provider: types.ProviderSAML,
					Category: "",
					UID:      "Néfix",

					Name: &name,
				}
			},
			CheckToken: func(ss string) {
				claims, err := token.ParseCategorySelectToken("Nodigasna", ss)
				assert.NoError(err)

				assert.Equal("isard-authentication", claims.Issuer)
				assert.Equal("isardvdi", claims.KeyID)
				// TODO: Test time
				assert.Equal([]token.CategorySelectClaimsCategory{{
					ID:    "categoria1",
					Name:  "Categoria 1",
					Photo: "https://clipground.com/images/potato-emoji-clipart-9.jpg",
				}, {
					ID:    "categoria2",
					Name:  "Categoria 2",
					Photo: "https://clipground.com/images/potato-emoji-clipart-9.jpg",
				}, {
					ID:    "categoria3",
					Name:  "Categoria 3",
					Photo: "https://clipground.com/images/potato-emoji-clipart-9.jpg",
				}}, claims.Categories)
			},
			CheckUserData: func(u *types.ProviderUserData) {
				name := "Néfix Estrada"
				expected := &types.ProviderUserData{
					Provider: types.ProviderSAML,
					Category: "",
					UID:      "Néfix",

					Name: &name,
				}

				assert.Equal(expected, u)
			},
		},
		"should return the category ID if the user only belongs to a single category": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Filter(r.Eq(r.Row.Field("uid"), "categoria1"))).Return([]interface{}{
					map[string]interface{}{
						"id":          "categoria1",
						"uid":         "categoria1",
						"name":        "Categoria 1",
						"description": "Descripció de categoria 1",
						"photo":       "https://clipground.com/images/potato-emoji-clipart-9.jpg",
					},
				}, nil)
			},
			Secret: "Nodigasna",
			PrepareRegexp: func() *regexp.Regexp {
				re, err := regexp.Compile(".*")
				require.NoError(err)

				return re
			},
			RawCategories: []string{"categoria1"},
			PrepareUserData: func() *types.ProviderUserData {
				name := "Néfix Estrada"
				return &types.ProviderUserData{
					Provider: types.ProviderSAML,
					Category: "",
					UID:      "Néfix",

					Name: &name,
				}
			},
			CheckUserData: func(u *types.ProviderUserData) {
				name := "Néfix Estrada"
				expected := &types.ProviderUserData{
					Provider: types.ProviderSAML,
					Category: "categoria1",
					UID:      "Néfix",

					Name: &name,
				}

				assert.Equal(expected, u)
			},
		},
		"should ignore categories that don't exist in the DB": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Filter(r.Eq(r.Row.Field("uid"), "categoria1"))).Return([]interface{}{
					map[string]interface{}{
						"id":          "categoria1",
						"uid":         "categoria1",
						"name":        "Categoria 1",
						"description": "Descripció de categoria 1",
						"photo":       "https://clipground.com/images/potato-emoji-clipart-9.jpg",
					},
				}, nil)
				m.On(r.Table("categories").Filter(r.Eq(r.Row.Field("uid"), "categoria2"))).Return([]interface{}{}, nil)
			},
			Secret: "Nodigasna",
			PrepareRegexp: func() *regexp.Regexp {
				re, err := regexp.Compile(".*")
				require.NoError(err)

				return re
			},
			RawCategories: []string{"categoria1", "categoria2"},
			PrepareUserData: func() *types.ProviderUserData {
				name := "Néfix Estrada"
				return &types.ProviderUserData{
					Provider: types.ProviderSAML,
					Category: "",
					UID:      "Néfix",

					Name: &name,
				}
			},
			CheckUserData: func(u *types.ProviderUserData) {
				name := "Néfix Estrada"
				expected := &types.ProviderUserData{
					Provider: types.ProviderSAML,
					Category: "categoria1",
					UID:      "Néfix",

					Name: &name,
				}

				assert.Equal(expected, u)
			},
		},
		"should return an error if the user doesn't belong to any category": {
			Secret: "Nodigasna",
			PrepareRegexp: func() *regexp.Regexp {
				re, err := regexp.Compile("AAAAAAAAAA.*")
				require.NoError(err)

				return re
			},
			RawCategories: []string{"categoria1", "categoria2"},
			PrepareUserData: func() *types.ProviderUserData {
				name := "Néfix Estrada"
				return &types.ProviderUserData{
					Provider: types.ProviderSAML,
					Category: "",
					UID:      "Néfix",

					Name: &name,
				}
			},
			CheckUserData: func(u *types.ProviderUserData) {
				name := "Néfix Estrada"
				expected := &types.ProviderUserData{
					Provider: types.ProviderSAML,
					Category: "",
					UID:      "Néfix",

					Name: &name,
				}

				assert.Equal(expected, u)
			},
			ExpectedErr: "invalid credentials: user doesn't have any valid category, recieved raw argument: '[categoria1 categoria2]'",
		},
		"should parse the categories correctly from a single field, with multiple regex matches": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Filter(r.Eq(r.Row.Field("uid"), "categoria1"))).Return([]interface{}{
					map[string]interface{}{
						"id":          "categoria1",
						"uid":         "categoria1",
						"name":        "Categoria 1",
						"description": "Descripció de categoria 1",
						"photo":       "https://clipground.com/images/potato-emoji-clipart-9.jpg",
					},
				}, nil)
				m.On(r.Table("categories").Filter(r.Eq(r.Row.Field("uid"), "categoria2"))).Return([]interface{}{}, nil)
				m.On(r.Table("categories").Filter(r.Eq(r.Row.Field("uid"), "categoria3"))).Return([]interface{}{}, nil)
			},
			Secret: "Nodigasna",
			PrepareRegexp: func() *regexp.Regexp {
				re, err := regexp.Compile("([^,]+)+")
				require.NoError(err)

				return re
			},
			RawCategories: []string{"categoria1,categoria2,categoria3"},
			PrepareUserData: func() *types.ProviderUserData {
				name := "Néfix Estrada"
				return &types.ProviderUserData{
					Provider: types.ProviderSAML,
					Category: "",
					UID:      "Néfix",

					Name: &name,
				}
			},
			CheckUserData: func(u *types.ProviderUserData) {
				name := "Néfix Estrada"
				expected := &types.ProviderUserData{
					Provider: types.ProviderSAML,
					Category: "categoria1",
					UID:      "Néfix",

					Name: &name,
				}

				assert.Equal(expected, u)
			},
		},
		"should return an error if there's an error checking if the category exists": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Filter(r.Eq(r.Row.Field("uid"), "categoria1"))).Return([]interface{}{}, errors.New("eRRoR"))
			},
			Secret: "Nodigasna",
			PrepareRegexp: func() *regexp.Regexp {
				re, err := regexp.Compile(".*")
				require.NoError(err)

				return re
			},
			RawCategories: []string{"categoria1", "categoria2"},
			PrepareUserData: func() *types.ProviderUserData {
				name := "Néfix Estrada"
				return &types.ProviderUserData{
					Provider: types.ProviderSAML,
					Category: "",
					UID:      "Néfix",

					Name: &name,
				}
			},
			CheckUserData: func(u *types.ProviderUserData) {
				name := "Néfix Estrada"
				expected := &types.ProviderUserData{
					Provider: types.ProviderSAML,
					Category: "",
					UID:      "Néfix",

					Name: &name,
				}

				assert.Equal(expected, u)
			},
			ExpectedErr: "internal server error: check category exists: eRRoR",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			mock := r.NewMock()

			if tc.PrepareDB != nil {
				tc.PrepareDB(mock)
			}

			ctx := context.Background()
			u := tc.PrepareUserData()
			tkn, err := guessCategory(ctx, mock, tc.Secret, tc.PrepareRegexp(), tc.RawCategories, u)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				if err != nil {
					assert.NoError(error(err))
				}
			}

			if tc.CheckToken != nil {
				tc.CheckToken(tkn)
			} else {
				assert.Zero(tkn)
			}

			if tc.CheckUserData != nil {
				tc.CheckUserData(u)
			}

			mock.AssertExpectations(t)
		})
	}
}
