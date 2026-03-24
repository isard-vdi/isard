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

func TestCategoryLoad(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB        func(*r.Mock)
		Category         *model.Category
		ExpectedCategory *model.Category
		ExpectedErr      string
	}{
		"should load a category successfully": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]interface{}{
					map[string]interface{}{
						"id":          "default",
						"uid":         "default",
						"name":        "Default",
						"description": "The default category",
						"photo":       "https://example.org/photo.jpg",
						"authentication": map[string]interface{}{
							"local": map[string]interface{}{
								"email_domain_restriction": map[string]interface{}{"enabled": true, "allowed": []string{"example.org"}},
							},
						},
					},
				}, nil)
			},
			Category: &model.Category{ID: "default"},
			ExpectedCategory: &model.Category{
				ID:          "default",
				UID:         "default",
				Name:        "Default",
				Description: "The default category",
				Photo:       "https://example.org/photo.jpg",
				Authentication: &model.CategoryAuthentication{
					Local: &model.CategoryAuthLocal{
						EmailDomainRestriction: model.CategoryAuthenticationEmailDomainRestriction{Enabled: true, Allowed: []string{"example.org"}},
					},
				},
			},
		},
		"should load a category with config_source global for LDAP": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("with-global-ldap")).Return([]interface{}{
					map[string]interface{}{
						"id":  "with-global-ldap",
						"uid": "with-global-ldap",
						"authentication": map[string]interface{}{
							"ldap": map[string]interface{}{
								"config_source": "global",
							},
						},
					},
				}, nil)
			},
			Category: &model.Category{ID: "with-global-ldap"},
			ExpectedCategory: &model.Category{
				ID:  "with-global-ldap",
				UID: "with-global-ldap",
				Authentication: &model.CategoryAuthentication{
					LDAP: &model.CategoryAuthLDAP{
						ConfigSource: model.CategoryAuthenticationConfigSourceGlobal,
					},
				},
			},
		},
		"should load a category with config_source custom for SAML": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("with-custom-saml")).Return([]interface{}{
					map[string]interface{}{
						"id":  "with-custom-saml",
						"uid": "with-custom-saml",
						"authentication": map[string]interface{}{
							"saml": map[string]interface{}{
								"config_source": "custom",
								"saml_config": map[string]interface{}{
									"metadata_url": "https://saml.test/metadata",
								},
							},
						},
					},
				}, nil)
			},
			Category: &model.Category{ID: "with-custom-saml"},
			ExpectedCategory: &model.Category{
				ID:  "with-custom-saml",
				UID: "with-custom-saml",
				Authentication: &model.CategoryAuthentication{
					SAML: &model.CategoryAuthSAML{
						ConfigSource: model.CategoryAuthenticationConfigSourceCustom,
						SAMLConfig:   &model.SAMLConfig{MetadataURL: "https://saml.test/metadata"},
					},
				},
			},
		},
		"should load a category with config_source global for Google": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("with-global-google")).Return([]interface{}{
					map[string]interface{}{
						"id":  "with-global-google",
						"uid": "with-global-google",
						"authentication": map[string]interface{}{
							"google": map[string]interface{}{
								"config_source": "global",
							},
						},
					},
				}, nil)
			},
			Category: &model.Category{ID: "with-global-google"},
			ExpectedCategory: &model.Category{
				ID:  "with-global-google",
				UID: "with-global-google",
				Authentication: &model.CategoryAuthentication{
					Google: &model.CategoryAuthGoogle{
						ConfigSource: model.CategoryAuthenticationConfigSourceGlobal,
					},
				},
			},
		},
		"should return ErrNotFound when category does not exist": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("nonexistent")).Return([]interface{}{}, nil)
			},
			Category:         &model.Category{ID: "nonexistent"},
			ExpectedCategory: &model.Category{ID: "nonexistent"},
			ExpectedErr:      db.ErrNotFound.Error(),
		},
		"should return an error on DB failure": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return(nil, errors.New("connection refused"))
			},
			Category:         &model.Category{ID: "default"},
			ExpectedCategory: &model.Category{ID: "default"},
			ExpectedErr:      "connection refused",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			mock := r.NewMock()
			tc.PrepareDB(mock)

			result, err := tc.Category.Load(context.Background(), mock)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
				assert.Nil(result)
			} else {
				assert.NoError(err)
				assert.Equal(tc.ExpectedCategory, result)
			}

			mock.AssertExpectations(t)
		})
	}
}

func TestCategoryExists(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB      func(*r.Mock)
		Category       *model.Category
		ExpectedExists bool
		ExpectedErr    string
	}{
		"should return true when category exists": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return([]interface{}{
					map[string]interface{}{
						"id":   "default",
						"uid":  "default",
						"name": "Default",
					},
				}, nil)
			},
			Category:       &model.Category{ID: "default"},
			ExpectedExists: true,
		},
		"should return false when category does not exist": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("nonexistent")).Return([]interface{}{}, nil)
			},
			Category:       &model.Category{ID: "nonexistent"},
			ExpectedExists: false,
		},
		"should return an error on DB failure": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Get("default")).Return(nil, errors.New("connection refused"))
			},
			Category:    &model.Category{ID: "default"},
			ExpectedErr: "connection refused",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			mock := r.NewMock()
			tc.PrepareDB(mock)

			exists, err := tc.Category.Exists(context.Background(), mock)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedExists, exists)

			mock.AssertExpectations(t)
		})
	}
}

func TestCategoryExistsWithUID(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB      func(*r.Mock)
		Category       *model.Category
		ExpectedExists bool
		ExpectedErr    string
	}{
		"should return true when category with UID exists": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Filter(
					r.Eq(r.Row.Field("uid"), "my-uid"),
				)).Return([]interface{}{
					map[string]interface{}{
						"id":   "some-id",
						"uid":  "my-uid",
						"name": "My Category",
					},
				}, nil)
			},
			Category:       &model.Category{UID: "my-uid"},
			ExpectedExists: true,
		},
		"should return false when category with UID does not exist": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Filter(
					r.Eq(r.Row.Field("uid"), "nonexistent-uid"),
				)).Return([]interface{}{}, nil)
			},
			Category:       &model.Category{UID: "nonexistent-uid"},
			ExpectedExists: false,
		},
		"should return an error on DB failure": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("categories").Filter(
					r.Eq(r.Row.Field("uid"), "my-uid"),
				)).Return(nil, errors.New("connection refused"))
			},
			Category:    &model.Category{UID: "my-uid"},
			ExpectedErr: "connection refused",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			mock := r.NewMock()
			tc.PrepareDB(mock)

			exists, err := tc.Category.ExistsWithUID(context.Background(), mock)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedExists, exists)

			mock.AssertExpectations(t)
		})
	}
}

func TestCategoryConfigurationsLoad(t *testing.T) {
	assert := assert.New(t)

	pluckQuery := r.Table("categories").Pluck("id", "authentication", map[string]any{
		"branding": map[string]any{
			"domain": true,
		},
	})

	cases := map[string]struct {
		PrepareDB      func(*r.Mock)
		ExpectedResult map[string]model.CategoryConfigEntry
		ExpectedErr    string
	}{
		"should load configurations for multiple categories": {
			PrepareDB: func(m *r.Mock) {
				m.On(pluckQuery).Return([]any{
					map[string]any{
						"id": "cat1",
						"authentication": map[string]any{
							"local": map[string]any{
								"email_domain_restriction": map[string]any{"enabled": true, "allowed": []string{"example.org"}},
							},
						},
					},
					map[string]any{
						"id": "cat2",
						"authentication": map[string]any{
							"saml": map[string]any{
								"email_domain_restriction": map[string]any{"enabled": true, "allowed": []string{"corp.com"}},
							},
						},
						"branding": map[string]any{
							"domain": map[string]any{"enabled": true, "name": "custom.example.com"},
						},
					},
				}, nil)
			},
			ExpectedResult: map[string]model.CategoryConfigEntry{
				"cat1": {
					Authentication: model.CategoryAuthentication{
						Local: &model.CategoryAuthLocal{
							EmailDomainRestriction: model.CategoryAuthenticationEmailDomainRestriction{Enabled: true, Allowed: []string{"example.org"}},
						},
					},
				},
				"cat2": {
					Authentication: model.CategoryAuthentication{
						SAML: &model.CategoryAuthSAML{
							EmailDomainRestriction: model.CategoryAuthenticationEmailDomainRestriction{Enabled: true, Allowed: []string{"corp.com"}},
						},
					},
					Branding: model.CategoryBranding{
						Domain: model.CategoryBrandingDomain{Enabled: true, Name: "custom.example.com"},
					},
				},
			},
		},
		"should return empty map when no categories have authentication": {
			PrepareDB: func(m *r.Mock) {
				m.On(pluckQuery).Return([]any{
					map[string]any{
						"id": "cat1",
					},
				}, nil)
			},
			ExpectedResult: map[string]model.CategoryConfigEntry{
				"cat1": {},
			},
		},
		"should return nil when result is nil (empty DB)": {
			PrepareDB: func(m *r.Mock) {
				m.On(pluckQuery).Return([]any{}, nil)
			},
			ExpectedResult: nil,
		},
		"should return an error on DB failure": {
			PrepareDB: func(m *r.Mock) {
				m.On(pluckQuery).Return(nil, errors.New("connection refused"))
			},
			ExpectedErr: "connection refused",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			mock := r.NewMock()
			tc.PrepareDB(mock)

			result, err := model.CategoryConfigurationsLoad(context.Background(), mock)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedResult, result)

			mock.AssertExpectations(t)
		})
	}
}
