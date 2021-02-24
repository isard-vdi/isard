package desktopbuilder

import (
	"context"

	"gitlab.com/isard/isardvdi/pkg/model"

	"github.com/go-pg/pg/v10"
)

type Interface interface {
	XMLGet(ctx context.Context, id string) (string, error)
	ViewerGet(xml string) (*Viewer, error)
}

type DesktopBuilder struct {
	db *pg.DB
}

func New(db *pg.DB) *DesktopBuilder {
	return &DesktopBuilder{
		db: db,
	}
}

func (d *DesktopBuilder) XMLGet(ctx context.Context, id string) (string, error) {
	desktop := &model.Desktop{UUID: id}
	if err := desktop.LoadWithUUID(ctx, d.db); err != nil {
		panic(err)
	}

	return BuildDesktop(desktop)
}
