package pool

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"os/exec"
	"strconv"
	"testing"
	"time"

	"github.com/bsm/redislock"
	"github.com/go-redis/redis/v8"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func freePort() (int, error) {
	addr, err := net.ResolveTCPAddr("tcp", "localhost:0")
	if err != nil {
		return 0, err
	}

	l, err := net.ListenTCP("tcp", addr)
	if err != nil {
		return 0, err
	}
	defer l.Close()
	return l.Addr().(*net.TCPAddr).Port, nil
}

func runRedis() (string, context.CancelFunc, error) {
	ctx, cancel := context.WithCancel(context.Background())

	port, err := freePort()
	if err != nil {
		return "", cancel, err
	}

	cmd := exec.CommandContext(ctx, "redis-server", "--port", strconv.Itoa(port))
	if err := cmd.Start(); err != nil {
		return "", cancel, err
	}

	return ":" + strconv.Itoa(port), cancel, nil
}

type testPoolItem struct {
	Test string `json:"test,omitempty"`
}

func (t *testPoolItem) ID() string {
	return "id"
}

func TestEnsureLatestData(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareTest func(cli *redis.Client)
		ExpectedErr string
	}{
		"should work as expected": {
			PrepareTest: func(cli *redis.Client) {
				id, err := cli.XAdd(context.Background(), &redis.XAddArgs{
					Stream: "example",
					Values: map[string]interface{}{
						msgKeyAction: int(poolActionSet),
						msgKeyData:   []byte{},
					},
				}).Result()
				require.NoError(err)

				err = cli.Set(context.Background(), "example_lastID", id, 0).Err()
				require.NoError(err)
			},
		},
		"should return an error if there's an error getting the reids lock": {
			PrepareTest: func(cli *redis.Client) {
				locker := redislock.New(cli)
				_, err := locker.Obtain("example_lock", 200*time.Millisecond, &redislock.Options{})
				require.NoError(err)
			},
			ExpectedErr: "obtain 'example' stream lock: redislock: not obtained",
		},
		"should work if there's no lastID": {},
		"should return an error if it reaches the timeout": {
			PrepareTest: func(cli *redis.Client) {
				err := cli.Set(context.Background(), "example_lastID", "1", 0).Err()
				require.NoError(err)
			},
			ExpectedErr: "ensure latest pool data: timeout",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			addr, redisCancel, err := runRedis()
			require.NoError(err)

			cli := redis.NewClient(&redis.Options{
				Addr: addr,
			})
			defer cli.Close()

			err = cli.Ping(context.Background()).Err()
			require.NoError(err)

			p := newPool("example", cli, func(item poolItem) ([]byte, error) {
				return json.Marshal(item)
			}, func(b []byte) (poolItem, error) {
				i := &testPoolItem{}
				err := json.Unmarshal(b, i)
				return i, err
			}, func(err error) {
				fmt.Println(err)
			})

			ctx, cancel := context.WithCancel(context.Background())
			go p.listen(ctx)

			if tc.PrepareTest != nil {
				tc.PrepareTest(cli)
			}

			lock, err := p.ensureLatestData()

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if lock != nil {
				lock.Release()
			}
			cancel()
			redisCancel()
		})
	}
}

func TestSendMsg(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareTest func(cli *redis.Client)
		ExpectedErr string
	}{
		"should work as expected": {},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			addr, redisCancel, err := runRedis()
			require.NoError(err)

			cli := redis.NewClient(&redis.Options{
				Addr: addr,
			})
			defer cli.Close()

			err = cli.Ping(context.Background()).Err()
			require.NoError(err)

			p := newPool("example", cli, func(item poolItem) ([]byte, error) {
				return json.Marshal(item)
			}, func(b []byte) (poolItem, error) {
				i := &testPoolItem{}
				err := json.Unmarshal(b, i)
				return i, err
			}, func(err error) {
				fmt.Println(err)
			})

			ctx, cancel := context.WithCancel(context.Background())
			go p.listen(ctx)

			if tc.PrepareTest != nil {
				tc.PrepareTest(cli)
			}

			err = p.sendMsg(context.Background(), poolActionSet, []byte{})

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			cancel()
			redisCancel()
		})
	}
}

func TestGet(t *testing.T) {
	require := require.New(t)
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareTest  func(cli *redis.Client)
		ExpectedItem interface{}
		ExpectedErr  string
	}{
		"should work as expected": {
			PrepareTest: func(cli *redis.Client) {
				b, err := json.Marshal(&testPoolItem{Test: "thisisatest"})
				require.NoError(err)

				id, err := cli.XAdd(context.Background(), &redis.XAddArgs{
					Stream: "example",
					Values: map[string]interface{}{
						msgKeyAction: int(poolActionSet),
						msgKeyData:   b,
					},
				}).Result()
				require.NoError(err)

				err = cli.Set(context.Background(), "example_lastID", id, 0).Err()
				require.NoError(err)
			},
			ExpectedItem: &testPoolItem{
				Test: "thisisatest",
			},
		},
		"should return an error if there's an error ensuring the latest data": {
			PrepareTest: func(cli *redis.Client) {
				locker := redislock.New(cli)
				_, err := locker.Obtain("example_lock", 200*time.Millisecond, &redislock.Options{})
				require.NoError(err)
			},
			ExpectedErr: "obtain 'example' stream lock: redislock: not obtained",
		},
		"should return an error if there's no data for the id": {
			ExpectedErr: ErrValueNotFound.Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			addr, redisCancel, err := runRedis()
			require.NoError(err)

			cli := redis.NewClient(&redis.Options{
				Addr: addr,
			})
			defer cli.Close()

			err = cli.Ping(context.Background()).Err()
			require.NoError(err)

			p := newPool("example", cli, func(item poolItem) ([]byte, error) {
				return json.Marshal(item)
			}, func(b []byte) (poolItem, error) {
				i := &testPoolItem{}
				err := json.Unmarshal(b, i)
				return i, err
			}, func(err error) {
				fmt.Println(err)
			})

			ctx, cancel := context.WithCancel(context.Background())
			go p.listen(ctx)

			if tc.PrepareTest != nil {
				tc.PrepareTest(cli)
			}

			item, err := p.get("id")

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedItem, item)

			cancel()
			redisCancel()
		})
	}
}
