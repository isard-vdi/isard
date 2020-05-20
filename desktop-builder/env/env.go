package env

import (
	"sync"

	"github.com/isard-vdi/isard/desktop-builder/cfg"
	"github.com/isard-vdi/isard/desktop-builder/desktopbuilder"

	"go.uber.org/zap"
)

type Env struct {
	WG    sync.WaitGroup
	Sugar *zap.SugaredLogger

	Cfg            cfg.Cfg
	DesktopBuilder *desktopbuilder.DesktopBuilder
}
