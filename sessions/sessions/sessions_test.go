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
		"should return an error if there's an error creating the new user": {
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
				}).ExpectSet(`user:`, nil, time.Until(time.Now().Add(8*time.Hour))).SetErr(errors.New("randomn't error"))
			},
			UserID:      "7005e5a3-6eba-4247-a771-2a2d575cf349",
			RemoteAddr:  "127.0.0.1",
			ExpectedErr: "create new user: save user: update: randomn't error",
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

func TestGet(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	now := time.Now()

	cases := map[string]struct {
		PrepareRedis func(redismock.ClientMock)
		SessionID    string
		RemoteAddr   string
		CheckSession func(*model.Session)
		ExpectedErr  string
	}{
		"should return an error if the session has expired": {
			PrepareRedis: func(m redismock.ClientMock) {
				sess := &model.Session{
					ID:         "79d4df90-fd30-46b6-b439-70b70f335dbe",
					RemoteAddr: "127.0.0.1",
					Time: &model.SessionTime{
						MaxTime:        now.Add(-5 * time.Minute),
						MaxRenewTime:   now.Add(30 * time.Second),
						ExpirationTime: now.Add(-5 * time.Minute),
					},
				}

				b, err := json.Marshal(sess)
				require.NoError(err)

				m.ExpectGet("session:79d4df90-fd30-46b6-b439-70b70f335dbe").SetVal(string(b))
			},
			SessionID:   "79d4df90-fd30-46b6-b439-70b70f335dbe",
			RemoteAddr:  "127.0.0.1",
			ExpectedErr: sessions.ErrSessionExpired.Error(),
		},
		"should return the session if the session is still valid": {
			PrepareRedis: func(m redismock.ClientMock) {
				sess := &model.Session{
					ID:         "79d4df90-fd30-46b6-b439-70b70f335dbe",
					RemoteAddr: "127.0.0.1",
					Time: &model.SessionTime{
						MaxTime:        now.Add(8 * time.Hour),
						MaxRenewTime:   now.Add(30 * time.Minute),
						ExpirationTime: now.Add(5 * time.Minute),
					},
				}

				b, err := json.Marshal(sess)
				require.NoError(err)

				m.ExpectGet("session:79d4df90-fd30-46b6-b439-70b70f335dbe").SetVal(string(b))
			},
			SessionID:  "79d4df90-fd30-46b6-b439-70b70f335dbe",
			RemoteAddr: "127.0.0.1",
			CheckSession: func(sess *model.Session) {
				assert.Equal("79d4df90-fd30-46b6-b439-70b70f335dbe", sess.ID)

				assert.True(sess.Time.MaxTime.Before(now.Add(8*time.Hour + 1*time.Minute)))
				assert.True(sess.Time.MaxTime.After(now.Add(7*time.Hour + 59*time.Minute)))

				assert.True(sess.Time.MaxRenewTime.Before(now.Add(30*time.Minute + 1*time.Minute)))
				assert.True(sess.Time.MaxRenewTime.After(now.Add(30*time.Minute - 1*time.Minute)))

				assert.True(sess.Time.ExpirationTime.Before(now.Add(5*time.Minute + 1*time.Minute)))
				assert.True(sess.Time.ExpirationTime.After(now.Add(5*time.Minute - 1*time.Minute)))
			},
		},
		"should return a session if id is isardvdi-service": {
			PrepareRedis: func(m redismock.ClientMock) {},
			SessionID:    "isardvdi-service",
			CheckSession: func(sess *model.Session) {
				assert.Equal("isardvdi-service", sess.ID)

				assert.True(sess.Time.MaxTime.Before(now.Add(21 * time.Second)))
				assert.True(sess.Time.MaxTime.After(now.Add(19 * time.Second)))

				assert.True(sess.Time.MaxRenewTime.Before(now.Add(21 * time.Second)))
				assert.True(sess.Time.MaxRenewTime.After(now.Add(19 * time.Second)))

				assert.True(sess.Time.ExpirationTime.Before(now.Add(21 * time.Second)))
				assert.True(sess.Time.ExpirationTime.After(now.Add(19 * time.Second)))
			},
		},
		"should return an error if the remote address is not the session's remote address": {
			PrepareRedis: func(m redismock.ClientMock) {
				sess := &model.Session{
					ID:         "dQw4w9WgXcQ",
					RemoteAddr: "127.0.0.1",
					Time: &model.SessionTime{
						MaxTime:        now.Add(8 * time.Hour),
						MaxRenewTime:   now.Add(30 * time.Minute),
						ExpirationTime: now.Add(5 * time.Minute),
					},
				}

				b, err := json.Marshal(sess)
				require.NoError(err)

				m.ExpectGet("session:dQw4w9WgXcQ").SetVal(string(b))
			},
			SessionID:   "dQw4w9WgXcQ",
			RemoteAddr:  "1.1.1.1",
			ExpectedErr: sessions.ErrRemoteAddrMismatch.Error(),
		},
		"should return an error if the remote address is not valid": {
			PrepareRedis: func(m redismock.ClientMock) {},
			SessionID:    "SessionID",
			RemoteAddr:   "this is an invalid address :P",
			ExpectedErr:  sessions.ErrInvalidRemoteAddr.Error(),
		},
		"should return an error if there's an error loading the user": {
			PrepareRedis: func(m redismock.ClientMock) {
				sess := &model.Session{
					ID:         "this is an ID",
					RemoteAddr: "127.0.0.1",
					Time: &model.SessionTime{
						MaxTime:        now.Add(8 * time.Hour),
						MaxRenewTime:   now.Add(30 * time.Minute),
						ExpirationTime: now.Add(5 * time.Minute),
					},
				}

				_, err := json.Marshal(sess)
				require.NoError(err)

				m.ExpectGet("session:this is an ID").SetErr(errors.New("random error"))
			},
			SessionID:   "this is an ID",
			RemoteAddr:  "127.0.0.1",
			ExpectedErr: "load session: get: random error",
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
			cfg.Sessions.RemoteAddrControl = true

			redis, redisMock := redismock.NewClientMock()
			tc.PrepareRedis(redisMock)

			s := sessions.Init(ctx, &log, cfg.Sessions, redis)

			sess, err := s.Get(ctx, tc.SessionID, tc.RemoteAddr)

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

func TestGetUserSession(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	now := time.Now()

	cases := map[string]struct {
		PrepareRedis func(redismock.ClientMock)
		UserID       string
		CheckSession func(*model.Session)
		ExpectedErr  string
	}{
		"should return the session if the session is still valid": {
			PrepareRedis: func(m redismock.ClientMock) {
				usr := &model.User{
					ID:        "79d4df90-fd30-46b6-b439-70b70f335dbe",
					SessionID: "c6b064b1-e27c-4482-b2a2-d9133f03b3a1",
				}

				ub, err := json.Marshal(usr)
				require.NoError(err)
				m.ExpectGet("user:79d4df90-fd30-46b6-b439-70b70f335dbe").SetVal(string(ub))

				sess := &model.Session{
					ID:         "c6b064b1-e27c-4482-b2a2-d9133f03b3a1",
					UserID:     "79d4df90-fd30-46b6-b439-70b70f335dbe",
					RemoteAddr: "127.0.0.1",
					Time: &model.SessionTime{
						MaxTime:        now.Add(8 * time.Hour),
						MaxRenewTime:   now.Add(30 * time.Minute),
						ExpirationTime: now.Add(5 * time.Minute),
					},
				}

				sb, err := json.Marshal(sess)
				require.NoError(err)
				m.ExpectGet("session:c6b064b1-e27c-4482-b2a2-d9133f03b3a1").SetVal(string(sb))
			},
			UserID: "79d4df90-fd30-46b6-b439-70b70f335dbe",
			CheckSession: func(sess *model.Session) {
				assert.Equal("79d4df90-fd30-46b6-b439-70b70f335dbe", sess.UserID)
				assert.True(sess.Time.MaxTime.Before(now.Add(8*time.Hour + 1*time.Minute)))
				assert.True(sess.Time.MaxTime.After(now.Add(7*time.Hour + 59*time.Minute)))
				assert.True(sess.Time.MaxRenewTime.Before(now.Add(30*time.Minute + 1*time.Minute)))
				assert.True(sess.Time.MaxRenewTime.After(now.Add(30*time.Minute - 1*time.Minute)))
				assert.True(sess.Time.ExpirationTime.Before(now.Add(5*time.Minute + 1*time.Minute)))
				assert.True(sess.Time.ExpirationTime.After(now.Add(5*time.Minute - 1*time.Minute)))
			},
		},
		"should return an error if the user ID is missing": {
			PrepareRedis: func(m redismock.ClientMock) {},
			UserID:       "",
			ExpectedErr:  sessions.ErrMissingUserID.Error(),
		},
		"should return an error if there's an error loading the user": {
			PrepareRedis: func(m redismock.ClientMock) {
				m.ExpectGet("user:this is an ID").SetErr(errors.New("random error"))
			},
			UserID:      "this is an ID",
			ExpectedErr: "load user: get: random error",
		},
		"should return an error if there's an error loading the session": {
			PrepareRedis: func(m redismock.ClientMock) {
				usr := &model.User{
					ID:        "79d4df90-fd30-46b6-b439-70b70f335dbe",
					SessionID: "c6b064b1-e27c-4482-b2a2-d9133f03b3a1",
				}

				ub, err := json.Marshal(usr)
				require.NoError(err)
				m.ExpectGet("user:79d4df90-fd30-46b6-b439-70b70f335dbe").SetVal(string(ub))

				m.ExpectGet("session:c6b064b1-e27c-4482-b2a2-d9133f03b3a1").SetErr(errors.New("random error"))
			},
			UserID:      "79d4df90-fd30-46b6-b439-70b70f335dbe",
			ExpectedErr: "load session: get: random error",
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
			cfg.Sessions.RemoteAddrControl = true

			redis, redisMock := redismock.NewClientMock()
			tc.PrepareRedis(redisMock)

			s := sessions.Init(ctx, &log, cfg.Sessions, redis)

			sess, err := s.GetUserSession(ctx, tc.UserID)

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
		"should return an error if the session's max renew time has been reached": {
			PrepareRedis: func(m redismock.ClientMock) {
				sess := &model.Session{
					ID:         "hola Néfix :)",
					RemoteAddr: "127.0.0.1",
					Time: &model.SessionTime{
						MaxTime:        now.Add(8 * time.Hour),
						MaxRenewTime:   now.Add(-5 * time.Minute),
						ExpirationTime: now.Add(5 * time.Minute),
					},
				}

				b, err := json.Marshal(sess)
				require.NoError(err)

				m.ExpectGet("session:hola Néfix :)").SetVal(string(b))
			},
			SessionID:   "hola Néfix :)",
			RemoteAddr:  "127.0.0.1",
			ExpectedErr: sessions.ErrRenewTimeExpired.Error(),
		},
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
		"should work as expected": {
			PrepareRedis: func(m redismock.ClientMock) {
				sess := &model.Session{
					ID:         "12345678-90ab-cdef-ghij-klmnopqrstuv",
					RemoteAddr: "127.0.0.1",
					Time: &model.SessionTime{
						MaxTime:        now.Add(8 * time.Hour),
						MaxRenewTime:   now.Add(30 * time.Minute),
						ExpirationTime: now.Add(5 * time.Minute),
					},
				}

				b, err := json.Marshal(sess)
				require.NoError(err)

				m.ExpectGet("session:12345678-90ab-cdef-ghij-klmnopqrstuv").SetVal(string(b))

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

					assert.Equal("12345678-90ab-cdef-ghij-klmnopqrstuv", sess.ID)

					assert.True(sess.Time.MaxTime.Before(now.Add(8*time.Hour + 1*time.Minute)))
					assert.True(sess.Time.MaxTime.After(now.Add(7*time.Hour + 59*time.Minute)))

					assert.True(sess.Time.MaxRenewTime.Before(now.Add(30*time.Minute + 1*time.Minute)))
					assert.True(sess.Time.MaxRenewTime.After(now.Add(30*time.Minute - 1*time.Minute)))

					assert.True(sess.Time.ExpirationTime.Before(now.Add(5*time.Minute + 1*time.Minute)))
					assert.True(sess.Time.ExpirationTime.After(now.Add(5*time.Minute - 1*time.Minute)))

					// duration
					assert.Equal(expected[4].(int64), actual[4].(int64))

					return nil
				}).ExpectSet(`session:`, nil, time.Until(now.Add(8*time.Hour))).SetVal("OK")

			},
			SessionID:  "12345678-90ab-cdef-ghij-klmnopqrstuv",
			RemoteAddr: "127.0.0.1",
			CheckTime: func(sessTime *model.SessionTime) {
				assert.True(sessTime.MaxTime.Before(now.Add(8*time.Hour + 1*time.Minute)))
				assert.True(sessTime.MaxTime.After(now.Add(7*time.Hour + 59*time.Minute)))

				assert.True(sessTime.MaxRenewTime.Before(now.Add(30*time.Minute + 1*time.Minute)))
				assert.True(sessTime.MaxRenewTime.After(now.Add(30*time.Minute - 1*time.Minute)))

				assert.True(sessTime.ExpirationTime.Before(now.Add(5*time.Minute + 1*time.Minute)))
				assert.True(sessTime.ExpirationTime.After(now.Add(5*time.Minute - 1*time.Minute)))
			},
		},
		"should return an error if the remote address is not valid": {
			PrepareRedis: func(m redismock.ClientMock) {},
			SessionID:    "SessionID",
			RemoteAddr:   "this is an invalid address :P",
			ExpectedErr:  sessions.ErrInvalidRemoteAddr.Error(),
		},
		"should return an error if the remote address is not the session's remote address": {
			PrepareRedis: func(m redismock.ClientMock) {
				sess := &model.Session{
					ID:         "←←←←→→→→",
					RemoteAddr: "127.0.0.1",
					Time: &model.SessionTime{
						MaxTime:        now.Add(8 * time.Hour),
						MaxRenewTime:   now.Add(30 * time.Minute),
						ExpirationTime: now.Add(5 * time.Minute),
					},
				}

				b, err := json.Marshal(sess)
				require.NoError(err)

				m.ExpectGet("session:←←←←→→→→").SetVal(string(b))
			},
			SessionID:   "←←←←→→→→",
			RemoteAddr:  "1.1.1.1",
			ExpectedErr: sessions.ErrRemoteAddrMismatch.Error(),
		},
		"should return an error if there's an error loading the user": {
			PrepareRedis: func(m redismock.ClientMock) {
				sess := &model.Session{
					ID:         "this is an ID",
					RemoteAddr: "127.0.0.1",
					Time: &model.SessionTime{
						MaxTime:        now.Add(8 * time.Hour),
						MaxRenewTime:   now.Add(30 * time.Minute),
						ExpirationTime: now.Add(5 * time.Minute),
					},
				}

				_, err := json.Marshal(sess)
				require.NoError(err)

				m.ExpectGet("session:this is an ID").SetErr(errors.New("random error"))
			},
			SessionID:   "this is an ID",
			RemoteAddr:  "127.0.0.1",
			ExpectedErr: "load session: get: random error",
		},
		"should return an error if there's an error setting the new session in redis": {
			PrepareRedis: func(m redismock.ClientMock) {
				sess := &model.Session{
					ID:         "ID",
					RemoteAddr: "127.0.0.1",
					Time: &model.SessionTime{
						MaxTime:        now.Add(8 * time.Hour),
						MaxRenewTime:   now.Add(30 * time.Minute),
						ExpirationTime: now.Add(5 * time.Minute),
					},
				}

				b, err := json.Marshal(sess)
				require.NoError(err)

				m.ExpectGet("session:ID").SetVal(string(b))

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

					assert.Equal("ID", sess.ID)

					assert.True(sess.Time.MaxTime.Before(now.Add(8*time.Hour + 1*time.Minute)))
					assert.True(sess.Time.MaxTime.After(now.Add(7*time.Hour + 59*time.Minute)))

					assert.True(sess.Time.MaxRenewTime.Before(now.Add(30*time.Minute + 1*time.Minute)))
					assert.True(sess.Time.MaxRenewTime.After(now.Add(30*time.Minute - 1*time.Minute)))

					assert.True(sess.Time.ExpirationTime.Before(now.Add(5*time.Minute + 1*time.Minute)))
					assert.True(sess.Time.ExpirationTime.After(now.Add(5*time.Minute - 1*time.Minute)))

					// duration
					assert.Equal(expected[4].(int64), actual[4].(int64))

					return nil
				}).ExpectSet("session:ID", nil, time.Until(now.Add(8*time.Hour))).SetErr(errors.New("i'm really tired :("))
			},
			SessionID:   "ID",
			RemoteAddr:  "127.0.0.1",
			ExpectedErr: "update the renewed session: update: i'm really tired :(",
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
			cfg.Sessions.RemoteAddrControl = true

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
		"should return an error if there is an error deleting the session": {
			PrepareRedis: func(m redismock.ClientMock) {
				s := &model.Session{
					ID:     "hola Néfix :)",
					UserID: "Néfix",
				}

				b, err := json.Marshal(s)
				require.NoError(err)

				m.ExpectGet("session:hola Néfix :)").SetVal(string(b))
				m.ExpectDel("session:hola Néfix :)").SetErr(errors.New("i'm really tired :("))
			},
			SessionID:   "hola Néfix :)",
			ExpectedErr: "delete session: delete: i'm really tired :(",
		},
		"should return an error if there is an error getting the user": {
			PrepareRedis: func(m redismock.ClientMock) {
				s := &model.Session{
					ID:     "hola Melina :)",
					UserID: "Melina",
				}

				b, err := json.Marshal(s)
				require.NoError(err)

				m.ExpectGet("session:hola Melina :)").SetVal(string(b))
				m.ExpectDel("session:hola Melina :)").SetVal(1)
				m.ExpectGet("user:Melina").SetErr(errors.New("i'm really tired :("))
			},
			SessionID:   "hola Melina :)",
			ExpectedErr: "load user: get: i'm really tired :(",
		},
		"should return an error if there is an error deleting the user": {
			PrepareRedis: func(m redismock.ClientMock) {
				s := &model.Session{
					ID:     "79d4df90-fd30-46b6-b439-70b70f335dbe",
					UserID: "79d4df90",
				}

				b, err := json.Marshal(s)
				require.NoError(err)

				m.ExpectGet("session:79d4df90-fd30-46b6-b439-70b70f335dbe").SetVal(string(b))
				m.ExpectDel("session:79d4df90-fd30-46b6-b439-70b70f335dbe").SetVal(1)
				u := map[string]interface{}{
					"user": &model.User{
						ID:        "79d4df90",
						SessionID: "79d4df90-fd30-46b6-b439-70b70f335dbe",
					},
				}

				ub, err := json.Marshal(u)
				require.NoError(err)
				m.ExpectGet("user:79d4df90").SetVal(string(ub))
				m.ExpectDel("user:79d4df90").SetErr(errors.New("i'm really tired :("))
			},
			SessionID:   "79d4df90-fd30-46b6-b439-70b70f335dbe",
			ExpectedErr: "delete user: delete: i'm really tired :(",
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
