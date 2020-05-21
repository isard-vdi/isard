package env

import (
	"sync"

	"github.com/isard-vdi/isard/disk-operations/cfg"
	"github.com/isard-vdi/isard/disk-operations/diskoperations"

	"go.uber.org/zap"
)

type Env struct {
	WG    sync.WaitGroup
	Sugar *zap.SugaredLogger

	Cfg            cfg.Cfg
	DiskOperations *diskoperations.DiskOperations
}
