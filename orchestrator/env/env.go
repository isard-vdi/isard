package env

import (
	"context"
	"sync"

	"github.com/isard-vdi/isard/orchestrator/cfg"
	"github.com/isard-vdi/isard/orchestrator/orchestrator"

	"github.com/go-redis/redis/v7"
	"go.uber.org/zap"
)

type Env struct {
	WG    sync.WaitGroup
	Ctx   context.Context
	Sugar *zap.SugaredLogger

	Cfg          cfg.Cfg
	Redis        *redis.Client
	Orchestrator orchestrator.Interface
}
