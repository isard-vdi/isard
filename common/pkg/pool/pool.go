package pool

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"sync"
	"time"

	"github.com/bsm/redislock"
	"github.com/go-redis/redis/v8"
)

var ErrValueNotFound = errors.New("value not found in the pool")

const (
	msgKeyAction = "action"
	msgKeyData   = "data"
)

type PoolAction int

const (
	PoolActionUnknown PoolAction = iota
	PoolActionSet
	PoolActionDelete
)

type poolItem interface {
	ID() string
}

type Pool struct {
	name   string
	cli    *redis.Client
	locker *redislock.Client
	lastID string

	val map[string]interface{}
	mu  sync.Mutex

	unmarshal func([]byte) (poolItem, error)
	onErr     func(err error)
}

func NewPool(name string, cli *redis.Client, unmarshal func([]byte) (poolItem, error), onErr func(err error)) *Pool {
	return &Pool{
		name:   name,
		cli:    cli,
		locker: redislock.New(cli),
		lastID: "0",

		val: map[string]interface{}{},

		unmarshal: unmarshal,
		onErr:     onErr,
	}
}

func (p *Pool) listen(ctx context.Context) {
	select {
	case <-ctx.Done():
		return

	default:
		streams, err := p.cli.XRead(ctx, &redis.XReadArgs{
			Streams: []string{p.name, p.lastID},
			Block:   0,
		}).Result()
		if err != nil {
			p.onErr(err)
		}

		for _, s := range streams {
			if s.Stream == p.name {
				for _, msg := range s.Messages {
					val, ok := msg.Values[msgKeyData]
					if !ok {
						p.onErr(errors.New("message with no data"))

					} else {
						b := []byte(val.(string))

						if val, ok := msg.Values[msgKeyAction]; !ok {
							p.onErr(errors.New("message with no action"))

						} else {
							item, err := p.unmarshal(b)
							if err != nil {
								p.onErr(fmt.Errorf("unmarshal '%s' pool item: %w", p.name, err))

							} else {
								i, err := strconv.Atoi(val.(string))
								if err != nil {
									p.onErr(fmt.Errorf("unknown pool action: %s", val.(string)))
								}

								switch PoolAction(i) {
								case PoolActionSet:
									p.set(item)

								case PoolActionDelete:
									p.del(item)

								default:
									p.onErr(fmt.Errorf("unknown pool action: %d", i))
								}
							}
						}
					}

					p.mu.Lock()
					p.lastID = msg.ID
					p.mu.Unlock()
				}
			}
		}
	}
}

func (p *Pool) ensureLatestData() (*redislock.Lock, error) {
	lock, err := p.locker.Obtain(p.name+"_lock", 100*time.Millisecond, &redislock.Options{})
	if err != nil {
		return nil, fmt.Errorf("obtain '%s' stream lock: %w", p.name, err)
	}

	lastID, err := p.cli.Get(context.Background(), p.name+"_lastID").Result()
	if err != nil {
		return nil, fmt.Errorf("get '%s' stream last message ID: %w", p.name, err)
	}

	tc := time.NewTimer(100 * time.Millisecond)
	for {
		select {
		case <-tc.C:
			return nil, errors.New("ensure latest pool data: timeout")

		default:
			p.mu.Lock()

			if p.lastID >= lastID {
				return lock, nil
			}

			p.mu.Unlock()
		}
	}
}

func (p *Pool) set(item poolItem) {
	p.mu.Lock()
	defer p.mu.Unlock()

	p.val[item.ID()] = item
}

func (p *Pool) del(item poolItem) {
	p.mu.Lock()
	defer p.mu.Unlock()

	delete(p.val, item.ID())
}

func (p *Pool) SendMsg(ctx context.Context, action PoolAction, b []byte) error {
	id, err := p.cli.XAdd(ctx, &redis.XAddArgs{
		Stream: p.name,
		Values: map[string]interface{}{
			msgKeyAction: action,
			msgKeyData:   b,
		},
	}).Result()
	if err != nil {
		return fmt.Errorf("send '%s' stream message: %w", p.name, err)
	}

	if p.cli.Set(ctx, p.name+"_lastID", id, 0).Err(); err != nil {
		return fmt.Errorf("update '%s' stream last message ID: %w", p.name, err)
	}

	return nil
}

func (p *Pool) Get(id string) (interface{}, error) {
	lock, err := p.ensureLatestData()
	if err != nil {
		return nil, err
	}
	defer lock.Release()

	p.mu.Lock()
	defer p.mu.Unlock()

	val, ok := p.val[id]
	if !ok {
		return nil, ErrValueNotFound
	}

	return val, nil
}

func (p *Pool) List() ([]interface{}, error) {
	lock, err := p.ensureLatestData()
	if err != nil {
		return nil, err
	}
	defer lock.Release()

	p.mu.Lock()
	defer p.mu.Unlock()

	val := []interface{}{}
	for _, v := range p.val {
		val = append(val, v)
	}

	return val, nil
}
