package desktopbuilder

import (
	"context"

	"github.com/isard-vdi/isard/desktop-builder/env"
)

type Interface interface {
	XMLGet(ctx context.Context, id string) (string, error)
	ViewerGet(xml string) (*Viewer, error)
}

type DesktopBuilder struct {
	env *env.Env
}

func New(env *env.Env) *DesktopBuilder {
	return &DesktopBuilder{env}
}
