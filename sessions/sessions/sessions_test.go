package sessions_test

import (
	"context"
	"encoding/json"
	"errors"
	"os"
	"strings"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/sessions/cfg"
	"gitlab.com/isard/isardvdi/sessions/model"
	"gitlab.com/isard/isardvdi/sessions/sessions"

	"github.com/go-redis/redismock/v9"
	"github.com/google/uuid"
	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestNew(t *testing.T) {
	assert := assert.New(t)

	now := time.Now()

	cases := map[string]struct {
		PrepareRedis func(redismock.ClientMock)
		UserID       string
		CheckSession func(*model.Session)
		ExpectedErr  string
	}{
		"should work as expected": {
			PrepareRedis: func(m redismock.ClientMock) {
				m.CustomMatch(func(expected, actual []interface{}) error {
					assert.Equal(len(expected), len(actual))

					// SET operation
					assert.Equal(expected[0], actual[0])

					// key -> session:XXXXX actual prefix expected
					assert.True(strings.HasPrefix(actual[1].(string), expected[1].(string)))
					uuid, err := uuid.Parse(strings.TrimPrefix(actual[1].(string), expected[1].(string)))
					assert.NoError(err)

					// session
					b := actual[2].([]byte)
					sess := &model.Session{}
					err = json.Unmarshal(b, sess)
					assert.NoError(err)

					assert.Equal(uuid.String(), sess.ID)

					assert.True(sess.Time.MaxTime.Before(now.Add(8*time.Hour + 1*time.Minute)))
					assert.True(sess.Time.MaxTime.After(now.Add(7*time.Hour + 59*time.Minute)))

					assert.True(sess.Time.MaxRenewTime.Before(now.Add(31 * time.Minute)))
					assert.True(sess.Time.MaxRenewTime.After(now.Add(29 * time.Minute)))

					assert.True(sess.Time.ExpirationTime.Before(now.Add(6 * time.Minute)))
					assert.True(sess.Time.ExpirationTime.After(now.Add(4 * time.Minute)))

					// duration
					assert.Equal(expected[4].(int64), actual[4].(int64))

					return nil
				}).ExpectSet(`session:`, nil, time.Until(time.Now().Add(8*time.Hour))).SetVal("OK")
			},
			CheckSession: func(sess *model.Session) {
				_, err := uuid.Parse(sess.ID)
				assert.NoError(err)

				assert.True(sess.Time.MaxTime.Before(now.Add(8*time.Hour + 1*time.Minute)))
				assert.True(sess.Time.MaxTime.After(now.Add(7*time.Hour + 59*time.Minute)))

				assert.True(sess.Time.MaxRenewTime.Before(now.Add(31 * time.Minute)))
				assert.True(sess.Time.MaxRenewTime.After(now.Add(29 * time.Minute)))

				assert.True(sess.Time.ExpirationTime.Before(now.Add(6 * time.Minute)))
				assert.True(sess.Time.ExpirationTime.After(now.Add(4 * time.Minute)))
			},
		},
		"should return an error if there's an error setting the new session in redis": {
			PrepareRedis: func(m redismock.ClientMock) {
				m.CustomMatch(func(expected, actual []interface{}) error {
					assert.Equal(len(expected), len(actual))

					// SET operation
					assert.Equal(expected[0], actual[0])

					// key -> session:XXXXX actual prefix expected
					assert.True(strings.HasPrefix(actual[1].(string), expected[1].(string)))
					uuid, err := uuid.Parse(strings.TrimPrefix(actual[1].(string), expected[1].(string)))
					assert.NoError(err)

					// session
					b := actual[2].([]byte)
					sess := &model.Session{}
					err = json.Unmarshal(b, sess)
					assert.NoError(err)

					assert.Equal(uuid.String(), sess.ID)

					assert.True(sess.Time.MaxTime.Before(now.Add(8*time.Hour + 1*time.Minute)))
					assert.True(sess.Time.MaxTime.After(now.Add(7*time.Hour + 59*time.Minute)))

					assert.True(sess.Time.MaxRenewTime.Before(now.Add(31 * time.Minute)))
					assert.True(sess.Time.MaxRenewTime.After(now.Add(29 * time.Minute)))

					assert.True(sess.Time.ExpirationTime.Before(now.Add(6 * time.Minute)))
					assert.True(sess.Time.ExpirationTime.After(now.Add(4 * time.Minute)))

					// duration
					assert.Equal(expected[4].(int64), actual[4].(int64))

					return nil
				}).ExpectSet(`session:`, nil, time.Until(time.Now().Add(8*time.Hour))).SetErr(errors.New("i'm really tired :("))
			},
			ExpectedErr: "create new session: save session: update session: i'm really tired :(",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ctx := context.Background()
			log := zerolog.New(os.Stdout)
			cfg := cfg.New()

			redis, redisMock := redismock.NewClientMock()
			tc.PrepareRedis(redisMock)

			s := sessions.Init(ctx, &log, cfg.Sessions, redis)

			sess, err := s.New(ctx, tc.UserID)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.CheckSession == nil {
				assert.Nil(sess)
			} else {
				tc.CheckSession(sess)
			}

			assert.NoError(redisMock.ExpectationsWereMet())
		})
	}
}

func TestRenew(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	now := time.Now()

	cases := map[string]struct {
		PrepareRedis func(redismock.ClientMock)
		SessionID    string
		ExpectedTime *model.SessionTime
		ExpectedErr  string
	}{
		"should return an error if the session has reached its max time": {
			PrepareRedis: func(m redismock.ClientMock) {
				sess := &model.Session{
					ID: "hola Melina :)",
					Time: &model.SessionTime{
						MaxTime:        now.Add(-5 * time.Minute),
						MaxRenewTime:   now.Add(30 * time.Second),
						ExpirationTime: now.Add(-5 * time.Minute),
					},
				}

				b, err := json.Marshal(sess)
				require.NoError(err)

				m.ExpectGet("session:hola Melina :)").SetVal(string(b))
			},
			SessionID:   "hola Melina :)",
			ExpectedErr: sessions.ErrMaxSessionTime.Error(),
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ctx := context.Background()
			log := zerolog.New(os.Stdout)
			cfg := cfg.New()

			redis, redisMock := redismock.NewClientMock()
			tc.PrepareRedis(redisMock)

			s := sessions.Init(ctx, &log, cfg.Sessions, redis)

			sessTime, err := s.Renew(ctx, tc.SessionID)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedTime, sessTime)

			assert.NoError(redisMock.ExpectationsWereMet())
		})
	}
}

func TestRevoke(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareRedis func(redismock.ClientMock)
		SessionID    string
		ExpectedErr  string
	}{
		"should work as expected": {
			PrepareRedis: func(m redismock.ClientMock) {
				v := map[string]interface{}{
					"session": &model.Session{
						ID: "hola Pau :)",
					},
				}

				b, err := json.Marshal(v)
				require.NoError(err)

				m.ExpectGet("session:hola Pau :)").SetVal(string(b))
				m.ExpectDel("session:hola Pau :)").SetVal(1)
			},
			SessionID: "hola Pau :)",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ctx := context.Background()
			log := zerolog.New(os.Stdout)
			cfg := cfg.New()

			redis, redisMock := redismock.NewClientMock()
			tc.PrepareRedis(redisMock)

			s := sessions.Init(ctx, &log, cfg.Sessions, redis)

			err := s.Revoke(ctx, tc.SessionID)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.NoError(redisMock.ExpectationsWereMet())
		})
	}
}
