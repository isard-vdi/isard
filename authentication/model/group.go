package model

import (
	"context"
	"errors"
	"fmt"

	"gitlab.com/isard/isardvdi/pkg/db"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type Group struct {
	ID            string `rethinkdb:"id"`
	UID           string `rethinkdb:"uid"`
	Name          string `rethinkdb:"name"`
	Description   string `rethinkdb:"description"`
	Category      string `rethinkdb:"parent_category"`
	ExternalAppID string `rethinkdb:"external_app_id"`
	ExternalGID   string `rethinkdb:"external_gid"`
}

func (g *Group) GenerateNameExternal(prv string) {
	g.Name = fmt.Sprintf("%s_%s_%s", prv, g.ExternalAppID, g.ExternalGID)
}

func (g *Group) LoadExternal(ctx context.Context, sess r.QueryExecutor) error {
	res, err := r.Table("groups").Filter(r.And(
		r.Eq(r.Row.Field("external_app_id"), g.ExternalAppID),
		r.Eq(r.Row.Field("external_gid"), g.ExternalGID),
	), r.FilterOpts{}).Run(sess)
	if err != nil {
		return &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if err := res.One(g); err != nil {
		if errors.Is(err, r.ErrEmptyResult) {
			return db.ErrNotFound
		}

		return &db.Err{
			Msg: "read db response",
			Err: err,
		}
	}

	return nil
}

func (g *Group) Exists(ctx context.Context, sess r.QueryExecutor) (bool, error) {
	// Check if the group is original of IsardVDI or is a group mapped from elsewhere
	if g.ExternalAppID != "" && g.ExternalGID != "" {
		return g.ExistsWithExternal(ctx, sess)
	}

	res, err := r.Table("groups").Get(g.ID).Run(sess)
	if err != nil {
		return false, &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if res.IsNil() {
		return false, nil
	}

	if err := res.One(g); err != nil {
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

func (g *Group) existsWith(ctx context.Context, sess r.QueryExecutor, filter r.Term) (bool, error) {
	res, err := r.Table("groups").Filter(filter).Run(sess)
	if err != nil {
		return false, &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if res.IsNil() {
		return false, nil
	}

	if err := res.One(g); err != nil {
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

func (g *Group) ExistsWithExternal(ctx context.Context, sess r.QueryExecutor) (bool, error) {
	return g.existsWith(ctx, sess,
		r.And(
			r.Eq(r.Row.Field("external_app_id"), g.ExternalAppID),
			r.Eq(r.Row.Field("external_gid"), g.ExternalGID),
		),
	)
}

func (g *Group) ExistsWithUID(ctx context.Context, sess r.QueryExecutor) (bool, error) {
	return g.existsWith(ctx, sess,
		r.And(
			r.Eq(r.Row.Field("category"), g.Category),
			r.Eq(r.Row.Field("uid"), g.UID),
		),
	)
}
