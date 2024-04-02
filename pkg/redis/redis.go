package redis

import (
	"context"
	"fmt"

	"gitlab.com/isard/isardvdi/pkg/cfg"

	"github.com/redis/go-redis/v9"
)

func New(ctx context.Context, cfg cfg.Redis) (redis.UniversalClient, error) {
	cli := redis.NewUniversalClient(&redis.UniversalOptions{
		Addrs:    []string{cfg.Addr()},
		Username: cfg.Usr,
		Password: cfg.Pwd,
		DB:       cfg.DB,
	})
	if ping, err := cli.Ping(ctx).Result(); err != nil {
		return nil, fmt.Errorf("connect to the Redis: %s: %w", ping, err)
	}

	return cli, nil
}
