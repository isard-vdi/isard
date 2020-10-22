package pool

import (
	"context"
	"testing"

	"github.com/alicebob/miniredis/v2"
	"github.com/go-redis/redis/v8"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type testPoolItem struct{}

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
						msgKeyAction: int(PoolActionSet),
						msgKeyData:   []byte{},
					},
				}).Result()
				require.NoError(err)

				err = cli.Set(context.Background(), "example_lastID", id, 0).Err()
				require.NoError(err)
			},
		},
		// "should return an error if there's an error getting the reids lock": {
		// 	PrepareTest: func(cli *redis.Client) {
		// 		locker := redislock.New(cli)
		// 		_, err := locker.Obtain("example_lock", 200*time.Millisecond, &redislock.Options{})
		// 		require.NoError(err)
		// 	},
		// },
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			s, err := miniredis.Run()
			require.NoError(err)
			defer s.Close()

			cli := redis.NewClient(&redis.Options{
				Addr: s.Addr(),
			})

			err = cli.Ping(context.Background()).Err()
			require.NoError(err)

			p := NewPool("example", cli, func(b []byte) (poolItem, error) {
				return &testPoolItem{}, nil
			}, func(err error) {
				panic(err)
			})

			ctx, cancel := context.WithCancel(context.Background())
			go p.listen(ctx)

			tc.PrepareTest(cli)

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
		})
	}
}
