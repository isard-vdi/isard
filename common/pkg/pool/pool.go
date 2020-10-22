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
	"github.com/qmuntal/stateless"
)

var ErrValueNotFound = errors.New("value not found in the pool")

type ctxKey int

const (
	poolStateCtxKey ctxKey = iota
)

const (
	msgKeyAction = "action"
	msgKeyData   = "data"
)

type poolAction int

const (
	poolActionUnknown poolAction = iota
	poolActionSet
	poolActionDelete
)

type poolItem interface {
	GetID() string
	GetState() stateless.State
	SetState(stateless.State)
}

type pool struct {
	name string

	cli    redis.Cmdable
	locker *redislock.Client
	lastID string

	val     map[string]poolItem
	machine *stateless.StateMachine
	mu      sync.Mutex

	marshal   func(item poolItem) ([]byte, error)
	unmarshal func([]byte) (poolItem, error)
	onErr     func(err error)
}

func newPool(name string, cli redis.Cmdable, configureMachine func(*stateless.StateMachine), marshal func(poolItem) ([]byte, error), unmarshal func([]byte) (poolItem, error), onErr func(err error)) *pool {
	p := &pool{
		name:   name,
		cli:    cli,
		locker: redislock.New(cli),
		lastID: "0",

		val: map[string]poolItem{},

		marshal:   marshal,
		unmarshal: unmarshal,
		onErr:     onErr,
	}

	p.machine = stateless.NewStateMachineWithExternalStorage(p.getState, p.setState, stateless.FiringQueued)
	configureMachine(p.machine)

	return p
}

func (p *pool) listen(ctx context.Context) {
	for {
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

									switch poolAction(i) {
									case poolActionSet:
										p.mu.Lock()
										p.val[item.GetID()] = item
										p.mu.Unlock()

									case poolActionDelete:
										p.mu.Lock()
										delete(p.val, item.GetID())
										p.mu.Unlock()

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
}

func (p *pool) ensureLatestData() (*redislock.Lock, error) {
	lock, err := p.locker.Obtain(p.name+"_lock", 100*time.Millisecond, &redislock.Options{})
	if err != nil {
		return nil, fmt.Errorf("obtain '%s' stream lock: %w", p.name, err)
	}

	lastID, err := p.cli.Get(context.Background(), p.name+"_lastID").Result()
	if err != nil {
		if !errors.Is(err, redis.Nil) {
			return nil, fmt.Errorf("get '%s' stream last message ID: %w", p.name, err)
		}
	}

	tc := time.NewTimer(100 * time.Millisecond)
	for {
		select {
		case <-tc.C:
			return nil, errors.New("ensure latest pool data: timeout")

		default:
			p.mu.Lock()

			if p.lastID >= lastID {
				p.mu.Unlock()
				return lock, nil
			}

			p.mu.Unlock()
		}
	}
}

func (p *pool) sendMsg(ctx context.Context, action poolAction, b []byte) error {
	id, err := p.cli.XAdd(ctx, &redis.XAddArgs{
		Stream: p.name,
		Values: map[string]interface{}{
			msgKeyAction: int(action),
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

func (p *pool) get(id string) (interface{}, error) {
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

func (p *pool) set(ctx context.Context, item poolItem) error {
	lock, err := p.ensureLatestData()
	if err != nil {
		return err
	}
	defer lock.Release()

	b, err := p.marshal(item)
	if err != nil {
		return fmt.Errorf("marshal item: %w", err)
	}

	return p.sendMsg(ctx, poolActionSet, b)
}

func (p *pool) list() ([]interface{}, error) {
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

func (p *pool) remove(ctx context.Context, item poolItem) error {
	lock, err := p.ensureLatestData()
	if err != nil {
		return err
	}
	defer lock.Release()

	b, err := p.marshal(item)
	if err != nil {
		return fmt.Errorf("marshal item: %w", err)
	}

	return p.sendMsg(ctx, poolActionDelete, b)
}

func (p *pool) getState(ctx context.Context) (stateless.State, error) {
	id := ctx.Value(poolStateCtxKey).(string)

	p.mu.Lock()
	defer p.mu.Unlock()

	item, ok := p.val[id]
	if !ok {
		return nil, ErrValueNotFound
	}

	return item.GetState(), nil
}

func (p *pool) setState(ctx context.Context, state stateless.State) error {
	id := ctx.Value(poolStateCtxKey).(string)

	p.mu.Lock()
	defer p.mu.Unlock()

	item, ok := p.val[id]
	if !ok {
		return ErrValueNotFound
	}

	item.SetState(state)

	b, err := p.marshal(item)
	if err != nil {
		return fmt.Errorf("marshal pool item: %w", err)
	}

	if err := p.sendMsg(ctx, poolActionSet, b); err != nil {
		return fmt.Errorf("update pool item state in redis: %w", err)
	}

	return nil
}

func (p *pool) fire(item poolItem, trigger stateless.Trigger) error {
	ctx := context.WithValue(context.Background(), poolStateCtxKey, item.GetID())

	return p.machine.FireCtx(ctx, trigger)
}
