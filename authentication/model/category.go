package model

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/pkg/db"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type Category struct {
	ID             string                  `rethinkdb:"id"`
	UID            string                  `rethinkdb:"uid"`
	Name           string                  `rethinkdb:"name"`
	Description    string                  `rethinkdb:"description"`
	Photo          string                  `rethinkdb:"photo"`
	Authentication *CategoryAuthentication `rethinkdb:"authentication"`
}

type CategoryAuthentication struct {
	Local  *CategoryAuthLocal  `rethinkdb:"local"`
	LDAP   *CategoryAuthLDAP   `rethinkdb:"ldap"`
	SAML   *CategoryAuthSAML   `rethinkdb:"saml"`
	Google *CategoryAuthGoogle `rethinkdb:"google"`
}

type CategoryAuthenticationConfigSource string

const (
	CategoryAuthenticationConfigSourceGlobal CategoryAuthenticationConfigSource = "global"
	CategoryAuthenticationConfigSourceCustom CategoryAuthenticationConfigSource = "custom"
)

type CategoryAuthLocal struct {
	Disabled               bool                                         `rethinkdb:"disabled"`
	EmailDomainRestriction CategoryAuthenticationEmailDomainRestriction `rethinkdb:"email_domain_restriction"`
	ConfigSource           CategoryAuthenticationConfigSource           `rethinkdb:"config_source"`
}

type CategoryAuthLDAP struct {
	Disabled               bool                                         `rethinkdb:"disabled"`
	EmailDomainRestriction CategoryAuthenticationEmailDomainRestriction `rethinkdb:"email_domain_restriction"`
	ConfigSource           CategoryAuthenticationConfigSource           `rethinkdb:"config_source"`
	LDAPConfig             *LDAPConfig                                  `rethinkdb:"ldap_config"`
}

type CategoryAuthSAML struct {
	Disabled               bool                                         `rethinkdb:"disabled"`
	EmailDomainRestriction CategoryAuthenticationEmailDomainRestriction `rethinkdb:"email_domain_restriction"`
	ConfigSource           CategoryAuthenticationConfigSource           `rethinkdb:"config_source"`
	SAMLConfig             *SAMLConfig                                  `rethinkdb:"saml_config"`
}

type CategoryAuthGoogle struct {
	Disabled               bool                                         `rethinkdb:"disabled"`
	EmailDomainRestriction CategoryAuthenticationEmailDomainRestriction `rethinkdb:"email_domain_restriction"`
	ConfigSource           CategoryAuthenticationConfigSource           `rethinkdb:"config_source"`
	GoogleConfig           *GoogleConfig                                `rethinkdb:"google_config"`
}

type CategoryAuthenticationEmailDomainRestriction struct {
	Enabled bool     `rethinkdb:"enabled"`
	Allowed []string `rethinkdb:"allowed"`
}

type CategoryConfigEntry struct {
	Authentication CategoryAuthentication `rethinkdb:"authentication"`
	Branding       CategoryBranding       `rethinkdb:"branding"`
}

type CategoryBranding struct {
	Domain CategoryBrandingDomain `rethinkdb:"domain"`
}

type CategoryBrandingDomain struct {
	Enabled bool   `rethinkdb:"enabled"`
	Name    string `rethinkdb:"name"`
}

func (c *Category) Load(ctx context.Context, sess r.QueryExecutor) (*Category, error) {
	res, err := r.Table("categories").Get(c.ID).Run(sess)
	if err != nil {
		return nil, &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if res.IsNil() {
		return nil, db.ErrNotFound
	}

	if err := res.One(c); err != nil {
		return nil, &db.Err{
			Msg: "read db response",
			Err: err,
		}
	}

	return c, nil
}

func (c *Category) Exists(ctx context.Context, sess r.QueryExecutor) (bool, error) {
	res, err := r.Table("categories").Get(c.ID).Run(sess)
	if err != nil {
		return false, &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if res.IsNil() {
		return false, nil
	}

	if err := res.One(c); err != nil {
		if errors.Is(err, r.ErrEmptyResult) {
			return false, nil
		}

		return false, &db.Err{
			Msg: "read db response",
			Err: err,
		}
	}

	return true, nil
}

func (c *Category) ExistsWithUID(ctx context.Context, sess r.QueryExecutor) (bool, error) {
	res, err := r.Table("categories").Filter(
		r.Eq(r.Row.Field("uid"), c.UID),
	).Run(sess)
	if err != nil {
		return false, &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if res.IsNil() {
		return false, nil
	}

	if err := res.One(c); err != nil {
		if errors.Is(err, r.ErrEmptyResult) {
			return false, nil
		}

		return false, &db.Err{
			Msg: "read db response",
			Err: err,
		}
	}

	return true, nil
}

func CategoryConfigurationsLoad(ctx context.Context, sess r.QueryExecutor) (map[string]CategoryConfigEntry, error) {
	res, err := r.Table("categories").Pluck("id", "authentication", map[string]any{
		"branding": map[string]any{
			"domain": true,
		},
	}).Run(sess, r.RunOpts{Context: ctx})
	if err != nil {
		return nil, &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if res.IsNil() {
		return nil, nil
	}

	result := []struct {
		ID             string                 `rethinkdb:"id"`
		Authentication CategoryAuthentication `rethinkdb:"authentication"`
		Branding       CategoryBranding       `rethinkdb:"branding"`
	}{}
	if err := res.All(&result); err != nil {
		if errors.Is(err, r.ErrEmptyResult) {
			return nil, nil
		}

		return nil, &db.Err{
			Msg: "read db response",
			Err: err,
		}
	}

	finalResult := map[string]CategoryConfigEntry{}
	for _, r := range result {
		finalResult[r.ID] = CategoryConfigEntry{
			Authentication: r.Authentication,
			Branding:       r.Branding,
		}
	}

	return finalResult, nil
}
