package env

import (
	"context"
	"sync"

	"github.com/isard-vdi/isard/hyper-stats/cfg"

	"github.com/go-redis/redis/v7"
	"go.uber.org/zap"
)

type Env struct {
	Ctx   context.Context
	WG    sync.WaitGroup
	Sugar *zap.SugaredLogger

	Cfg   cfg.Cfg
	Redis *redis.Client
}
