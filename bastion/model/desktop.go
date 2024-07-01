package model

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/pkg/db"

	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type Desktop struct {
	ID              string                 `rethinkdb:"id"`
	Kind            string                 `rethinkdb:"kind"`
	Status          string                 `rethinkdb:"status"`
	GuestProperties DesktopGuestProperties `rethinkdb:"guest_properties"`
	Viewer          *DesktopViewer         `rethinkdb:"viewer,omitempty"`
}

type DesktopGuestProperties struct {
	Credentials DesktopGuestPropertiesCredentials `rethinkdb:"credentials"`
}

type DesktopGuestPropertiesCredentials struct {
	Username string `rethinkdb:"username"`
	Password string `rethinkdb:"password"`
}

type DesktopViewer struct {
	GuestIP *string `rethinkdb:"guest_ip,omitempty"`
}

func (d *Desktop) Load(ctx context.Context, sess r.QueryExecutor) error {
	res, err := r.Table("domains").Get(d.ID).Run(sess)
	if err != nil {
		return &db.Err{
			Err: err,
		}
	}
	defer res.Close()

	if err := res.One(d); err != nil {
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
