package pool

import (
	"context"
	"encoding/json"

	"github.com/go-redis/redis/v8"
)

const destkopStreamName = "desktops"

type DesktopState int

type Desktop struct {
	Id  string
	XML string
}

func (d *Desktop) ID() string {
	return d.Id
}

type DesktopPool struct {
	pool *Pool
}

func NewDesktopPool(ctx context.Context, cli *redis.Client) *DesktopPool {
	d := &DesktopPool{}
	d.pool = NewPool(destkopStreamName, cli, d.unmarshal, d.onErr)

	go d.pool.listen(ctx)

	return d
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
	desktop, err := d.pool.Get(id)
	if err != nil {
		return nil, err
	}

	return desktop.(*Desktop), nil
}
