package desktopbuilder

import (
	"context"

	"github.com/go-pg/pg/v10"
	"gitlab.com/isard/isardvdi/common/pkg/model"
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
	desktop := &model.Desktop{ID: id}
	if err := d.db.WithContext(ctx).Model(desktop).WherePK().Select(); err != nil {
		// TODO: Handle this`
		panic(err)
	}

	return BuildDesktop(desktop)
}
