package desktopbuilder

import "github.com/isard-vdi/isard/desktop-builder/env"

type Interface interface {
	XMLGet(id string, template string) (string, error)
	ViewerGet(xml string) error
}

type DesktopBuilder struct {
	env *env.Env
}

func New(env *env.Env) (*DesktopBuilder, error) {
	return &DesktopBuilder{env}, nil
}
