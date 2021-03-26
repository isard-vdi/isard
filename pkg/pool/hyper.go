package pool

import (
	"context"
	"encoding/json"

	"gitlab.com/isard/isardvdi/pkg/state"

	"github.com/go-redis/redis/v8"
	"github.com/qmuntal/stateless"
)

const hyperStreamName = "hypervisors"

type Hyper struct {
	Host        string            `json:"host,omitempty"`
	State       stateless.State   `json:"state,omitempty"`
	Capabilites *HyperCapabilites `json:"capabilites,omitempty"`
}

type HyperCapabilites struct {
	Persistent bool
	GPU        bool
}

func (h *Hyper) GetID() string {
	return h.Host
}

func (h *Hyper) GetState() stateless.State {
	return h.State
}

func (h *Hyper) SetState(state stateless.State) {
	h.State = state
}

type HyperPool struct {
	pool *pool
}

func NewHyperPool(ctx context.Context, cli redis.UniversalClient) *HyperPool {
	h := &HyperPool{}

	h.pool = newPool(hyperStreamName, cli, state.NewHyperState, h.marshal, h.unmarshal, h.onErr)

	go h.pool.listen(ctx)

	return h
}

func (h *HyperPool) marshal(hyper poolItem) ([]byte, error) {
	return json.Marshal(hyper)
}

func (h *HyperPool) unmarshal(b []byte) (poolItem, error) {
	hyper := &Hyper{}

	if err := json.Unmarshal(b, hyper); err != nil {
		return nil, err
	}

	if hyper.Capabilites == nil {
		hyper.Capabilites = &HyperCapabilites{}
	}

	return hyper, nil
}

func (h *HyperPool) onErr(err error) {
	// TODO: Handle errors?
}

func (h *HyperPool) Get(ctx context.Context, host string) (*Hyper, error) {
	hyper, err := h.pool.get(ctx, host)
	if err != nil {
		return nil, err
	}

	return hyper.(*Hyper), nil
}

func (h *HyperPool) Set(ctx context.Context, hyper *Hyper) error {
	return h.pool.set(ctx, hyper)
}

func (h *HyperPool) List(ctx context.Context) ([]*Hyper, error) {
	val, err := h.pool.list(ctx)
	if err != nil {
		return nil, err
	}

	hypers := []*Hyper{}
	for _, h := range val {
		hypers = append(hypers, h.(*Hyper))
	}

	return hypers, nil
}

func (h *HyperPool) Remove(ctx context.Context, host string) error {
	hyper, err := h.Get(ctx, host)
	if err != nil {
		return err
	}

	return h.pool.remove(ctx, hyper)
}

func (h *HyperPool) Fire(hyper *Hyper, trigger stateless.Trigger) error {
	return h.pool.fire(hyper, trigger)
}
