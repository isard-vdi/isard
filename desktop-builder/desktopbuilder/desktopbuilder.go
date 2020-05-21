package desktopbuilder

import "github.com/isard-vdi/isard/desktop-builder/env"

type DesktopBuilder struct {
	env *env.Env
}

func New(env *env.Env) *DesktopBuilder {
	return &DesktopBuilder{env}
}
