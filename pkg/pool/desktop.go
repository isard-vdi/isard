package pool

import (
	"context"
	"encoding/json"

	"gitlab.com/isard/isardvdi/pkg/state"

	"github.com/go-redis/redis/v8"
	"github.com/qmuntal/stateless"
)

const destkopStreamName = "desktops"

type Desktop struct {
	ID    string          `json:"id,omitempty"`
	State stateless.State `json:"state,omitempty"`
	Hyper string          `json:"hyper,omitempty"`
	XML   string          `json:"xml,omitempty"`
}

func (d *Desktop) GetID() string {
	return d.ID
}

func (d *Desktop) GetState() stateless.State {
	return d.State
}

func (d *Desktop) SetState(state stateless.State) {
	d.State = state
}

type DesktopPool struct {
	pool *pool
}

func NewDesktopPool(ctx context.Context, cli redis.Cmdable) *DesktopPool {
	d := &DesktopPool{}

	d.pool = newPool(destkopStreamName, cli, state.NewDesktopState, d.marshal, d.unmarshal, d.onErr)

	go d.pool.listen(ctx)

	return d
}

func (d *DesktopPool) marshal(desktop poolItem) ([]byte, error) {
	return json.Marshal(desktop)
}

func (d *DesktopPool) unmarshal(b []byte) (poolItem, error) {
	desktop := &Desktop{}

	if err := json.Unmarshal(b, desktop); err != nil {
		return nil, err
	}

	return desktop, nil
}

func (d *DesktopPool) onErr(err error) {
	// TODO: Handle errors?
}

func (d *DesktopPool) Get(id string) (*Desktop, error) {
	desktop, err := d.pool.get(id)
	if err != nil {
		return nil, err
	}

	return desktop.(*Desktop), nil
}

func (d *DesktopPool) Set(ctx context.Context, desktop *Desktop) error {
	return d.pool.set(ctx, desktop)
}

func (d *DesktopPool) List() ([]*Desktop, error) {
	val, err := d.pool.list()
	if err != nil {
		return nil, err
	}

	desktops := []*Desktop{}
	for _, d := range val {
		desktops = append(desktops, d.(*Desktop))
	}

	return desktops, nil
}

func (d *DesktopPool) Remove(ctx context.Context, id string) error {
	desktop, err := d.Get(id)
	if err != nil {
		return err
	}

	return d.pool.remove(ctx, desktop)
}

func (d *DesktopPool) Fire(desktop *Desktop, trigger stateless.Trigger) error {
	return d.pool.fire(desktop, trigger)
}
