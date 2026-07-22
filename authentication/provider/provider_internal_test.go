package provider

import (
	"context"
	"errors"
	"regexp"
	"testing"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestMatchRegexMultiple(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareRegexp   func() *regexp.Regexp
		Input           string
		ExpectedMatches []string
	}{
		"should be able to do a simple match": {
			PrepareRegexp: func() *regexp.Regexp {
				re, err := regexp.Compile(".*")
				require.NoError(err)

				return re
			},
			Input:           "nefix",
			ExpectedMatches: []string{"nefix"},
		},
		"should be able to do a simple group match": {
			PrepareRegexp: func() *regexp.Regexp {
				re, err := regexp.Compile("([^,]+)+")
				require.NoError(err)

				return re
			},
			Input:           "categoria1,categoria2,categoria3",
			ExpectedMatches: []string{"categoria1", "categoria2", "categoria3"},
		},
		"should be able to match a group": {
			PrepareRegexp: func() *regexp.Regexp {
				re, err := regexp.Compile("/home/users/([^/]+)/[^/]+/[^/]+")
				require.NoError(err)

				return re
			},
			Input:           "/home/users/escola/escola/nefix",
			ExpectedMatches: []string{"escola"},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			result := matchRegexMultiple(tc.PrepareRegexp(), tc.Input)

			assert.Equal(tc.ExpectedMatches, result)
		})
	}
}

func TestExtractGroups(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	nested := `^/[^/]+/(?P<primary>[^/]+)(?:/(?P<secondary>[^/]+))?$`

	cases := map[string]struct {
		Regex             string
		RawGroups         []string
		ExpectedPrimary   []string
		ExpectedSecondary []string
	}{
		"should extract nested primary and secondary groups": {
			Regex: nested,
			RawGroups: []string{
				"/ikasleak/ADFI",
				"/ikasleak/ADFI/CF",
				"/irakasleak/COC",
				"/ikasleak/ADFI/GF",
				"/ikasleak",
				"/irakasleak",
			},
			ExpectedPrimary:   []string{"ADFI", "COC"},
			ExpectedSecondary: []string{"CF", "GF"},
		},
		"should extract only the primary group if there's no secondary segment": {
			Regex:             nested,
			RawGroups:         []string{"/ikasleak/ADFI"},
			ExpectedPrimary:   []string{"ADFI"},
			ExpectedSecondary: []string{},
		},
		"should ignore strings that don't match the nested regex": {
			Regex:             nested,
			RawGroups:         []string{"/ikasleak", "/irakasleak"},
			ExpectedPrimary:   []string{},
			ExpectedSecondary: []string{},
		},
		"should fall back to flat matching if the regex has no primary group": {
			Regex:             `([^,]+)+`,
			RawGroups:         []string{"group1,group2,group3", "group1"},
			ExpectedPrimary:   []string{"group1", "group2", "group3"},
			ExpectedSecondary: []string{},
		},
		"should extract the capturing group in flat mode": {
			Regex:             `/home/users/([^/]+)/[^/]+/[^/]+`,
			RawGroups:         []string{"/home/users/escola/escola/nefix"},
			ExpectedPrimary:   []string{"escola"},
			ExpectedSecondary: []string{},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			re := regexp.MustCompile(tc.Regex)
			primary, secondary := extractGroups(re, tc.RawGroups)

			assert.Equal(tc.ExpectedPrimary, primary)
			assert.Equal(tc.ExpectedSecondary, secondary)
		})
	}
}

func TestGuessCategory(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	rawGroups := []string{"group1", "group2", "group3"}
	rawRoles := []string{"hello", "admin", "how", "are", "you?:)"}

	cases := map[string]struct {
		PrepareDB       func(*r.Mock)
		Secret          string
		PrepareRegexp   func() *regexp.Regexp
		RawCategories   []string
		RawGroups       *[]string
		RawRoles        *[]string
		PrepareUserData func() *types.ProviderUserData

		ExpectedErr   string
		CheckToken    func(string)
		CheckUserData func(*types.ProviderUserData)
	}{
		"should work as expected": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").GetAllByIndex("uid", "categoria1")).Return([]interface{}{
					map[string]interface{}{
						"id":          "categoria1",
						"uid":         "categoria1",
						"name":        "Categoria 1",
						"description": "Descripció de categoria 1",
						"photo":       "https://clipground.com/images/potato-emoji-clipart-9.jpg",
					},
				}, nil)
				m.On(r.Table("categories").GetAllByIndex("uid", "categoria2")).Return([]interface{}{
					map[string]interface{}{
						"id":          "categoria2",
						"uid":         "categoria2",
						"name":        "Categoria 2",
						"description": "Descripció de categoria 2",
						"photo":       "https://clipground.com/images/potato-emoji-clipart-9.jpg",
					},
				}, nil)
				m.On(r.Table("categories").GetAllByIndex("uid", "categoria3")).Return([]interface{}{
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
			RawGroups:     &rawGroups,
			RawRoles:      &rawRoles,
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

				expectedRawGroups := []string{"group1", "group2", "group3"}
				expectedRawRoles := []string{"hello", "admin", "how", "are", "you?:)"}

				assert.Equal(&expectedRawGroups, claims.RawGroups)
				assert.Equal(&expectedRawRoles, claims.RawRoles)
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
				m.On(r.Table("categories").GetAllByIndex("uid", "categoria1")).Return([]interface{}{
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
				m.On(r.Table("categories").GetAllByIndex("uid", "categoria1")).Return([]interface{}{
					map[string]interface{}{
						"id":          "categoria1",
						"uid":         "categoria1",
						"name":        "Categoria 1",
						"description": "Descripció de categoria 1",
						"photo":       "https://clipground.com/images/potato-emoji-clipart-9.jpg",
					},
				}, nil)
				m.On(r.Table("categories").GetAllByIndex("uid", "categoria2")).Return([]interface{}{}, nil)
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
			ExpectedErr: "user can't use IsardVDI: user doesn't have any valid category, received raw: '[categoria1 categoria2]', extracted UIDs: '[]' (none found in database)",
		},
		"should parse the categories correctly from a single field, with multiple regex matches": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").GetAllByIndex("uid", "categoria1")).Return([]interface{}{
					map[string]interface{}{
						"id":          "categoria1",
						"uid":         "categoria1",
						"name":        "Categoria 1",
						"description": "Descripció de categoria 1",
						"photo":       "https://clipground.com/images/potato-emoji-clipart-9.jpg",
					},
				}, nil)
				m.On(r.Table("categories").GetAllByIndex("uid", "categoria2")).Return([]interface{}{}, nil)
				m.On(r.Table("categories").GetAllByIndex("uid", "categoria3")).Return([]interface{}{}, nil)
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
				m.On(r.Table("categories").GetAllByIndex("uid", "categoria1")).Return([]interface{}{}, errors.New("eRRoR"))
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
		"should match a regex group in a signle field response": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").GetAllByIndex("uid", "escola")).Return([]interface{}{
					map[string]interface{}{
						"id":          "escola",
						"uid":         "escola",
						"name":        "Escola",
						"description": "Descripció de escola",
						"photo":       "https://clipground.com/images/potato-emoji-clipart-9.jpg",
					},
				}, nil)
			},
			Secret: "Nodigasna",
			PrepareRegexp: func() *regexp.Regexp {
				re, err := regexp.Compile("/home/users/([^/]+)/[^/]+/[^/]+")
				require.NoError(err)

				return re
			},
			RawCategories: []string{"/home/users/escola/escola/isardqueryldap"},
			PrepareUserData: func() *types.ProviderUserData {
				name := "Escola"

				return &types.ProviderUserData{
					Provider: types.ProviderSAML,
					Category: "",
					UID:      "escola",
					Name:     &name,
				}
			},
			CheckUserData: func(u *types.ProviderUserData) {
				name := "Escola"
				expected := &types.ProviderUserData{
					Provider: types.ProviderSAML,
					Category: "escola",
					UID:      "escola",
					Name:     &name,
				}

				assert.Equal(expected, u)
			},
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
			tkn, err := guessCategory(ctx, log.New("authentication-test", "debug"), mock, tc.Secret, tc.PrepareRegexp(), tc.RawCategories, tc.RawGroups, tc.RawRoles, u)

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

func TestGuessGroup(t *testing.T) {
	t.Parallel()
	assert := assert.New(t)

	nested := `^/[^/]+/(?P<primary>[^/]+)(?:/(?P<secondary>[^/]+))?$`

	cases := map[string]struct {
		PrepareDB         func(*r.Mock)
		DefaultGroup      string
		RawGroups         []string
		ExpectedPrimary   string
		ExpectedSecondary []string
		ExpectedErr       string
	}{
		"should map nested groups to a primary and secondaries": {
			PrepareDB: func(m *r.Mock) {
				groups := []*model.Group{
					genExternalGroup(Unknown{}, "default", "ADFI"),
					genExternalGroup(Unknown{}, "default", "COC"),
				}
				m.On(r.Table("groups").Filter(func(row r.Term) r.Term {
					return r.Expr(groups).Contains(func(group r.Term) r.Term {
						return r.And(
							r.Eq(row.Field("parent_category"), group.Field("parent_category")),
							r.Eq(row.Field("external_app_id"), group.Field("external_app_id")),
							r.Eq(row.Field("external_gid"), group.Field("external_gid")),
						)
					})
				})).Return([]any{}, nil)
			},
			RawGroups: []string{
				"/ikasleak/ADFI",
				"/ikasleak/ADFI/CF",
				"/irakasleak/COC",
				"/ikasleak/ADFI/GF",
				"/ikasleak",
				"/irakasleak",
			},
			ExpectedPrimary:   "ADFI",
			ExpectedSecondary: []string{"COC", "CF", "GF"},
		},
		"should prefer an already-existing group as the primary": {
			PrepareDB: func(m *r.Mock) {
				groups := []*model.Group{
					genExternalGroup(Unknown{}, "default", "ADFI"),
					genExternalGroup(Unknown{}, "default", "COC"),
				}
				m.On(r.Table("groups").Filter(func(row r.Term) r.Term {
					return r.Expr(groups).Contains(func(group r.Term) r.Term {
						return r.And(
							r.Eq(row.Field("parent_category"), group.Field("parent_category")),
							r.Eq(row.Field("external_app_id"), group.Field("external_app_id")),
							r.Eq(row.Field("external_gid"), group.Field("external_gid")),
						)
					})
				})).Return([]any{
					map[string]any{
						"parent_category": "default",
						"external_app_id": "provider-unknown",
						"external_gid":    "COC",
					},
				}, nil)
			},
			RawGroups:         []string{"/ikasleak/ADFI", "/irakasleak/COC"},
			ExpectedPrimary:   "COC",
			ExpectedSecondary: []string{"ADFI"},
		},
		"should prefer the earliest existing group in IdP order when several exist": {
			PrepareDB: func(m *r.Mock) {
				groups := []*model.Group{
					genExternalGroup(Unknown{}, "default", "ADFI"),
					genExternalGroup(Unknown{}, "default", "COC"),
				}
				m.On(r.Table("groups").Filter(func(row r.Term) r.Term {
					return r.Expr(groups).Contains(func(group r.Term) r.Term {
						return r.And(
							r.Eq(row.Field("parent_category"), group.Field("parent_category")),
							r.Eq(row.Field("external_app_id"), group.Field("external_app_id")),
							r.Eq(row.Field("external_gid"), group.Field("external_gid")),
						)
					})
				})).Return([]any{
					map[string]any{
						"parent_category": "default",
						"external_app_id": "provider-unknown",
						"external_gid":    "COC",
					},
					map[string]any{
						"parent_category": "default",
						"external_app_id": "provider-unknown",
						"external_gid":    "ADFI",
					},
				}, nil)
			},
			RawGroups:         []string{"/ikasleak/ADFI", "/irakasleak/COC"},
			ExpectedPrimary:   "ADFI",
			ExpectedSecondary: []string{"COC"},
		},
		"should deduplicate a group mapped as both a primary and a secondary": {
			PrepareDB: func(m *r.Mock) {
				groups := []*model.Group{
					genExternalGroup(Unknown{}, "default", "ADFI"),
					genExternalGroup(Unknown{}, "default", "COC"),
					genExternalGroup(Unknown{}, "default", "GRP"),
				}
				m.On(r.Table("groups").Filter(func(row r.Term) r.Term {
					return r.Expr(groups).Contains(func(group r.Term) r.Term {
						return r.And(
							r.Eq(row.Field("parent_category"), group.Field("parent_category")),
							r.Eq(row.Field("external_app_id"), group.Field("external_app_id")),
							r.Eq(row.Field("external_gid"), group.Field("external_gid")),
						)
					})
				})).Return([]any{}, nil)
			},
			RawGroups:         []string{"/ikasleak/ADFI", "/ikasleak/COC", "/irakasleak/GRP/COC"},
			ExpectedPrimary:   "ADFI",
			ExpectedSecondary: []string{"COC", "GRP"},
		},
		"should fall back to the default group when nothing matches": {
			DefaultGroup:      "default-group",
			RawGroups:         []string{"/ikasleak"},
			ExpectedPrimary:   "default-group",
			ExpectedSecondary: []string{},
		},
		"should return an error when nothing matches and there's no default group": {
			RawGroups:   []string{"/ikasleak"},
			ExpectedErr: "invalid credentials: emtpy user group, no default",
		},
		"should return an internal error if the DB check fails": {
			PrepareDB: func(m *r.Mock) {
				groups := []*model.Group{genExternalGroup(Unknown{}, "default", "ADFI")}
				m.On(r.Table("groups").Filter(func(row r.Term) r.Term {
					return r.Expr(groups).Contains(func(group r.Term) r.Term {
						return r.And(
							r.Eq(row.Field("parent_category"), group.Field("parent_category")),
							r.Eq(row.Field("external_app_id"), group.Field("external_app_id")),
							r.Eq(row.Field("external_gid"), group.Field("external_gid")),
						)
					})
				})).Return(nil, errors.New("boom"))
			},
			RawGroups:   []string{"/ikasleak/ADFI"},
			ExpectedErr: "internal server error: guess primary group: check if groups already exist: boom",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			var sess r.QueryExecutor
			var mock *r.Mock
			if tc.PrepareDB != nil {
				mock = r.NewMock()
				tc.PrepareDB(mock)
				sess = mock
			}

			opts := guessGroupOpts{
				Provider:     Unknown{},
				ReGroup:      regexp.MustCompile(nested),
				DefaultGroup: tc.DefaultGroup,
			}
			u := &types.ProviderUserData{Category: "default"}

			primary, secondary, err := guessGroup(t.Context(), sess, opts, u, tc.RawGroups)

			if mock != nil {
				mock.AssertExpectations(t)
			}

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
				assert.Nil(primary)
				assert.Empty(secondary)

				return
			}

			assert.Nil(err)
			assert.Equal(tc.ExpectedPrimary, primary.ExternalGID)

			gids := []string{}
			for _, g := range secondary {
				gids = append(gids, g.ExternalGID)
			}
			assert.Equal(tc.ExpectedSecondary, gids)
		})
	}
}

func TestGuessRole(t *testing.T) {
	cases := map[string]struct {
		Cfg          guessRoleOpts
		AllUsrRoles  []string
		ExpectedRole model.Role
		ExpectedErr  string
	}{
		"should work as expected": {
			Cfg: guessRoleOpts{
				ReRole:          regexp.MustCompile(".*"),
				RoleAdminIDs:    []string{"other-admin", "admin"},
				RoleManagerIDs:  []string{"manager"},
				RoleAdvancedIDs: []string{"advanced"},
				RoleUserIDs:     []string{"user"},
				RoleDefault:     model.RoleUser,
			},
			AllUsrRoles:  []string{"aaa", "user", "advanced", "admin"},
			ExpectedRole: model.RoleAdmin,
		},
		"should fallback to the default role if not found": {
			Cfg: guessRoleOpts{
				ReRole:          regexp.MustCompile(".*"),
				RoleAdminIDs:    []string{"other-admin", "admin"},
				RoleManagerIDs:  []string{"manager"},
				RoleAdvancedIDs: []string{"advanced"},
				RoleUserIDs:     []string{"user"},
				RoleDefault:     model.RoleUser,
			},
			AllUsrRoles:  []string{"aaa", "bbb", "ccc", "ddd"},
			ExpectedRole: model.RoleUser,
		},
		"should return an error if no role is found and there's no default": {
			Cfg: guessRoleOpts{
				ReRole:          regexp.MustCompile(".*"),
				RoleAdminIDs:    []string{"other-admin", "admin"},
				RoleManagerIDs:  []string{"manager"},
				RoleAdvancedIDs: []string{"advanced"},
				RoleUserIDs:     []string{"user"},
			},
			AllUsrRoles: []string{"aaa", "bbb", "ccc", "ddd"},
			ExpectedErr: "invalid credentials: emtpy user role, no default",
		},
		"should return an err if no role is found and there's no default #2": {
			Cfg: guessRoleOpts{
				ReRole:          regexp.MustCompile("([^,]+)+"),
				RoleAdminIDs:    []string{"4ea5c9e6-c94f-4d70-8593-f1f83e88dd0e"},
				RoleManagerIDs:  []string{"70899241-137a-4525-b762-32bec47f9292"},
				RoleAdvancedIDs: []string{},
				RoleUserIDs:     []string{},
			},
			AllUsrRoles: []string{
				"cfa133fa-175d-4f6f-a160-2deb0b757e50",
				"5df8e55b-9785-41e7-ae98-085e01de36c4",
				"a0b4fc1c-8bae-4980-9fdd-1c91afa7f23c",
				"71782231-4312-4dfa-8707-1720fe8e90ba",
				"0a1e46a5-b6aa-4381-826e-147c8b507195",
			},
			ExpectedErr: "invalid credentials: emtpy user role, no default",
		},
	}

	for name, tc := range cases {
		assert := assert.New(t)

		t.Run(name, func(t *testing.T) {
			role, err := guessRole(tc.Cfg, tc.AllUsrRoles)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.Nil(err)
			}

			if tc.ExpectedRole != "" {
				assert.Equal(tc.ExpectedRole, *role)
			}
		})
	}
}
