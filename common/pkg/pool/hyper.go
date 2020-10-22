package pool

import (
	"context"
	"encoding/json"

	"github.com/go-redis/redis/v8"
)

const hyperStreamName = "hypervisors"

type HyperState int

const (
	HyperStateUnknown HyperState = iota
	HyperStateOk
	HyperStateMigrating
	HyperStateOff
)

type Hyper struct {
	Host  string
	State HyperState
}

func (h *Hyper) ID() string {
	return h.Host
}

type HyperPool struct {
	pool *Pool
}

func NewHyperPool(ctx context.Context, cli *redis.Client) *HyperPool {
	h := &HyperPool{}
	h.pool = NewPool(hyperStreamName, cli, h.unmarshal, h.onErr)

	go h.pool.listen(ctx)

	return h
}

func (h *HyperPool) unmarshal(b []byte) (poolItem, error) {
	hyper := &Hyper{}

	if err := json.Unmarshal(b, hyper); err != nil {
		return nil, err
	}

	return hyper, nil
}

func (h *HyperPool) onErr(err error) {
	// TODO: Handle errors?
}

func (h *HyperPool) Get(host string) (*Hyper, error) {
	hyper, err := h.pool.Get(host)
	if err != nil {
		return nil, err
	}

	return hyper.(*Hyper), nil
}

func (h *HyperPool) List() ([]*Hyper, error) {
	val, err := h.pool.List()
	if err != nil {
		return nil, err
	}

	hypers := []*Hyper{}
	for _, h := range val {
		hypers = append(hypers, h.(*Hyper))
	}

	return hypers, nil
}
