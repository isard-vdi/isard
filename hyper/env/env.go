package env

import (
	"sync"

	"github.com/isard-vdi/isard/hyper/cfg"

	"go.uber.org/zap"
)

type Env struct {
	WG    sync.WaitGroup
	Sugar *zap.SugaredLogger

	Cfg cfg.Cfg
}
