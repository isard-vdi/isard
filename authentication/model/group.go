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

func (g *Group) GenerateNameExternal(label string) {
	g.Name = fmt.Sprintf("[%s] %s", label, g.ExternalGID)
}

func (g *Group) SameExternal(other *Group) bool {
	return g.Category == other.Category &&
		g.ExternalAppID == other.ExternalAppID &&
		g.ExternalGID == other.ExternalGID
}

func (g *Group) externalFilter() r.Term {
	return r.And(
		r.Eq(r.Row.Field("external_app_id"), g.ExternalAppID),
		r.Eq(r.Row.Field("external_gid"), g.ExternalGID),
	)
}

func (g *Group) LoadExternal(ctx context.Context, sess r.QueryExecutor) error {
	res, err := r.Table("groups").GetAllByIndex("parent_category", g.Category).Filter(g.externalFilter()).Run(sess, r.RunOpts{Context: ctx})
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

	res, err := r.Table("groups").Get(g.ID).Run(sess, r.RunOpts{Context: ctx})
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

func (g *Group) existsWith(ctx context.Context, sess r.QueryExecutor, category interface{}, filter r.Term) (bool, error) {
	res, err := r.Table("groups").GetAllByIndex("parent_category", category).Filter(filter).Run(sess, r.RunOpts{Context: ctx})
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
	return g.existsWith(ctx, sess, g.Category, g.externalFilter())
}

func GroupsExistsWithExternal(ctx context.Context, sess r.QueryExecutor, groups []*Group) ([]*Group, error) {
	res, err := r.Table("groups").Filter(func(row r.Term) r.Term {
		return r.Expr(groups).Contains(func(group r.Term) r.Term {
			return r.And(
				r.Eq(row.Field("parent_category"), group.Field("parent_category")),
				r.Eq(row.Field("external_app_id"), group.Field("external_app_id")),
				r.Eq(row.Field("external_gid"), group.Field("external_gid")),
			)
		})
	}).Run(sess, r.RunOpts{Context: ctx})
	if err != nil {
		return nil, &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if res.IsNil() {
		return []*Group{}, nil
	}

	result := []*Group{}
	if err := res.All(&result); err != nil {
		if errors.Is(err, r.ErrEmptyResult) {
			return []*Group{}, nil
		}

		return nil, &db.Err{
			Msg: "read db response",
			Err: err,
		}
	}

	return result, nil
}
