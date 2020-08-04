package env

import (
	"sync"

	"github.com/isard-vdi/isard/backend/cfg"
	"github.com/isard-vdi/isard/backend/isard"

	"github.com/crewjam/saml/samlsp"
	"github.com/go-redis/redis"
	"github.com/gorilla/sessions"
	"github.com/spf13/afero"
	"go.uber.org/zap"
)

// Env is used for dependency injection
type Env struct {
	WG    sync.WaitGroup
	Sugar *zap.SugaredLogger

	Cfg   cfg.Cfg
	FS    afero.Fs
	Redis *redis.Client
	Auth  *Auth
	Isard *isard.Isard
}

type Auth struct {
	SessStore sessions.Store
	SAML      *samlsp.Middleware
}
