package model

import (
	"context"
	"errors"
	"fmt"
	"strings"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

const idsFieldSeparator = "-"

type Group struct {
	ID            string `rethinkdb:"id"`
	UID           string `rethinkdb:"uid"`
	Name          string `rethinkdb:"name"`
	Description   string `rethinkdb:"description"`
	Category      string `rethinkdb:"parent_category"`
	ExternalAppID string `rethinkdb:"external_app_id"`
	ExternalGID   string `rethinkdb:"external_gid"`
}

func (g *Group) JoinID() string {
	return strings.Join([]string{g.Category, g.Name}, idsFieldSeparator)
}

func (g *Group) LoadExternal(ctx context.Context, sess r.QueryExecutor) error {
	res, err := r.Table("groups").Filter(r.And(
		r.Eq(r.Row.Field("external_app_id"), g.ExternalAppID),
		r.Eq(r.Row.Field("external_gid"), g.ExternalGID),
	), r.FilterOpts{}).Run(sess)
	if err != nil {
		return err
	}
	defer res.Close()

	if err := res.One(g); err != nil {
		if errors.Is(err, r.ErrEmptyResult) {
			return ErrNotFound
		}

		return fmt.Errorf("read db response: %w", err)
	}

	return nil
}
