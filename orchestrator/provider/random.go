package provider

import (
	"context"
	"fmt"
	"math/rand"
	"time"

	"github.com/go-redis/redis/v8"
	"gitlab.com/isard/isardvdi/common/pkg/pool"
)

type Random struct {
	hypers *pool.HyperPool
}

func NewRandom(ctx context.Context, redis *redis.Client) *Random {
	return &Random{
		hypers: pool.NewHyperPool(ctx, redis),
	}
}

func (r *Random) GetHyper(opts *GetHyperOpts) (string, error) {
	hypers, err := r.hypers.List()
	if err != nil {
		return "", fmt.Errorf("get hypers list: %w", err)
	}

	availHypers := availableHypers(hypers, opts)
	if len(availHypers) == 0 {
		return "", ErrNoAvailableHyper
	}

	rand.Seed(time.Now().UnixNano())
	return availHypers[rand.Intn(len(availHypers))], nil
}
