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
		RemoteAddr   string
		CheckSession func(*model.Session)
		ExpectedErr  string
	}{
		"should work as expected": {
			PrepareRedis: func(m redismock.ClientMock) {
				var sessionID string

				m.ExpectGet("user:7005e5a3-6eba-4247-a771-2a2d575cf349").RedisNil()
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

					sessionID = sess.ID

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
				m.CustomMatch(func(expected, actual []interface{}) error {
					assert.Equal(len(expected), len(actual))

					// SET operation
					assert.Equal(expected[0], actual[0])

					// key -> user:XXXXX actual prefix expected
					assert.True(strings.HasPrefix(actual[1].(string), expected[1].(string)))
					usrUUID, err := uuid.Parse(strings.TrimPrefix(actual[1].(string), expected[1].(string)))
					assert.NoError(err)

					// session
					b := actual[2].([]byte)
					usr := &model.User{}
					err = json.Unmarshal(b, usr)
					assert.NoError(err)

					assert.Equal(usrUUID.String(), usr.ID)

					sessUUID, err := uuid.Parse(usr.SessionID)
					assert.NoError(err)

					assert.Equal(sessionID, sessUUID.String())

					return nil
				}).ExpectSet(`user:`, nil, time.Until(time.Now().Add(8*time.Hour))).SetVal("OK")
			},
			UserID:     "7005e5a3-6eba-4247-a771-2a2d575cf349",
			RemoteAddr: "127.0.0.1",
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
				m.ExpectGet("user:05837779-35f8-4f17-a4a9-b0540cc0fe81").RedisNil()
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
			UserID:      "05837779-35f8-4f17-a4a9-b0540cc0fe81",
			RemoteAddr:  "127.0.0.1",
			ExpectedErr: "create new session: save session: update: i'm really tired :(",
		},
		"should return an error if the remote address is not valid": {
			PrepareRedis: func(m redismock.ClientMock) {},
			UserID:       "05837779-35f8-4f17-a4a9-b0540cc0fe81",
			RemoteAddr:   "this is an invalid address :P",
			ExpectedErr:  sessions.ErrInvalidRemoteAddr.Error(),
		},
		"should return an error if the user ID is missing": {
			PrepareRedis: func(m redismock.ClientMock) {},
			UserID:       "",
			RemoteAddr:   "127.0.0.1",
			ExpectedErr:  sessions.ErrMissingUserID.Error(),
		},
		"should return revoke the old session and create a new one if the user already has an active session": {
			PrepareRedis: func(m redismock.ClientMock) {
				var sessionID string
				usr := &model.User{
					ID:        "75a52380-7a9f-45b9-814a-3448870ec0a9",
					SessionID: "05837779-35f8-4f17-a4a9-b0540cc0fe81",
				}

				bUsr, err := json.Marshal(usr)
				assert.NoError(err)

				m.ExpectGet("user:" + usr.ID).SetVal(string(bUsr))
				sess := &model.Session{
					ID:         "05837779-35f8-4f17-a4a9-b0540cc0fe81",
					UserID:     "75a52380-7a9f-45b9-814a-3448870ec0a9",
					RemoteAddr: "127.0.0.1",
					Time: &model.SessionTime{
						MaxTime:        now.Add(-5 * time.Minute),
						MaxRenewTime:   now.Add(30 * time.Second),
						ExpirationTime: now.Add(-5 * time.Minute),
					},
				}

				bSess, err := json.Marshal(sess)
				assert.NoError(err)

				m.ExpectGet("session:" + usr.SessionID).SetVal(string(bSess))
				m.ExpectDel("session:" + usr.SessionID).SetVal(1)
				m.ExpectGet("user:" + usr.ID).SetVal(string(bUsr))
				m.ExpectDel("user:" + usr.ID).SetVal(1)

				sess = &model.Session{
					ID:         "89d11dea-6cf5-442f-bf8f-aebf3d0596bd",
					UserID:     "75a52380-7a9f-45b9-814a-3448870ec0a9",
					RemoteAddr: "127.0.0.1",
					Time: &model.SessionTime{
						MaxTime:        now.Add(-5 * time.Minute),
						MaxRenewTime:   now.Add(30 * time.Second),
						ExpirationTime: now.Add(-5 * time.Minute),
					},
				}
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

					sessionID = sess.ID

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
				m.CustomMatch(func(expected, actual []interface{}) error {
					assert.Equal(len(expected), len(actual))

					// SET operation
					assert.Equal(expected[0], actual[0])

					// key -> user:XXXXX actual prefix expected
					assert.True(strings.HasPrefix(actual[1].(string), expected[1].(string)))
					usrUUID, err := uuid.Parse(strings.TrimPrefix(actual[1].(string), expected[1].(string)))
					assert.NoError(err)

					// session
					b := actual[2].([]byte)
					usr := &model.User{}
					err = json.Unmarshal(b, usr)
					assert.NoError(err)

					assert.Equal(usrUUID.String(), usr.ID)

					sessUUID, err := uuid.Parse(usr.SessionID)
					assert.NoError(err)

					assert.Equal(sessionID, sessUUID.String())

					return nil
				}).ExpectSet(`user:`, nil, time.Until(time.Now().Add(8*time.Hour))).SetVal("OK")
			},
			UserID:     "75a52380-7a9f-45b9-814a-3448870ec0a9",
			RemoteAddr: "127.0.0.1",
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
		"should return an error if there's an error loading the user": {
			PrepareRedis: func(m redismock.ClientMock) {
				usr := &model.User{
					ID:        "this is an ID",
					SessionID: "05837779-35f8-4f17-a4a9-b0540cc0fe81",
				}

				_, err := json.Marshal(usr)
				assert.NoError(err)

				m.ExpectGet("user:" + usr.ID).SetErr(errors.New("random error"))
			},
			UserID:      "this is an ID",
			RemoteAddr:  "127.0.0.1",
			ExpectedErr: "load user: get: random error",
		},
		"should return an error if there's an error revoking the old user session": {
			PrepareRedis: func(m redismock.ClientMock) {
				usr := &model.User{
					ID:        "this is an ID",
					SessionID: "05837779-35f8-4f17-a4a9-b0540cc0fe81",
				}

				bUsr, err := json.Marshal(usr)
				assert.NoError(err)

				m.ExpectGet("user:" + usr.ID).SetVal(string(bUsr))
				sess := &model.Session{
					ID:         "05837779-35f8-4f17-a4a9-b0540cc0fe81",
					UserID:     "this is an ID",
					RemoteAddr: "127.0.0.1",
					Time: &model.SessionTime{
						MaxTime:        now.Add(-5 * time.Minute),
						MaxRenewTime:   now.Add(30 * time.Second),
						ExpirationTime: now.Add(-5 * time.Minute),
					},
				}

				_, err = json.Marshal(sess)
				assert.NoError(err)

				m.ExpectGet("session:" + usr.SessionID).SetErr(errors.New("random error"))
			},
			UserID:      "this is an ID",
			RemoteAddr:  "127.0.0.1",
			ExpectedErr: "revoke old user session: load session: get: random error",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ctx := context.Background()
			log := zerolog.New(os.Stdout)
			cfg := cfg.New()
			cfg.Sessions.MaxTime = 8 * time.Hour
			cfg.Sessions.MaxRenewTime = 30 * time.Minute
			cfg.Sessions.ExpirationTime = 5 * time.Minute

			redis, redisMock := redismock.NewClientMock()
			tc.PrepareRedis(redisMock)

			s := sessions.Init(ctx, &log, cfg.Sessions, redis)

			sess, err := s.New(ctx, tc.UserID, tc.RemoteAddr)

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
		RemoteAddr   string
		CheckTime    func(*model.SessionTime)
		ExpectedErr  string
	}{
		"should return an error if the session has reached its max time": {
			PrepareRedis: func(m redismock.ClientMock) {
				sess := &model.Session{
					ID:         "hola Melina :)",
					RemoteAddr: "127.0.0.1",
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
			RemoteAddr:  "127.0.0.1",
			ExpectedErr: sessions.ErrMaxSessionTime.Error(),
		},
		"should set the renew time as the max time if the session has reached its max renew time surpasses its max time": {
			PrepareRedis: func(m redismock.ClientMock) {
				sess := &model.Session{
					ID:         "hola Néfix :)",
					RemoteAddr: "127.0.0.1",
					Time: &model.SessionTime{
						MaxTime:        now.Add(8 * time.Hour),
						MaxRenewTime:   now.Add(7*time.Hour + 45*time.Minute),
						ExpirationTime: now.Add(-15 * time.Minute),
					},
				}

				b, err := json.Marshal(sess)
				require.NoError(err)

				m.ExpectGet("session:hola Néfix :)").SetVal(string(b))

				m.CustomMatch(func(expected, actual []interface{}) error {
					assert.Equal(len(expected), len(actual))

					// SET operation
					assert.Equal(expected[0], actual[0])

					// key -> session:XXXXX actual prefix expected
					assert.True(strings.HasPrefix(actual[1].(string), expected[1].(string)))

					// session
					b := actual[2].([]byte)
					sess := &model.Session{}
					err = json.Unmarshal(b, sess)
					assert.NoError(err)

					assert.Equal("hola Néfix :)", sess.ID)

					assert.True(sess.Time.MaxTime.Before(now.Add(8*time.Hour + 1*time.Minute)))
					assert.True(sess.Time.MaxTime.After(now.Add(7*time.Hour + 59*time.Minute)))

					assert.True(sess.Time.MaxRenewTime.Before(now.Add(8*time.Hour + 1*time.Minute)))
					assert.True(sess.Time.MaxRenewTime.After(now.Add(7*time.Hour + 59*time.Minute)))

					assert.True(sess.Time.ExpirationTime.Before(now.Add(6 * time.Minute)))
					assert.True(sess.Time.ExpirationTime.After(now.Add(4 * time.Minute)))

					// duration
					assert.Equal(expected[4].(int64), actual[4].(int64))

					return nil
				}).ExpectSet(`session:`, nil, time.Until(now.Add(8*time.Hour))).SetVal("OK")
			},
			SessionID:  "hola Néfix :)",
			RemoteAddr: "127.0.0.1",
			CheckTime: func(sessTime *model.SessionTime) {
				assert.True(sessTime.MaxTime.Before(now.Add(8*time.Hour + 1*time.Minute)))
				assert.True(sessTime.MaxTime.After(now.Add(7*time.Hour + 59*time.Minute)))

				assert.True(sessTime.MaxRenewTime.Before(now.Add(8*time.Hour + 1*time.Minute)))
				assert.True(sessTime.MaxRenewTime.After(now.Add(7*time.Hour + 59*time.Minute)))

				assert.True(sessTime.ExpirationTime.Before(now.Add(6 * time.Minute)))
				assert.True(sessTime.ExpirationTime.After(now.Add(4 * time.Minute)))
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ctx := context.Background()
			log := zerolog.New(os.Stdout)
			cfg := cfg.New()
			cfg.Sessions.MaxTime = 8 * time.Hour
			cfg.Sessions.MaxRenewTime = 30 * time.Minute
			cfg.Sessions.ExpirationTime = 5 * time.Minute

			redis, redisMock := redismock.NewClientMock()
			tc.PrepareRedis(redisMock)

			s := sessions.Init(ctx, &log, cfg.Sessions, redis)

			sessTime, err := s.Renew(ctx, tc.SessionID, tc.RemoteAddr)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.CheckTime == nil {
				assert.Nil(sessTime)
			} else {
				tc.CheckTime(sessTime)
			}

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
				s := &model.Session{
					ID:     "hola Pau :)",
					UserID: "Pau",
				}

				b, err := json.Marshal(s)
				require.NoError(err)

				m.ExpectGet("session:hola Pau :)").SetVal(string(b))
				m.ExpectDel("session:hola Pau :)").SetVal(1)
				u := map[string]interface{}{
					"user": &model.User{
						ID:        "Pau",
						SessionID: "hola Pau :)",
					},
				}

				ub, err := json.Marshal(u)
				require.NoError(err)
				m.ExpectGet("user:Pau").SetVal(string(ub))
				m.ExpectDel("user:Pau").SetVal(1)
			},
			SessionID: "hola Pau :)",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ctx := context.Background()
			log := zerolog.New(os.Stdout)
			cfg := cfg.New()
			cfg.Sessions.MaxTime = 8 * time.Hour
			cfg.Sessions.MaxRenewTime = 30 * time.Minute
			cfg.Sessions.ExpirationTime = 5 * time.Minute

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
