package redis

import (
	"fmt"
	"os"
	"time"

	"github.com/isard-vdi/isard/hyper-stats/env"

	"github.com/go-redis/redis/v7"
)

const Channel = "hypervisors"

type HyperState int

const (
	HyperStateUnknown HyperState = iota
	HyperStateOK
	HyperStateMigrating
	HyperStateStopping
)

type HyperMsg struct {
	ID    string
	State HyperState
	Time  time.Time
}

func Init(env *env.Env) {
	env.Redis = redis.NewClient(&redis.Options{
		Addr: fmt.Sprintf("%s:%d", env.Cfg.Redis.Host, env.Cfg.Redis.Port),
	})

	_, err := env.Redis.Ping().Result()
	if err != nil {
		env.Sugar.Fatalw("connect to redis",
			"err", err,
		)
	}

	env.WG.Add(1)
	go keepAlive(env)
}

func keepAlive(env *env.Env) {
	hostname := os.Getenv("HOSTNAME")

	select {
	case <-time.After(5 * time.Second):
		if _, err := env.Redis.Publish(Channel, HyperMsg{
			ID:    hostname,
			State: HyperStateOK,
			Time:  time.Now(),
		}).Result(); err != nil {
			env.Sugar.Errorw("send hyper keepalive",
				"err", err,
			)
		}

	case <-env.Ctx.Done():
		if _, err := env.Redis.Publish(Channel, HyperMsg{
			ID:    hostname,
			State: HyperStateStopping,
			Time:  time.Now(),
		}).Result(); err != nil {
			env.Sugar.Errorw("send hyper stop signal",
				"err", err,
			)
		}

		env.WG.Done()
		return
	}
}
