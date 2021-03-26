package provider

import (
	"context"
	"errors"
	"fmt"

	"gitlab.com/isard/isardvdi/pkg/pool"
	"gitlab.com/isard/isardvdi/pkg/state"

	"github.com/go-redis/redis/v8"
)

var ErrNoAvailableHyper = errors.New("no hypervisor with the capabilities requested is available")

type Provider interface {
	GetHyper(context.Context, *GetHyperOpts) (string, error)
}

type GetHyperOpts struct {
	Persistent bool
	GPU        bool
}

func New(ctx context.Context, provider string, redis redis.UniversalClient) (Provider, error) {
	switch provider {
	case "random":
		return NewRandom(ctx, redis), nil

	default:
		return nil, fmt.Errorf("unknown provider: %s", provider)
	}
}

func availableHypers(hypers []*pool.Hyper, opts *GetHyperOpts) []string {
	availHypers := []string{}

	for _, h := range hypers {
		if h.State == state.HyperStateReady {
			availHyp := true

			if opts.Persistent {
				if !h.Capabilites.Persistent {
					availHyp = false
				}
			}

			if opts.GPU {
				if !h.Capabilites.GPU {
					availHyp = false
				}
			}

			if availHyp {
				availHypers = append(availHypers, h.GetID())
			}
		}
	}

	return availHypers
}
