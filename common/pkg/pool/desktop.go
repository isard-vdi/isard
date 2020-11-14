package pool

import (
	"context"
	"encoding/json"

	"github.com/go-redis/redis/v8"
	"github.com/qmuntal/stateless"
)

const destkopStreamName = "desktops"

type DesktopState int

type Desktop struct {
	ID  string
	XML string

	StateMachine *stateless.StateMachine
}

func (d *Desktop) GetID() string {
	return d.ID
}

type DesktopPool struct {
	pool *pool
}

func NewDesktopPool(ctx context.Context, cli redis.Cmdable) *DesktopPool {
	d := &DesktopPool{}
	// d.pool = newPool(destkopStreamName, cli, d.marshal, d.unmarshal, d.onErr)

	// go d.pool.listen(ctx)

	return d
}

func (d *DesktopPool) marshal(desktop poolItem) ([]byte, error) {
	return json.Marshal(desktop)
}

// func (d *DesktopPool) unmarshal(b []byte) (poolItem, error) {
// 	desktop := &Desktop{}

// 	if err := json.Unmarshal(b, desktop); err != nil {
// 		return nil, err
// 	}

// 	return desktop, nil
// }

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
