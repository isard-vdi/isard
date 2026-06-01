package redis_test

import (
	"context"
	"errors"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/pkg/redis"

	"github.com/go-redis/redismock/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type model struct {
	ID    string `json:"id"`
	Value string `json:"value"`
}

func (m *model) Key() string {
	return m.ID
}

func (m *model) Expiration() time.Duration {
	return time.Until(time.Now())
}

func TestModelLoad(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareMock   func(m redismock.ClientMock)
		Model         *model
		ExpectedModel *model
		ExpectedErr   string
	}{
		"should work as expected": {
			PrepareMock: func(m redismock.ClientMock) {
				m.ExpectGet("hola").SetVal(`{"id": "hola", "value": "Melina"}`)
			},
			Model: &model{
				ID: "hola",
			},
			ExpectedModel: &model{
				ID:    "hola",
				Value: "Melina",
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			cli, mock := redismock.NewClientMock()

			if tc.PrepareMock != nil {
				tc.PrepareMock(mock)
			}

			err := redis.NewModel(tc.Model).Load(context.Background(), cli)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				require.NoError(err)
			}

			assert.Equal(tc.ExpectedModel, tc.Model)
		})
	}
}

func TestModelUpdate(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareMock func(m redismock.ClientMock)
		Model       *model
		ExpectedErr string
	}{
		"should work as expected": {
			PrepareMock: func(m redismock.ClientMock) {
				m.ExpectSet("hola", []byte(`{"id":"hola","value":"Melina"}`), time.Until(time.Now())).SetVal("OK")
			},
			Model: &model{
				ID:    "hola",
				Value: "Melina",
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			cli, mock := redismock.NewClientMock()

			if tc.PrepareMock != nil {
				tc.PrepareMock(mock)
			}

			err := redis.NewModel(tc.Model).Update(context.Background(), cli)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				require.NoError(err)
			}
		})
	}
}

func TestModelLock(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareMock    func(m redismock.ClientMock)
		Opts           redis.LockOptions
		Ctx            func(t *testing.T) (context.Context, context.CancelFunc)
		InvokeRelease  bool
		ExpectedErr    error
		ExpectedErrStr string
	}{
		"should acquire when free": {
			PrepareMock: func(m redismock.ClientMock) {
				m.ExpectSetNX("lock:hola", "", 5*time.Second).SetVal(true)
				m.ExpectDel("lock:hola").SetVal(1)
			},
			Opts:          redis.DefaultLockOptions,
			InvokeRelease: true,
		},
		"should retry until acquired": {
			PrepareMock: func(m redismock.ClientMock) {
				m.ExpectSetNX("lock:hola", "", 5*time.Second).SetVal(false)
				m.ExpectSetNX("lock:hola", "", 5*time.Second).SetVal(true)
				m.ExpectDel("lock:hola").SetVal(1)
			},
			Opts: redis.LockOptions{
				TTL:        5 * time.Second,
				MaxWait:    time.Second,
				RetryDelay: time.Millisecond,
			},
			InvokeRelease: true,
		},
		"should return ErrLockBusy on timeout": {
			PrepareMock: func(m redismock.ClientMock) {
				m.ExpectSetNX("lock:hola", "", 5*time.Second).SetVal(false)
			},
			Opts: redis.LockOptions{
				TTL:        5 * time.Second,
				MaxWait:    time.Microsecond,
				RetryDelay: time.Millisecond,
			},
			ExpectedErr: redis.ErrLockBusy,
		},
		"should return ctx err on cancel": {
			PrepareMock: func(m redismock.ClientMock) {
				m.ExpectSetNX("lock:hola", "", 5*time.Second).SetVal(false)
			},
			Opts: redis.LockOptions{
				TTL:        5 * time.Second,
				MaxWait:    time.Second,
				RetryDelay: time.Second,
			},
			Ctx: func(t *testing.T) (context.Context, context.CancelFunc) {
				ctx, cancel := context.WithCancel(t.Context())
				time.AfterFunc(5*time.Millisecond, cancel)
				return ctx, cancel
			},
			ExpectedErr: context.Canceled,
		},
		"should propagate redis error on setnx": {
			PrepareMock: func(m redismock.ClientMock) {
				m.ExpectSetNX("lock:hola", "", 5*time.Second).SetErr(errors.New("boom"))
			},
			Opts:           redis.DefaultLockOptions,
			ExpectedErrStr: "acquire lock: boom",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			cli, mock := redismock.NewClientMock()

			if tc.PrepareMock != nil {
				tc.PrepareMock(mock)
			}

			ctx := t.Context()
			if tc.Ctx != nil {
				var cancel context.CancelFunc
				ctx, cancel = tc.Ctx(t)
				defer cancel()
			}

			m := &model{ID: "hola"}
			release, err := redis.NewModel(m).Lock(ctx, cli, tc.Opts)

			switch {
			case tc.ExpectedErr != nil:
				require.Error(err)
				assert.ErrorIs(err, tc.ExpectedErr)
				assert.Nil(release)

			case tc.ExpectedErrStr != "":
				assert.EqualError(err, tc.ExpectedErrStr)
				assert.Nil(release)

			default:
				require.NoError(err)
				require.NotNil(release)
				if tc.InvokeRelease {
					release()
				}
			}

			assert.NoError(mock.ExpectationsWereMet())
		})
	}
}
