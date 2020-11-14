package redis

import (
	"fmt"

	"github.com/go-redis/redis/v8"
)

func New(cluster bool, host string, port int, usr, pwd string) redis.Cmdable {
	addr := fmt.Sprintf("%s:%d", host, port)

	if cluster {
		return redis.NewClusterClient(&redis.ClusterOptions{
			Addrs:    []string{addr},
			Username: usr,
			Password: pwd,
		})
	}

	return redis.NewClient(&redis.Options{
		Addr:     addr,
		Username: usr,
		Password: pwd,
	})
}
