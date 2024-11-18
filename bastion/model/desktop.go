package model

import (
	"context"
	"errors"
	"time"

	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/jellydator/ttlcache/v3"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

var desktopCache = ttlcache.New(
	ttlcache.WithTTL[string, Desktop](10*time.Second),
	ttlcache.WithDisableTouchOnHit[string, Desktop](),
)

func init() {
	go desktopCache.Start()
}

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
	cached := desktopCache.Get(d.ID)
	if cached != nil {
		*d = cached.Value()
		return nil
	}

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

	desktopCache.Set(d.ID, *d, ttlcache.DefaultTTL)

	return nil
}
