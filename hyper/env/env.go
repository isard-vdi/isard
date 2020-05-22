package env

import (
	"sync"

	"github.com/isard-vdi/isard/hyper/cfg"
	"github.com/isard-vdi/isard/hyper/hyper"

	"go.uber.org/zap"
)

type Env struct {
	WG    sync.WaitGroup
	Sugar *zap.SugaredLogger

	Cfg   cfg.Cfg
	Hyper hyper.Interface
}
