package redis

import (
	"bytes"
	"encoding/gob"
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
	Host  string
	State HyperState
	Time  time.Time
}

func Init(env *env.Env) {
	env.Redis = redis.NewClient(&redis.Options{
		Addr:     fmt.Sprintf("%s:%d", env.Cfg.Redis.Host, env.Cfg.Redis.Port),
		Password: env.Cfg.Redis.Password,
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

	for {
		select {
		case <-time.After(5 * time.Second):
			var buf bytes.Buffer
			enc := gob.NewEncoder(&buf)
			if err := enc.Encode(HyperMsg{
				Host:  hostname,
				State: HyperStateOK,
				Time:  time.Now(),
			}); err != nil {
				env.Sugar.Errorw("encode hyper keepalive",
					"err", err,
				)
				break
			}

			if _, err := env.Redis.Publish(Channel, buf.Bytes()).Result(); err != nil {
				env.Sugar.Errorw("send hyper keepalive",
					"err", err,
				)
				break
			}

			env.Sugar.Info("hyper keepalive sent")

		case <-env.Ctx.Done():
			if _, err := env.Redis.Publish(Channel, HyperMsg{
				Host:  hostname,
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
}
