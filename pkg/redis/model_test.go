package redis_test

import (
	"context"
	"testing"
	"time"

	"github.com/go-redis/redismock/v9"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"gitlab.com/isard/isardvdi/pkg/redis"
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
