package limits

import (
	"strings"
	"testing"
	"time"

	"github.com/jellydator/ttlcache/v3"
	"github.com/stretchr/testify/assert"
)

func TestIsRateLimited(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		Username     string
		CategoryID   string
		Provider     string
		PrepareCache func(*ttlcache.Cache[rateLimitedKey, rateLimitedValue])
		ExpectedErr  string
	}{
		"should not return an error if the user hasn't failed an attempt": {
			Username:   "néfix",
			CategoryID: "default",
			Provider:   "form",
		},
		"should not return an error if the user has no active rate": {
			Username:   "néfix",
			CategoryID: "default",
			Provider:   "form",
			PrepareCache: func(cache *ttlcache.Cache[rateLimitedKey, rateLimitedValue]) {
				cache.Set(rateLimitedKey{
					Username:   "néfix",
					CategoryID: "default",
					Provider:   "form",
				}, rateLimitedValue{
					Attempts:   999,
					RetryAfter: time.Now().Add(-1 * time.Hour),
				}, ttlcache.NoTTL)
			},
		},
		"should return an error if there's an active rate limit on the user": {
			Username:   "néfix",
			CategoryID: "default",
			Provider:   "form",
			PrepareCache: func(cache *ttlcache.Cache[rateLimitedKey, rateLimitedValue]) {
				cache.Set(rateLimitedKey{
					Username:   "néfix",
					CategoryID: "default",
					Provider:   "form",
				}, rateLimitedValue{
					Attempts:   999,
					RetryAfter: time.Now().Add(1 * time.Hour),
				}, ttlcache.NoTTL)
			},
			ExpectedErr: "you have been rate limited, try again at '",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			l := NewLimits(10, 1*time.Minute, 2)

			if tc.PrepareCache != nil {
				tc.PrepareCache(l.cache)
			}

			err := l.IsRateLimited(tc.Username, tc.CategoryID, tc.Provider)

			if tc.ExpectedErr != "" {
				assert.True(strings.HasPrefix(err.Error(), tc.ExpectedErr))
			} else {
				assert.NoError(err)
			}
		})
	}
}

func TestRecordFailedAttempt(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		Username         string
		CategoryID       string
		Provider         string
		PrepareCache     func(*ttlcache.Cache[rateLimitedKey, rateLimitedValue])
		ExpectedErr      string
		ExpectedAttempts int
		CheckRetryTime   func(time.Time)
	}{
		"shouldn't return an error if it's the first failed attempt": {
			Username:         "néfix",
			CategoryID:       "default",
			Provider:         "form",
			ExpectedAttempts: 1,
		},
		"shouldn't return an error and increase the attempts counter if there have been less than 10 attempts": {
			Username:   "néfix",
			CategoryID: "default",
			Provider:   "form",
			PrepareCache: func(cache *ttlcache.Cache[rateLimitedKey, rateLimitedValue]) {
				cache.Set(rateLimitedKey{
					Username:   "néfix",
					CategoryID: "default",
					Provider:   "form",
				}, rateLimitedValue{
					Attempts: 8,
				}, ttlcache.NoTTL)
			},
			ExpectedAttempts: 9,
		},
		"should return the current retry time if is currently active": {
			Username:   "néfix",
			CategoryID: "default",
			Provider:   "form",
			PrepareCache: func(cache *ttlcache.Cache[rateLimitedKey, rateLimitedValue]) {
				cache.Set(rateLimitedKey{
					Username:   "néfix",
					CategoryID: "default",
					Provider:   "form",
				}, rateLimitedValue{
					Attempts:   999,
					RetryAfter: time.Now().Add(1 * time.Hour),
				}, ttlcache.NoTTL)
			},
			ExpectedErr:      "you have been rate limited, try again at '",
			ExpectedAttempts: 1000,
			CheckRetryTime: func(t time.Time) {
				assert.True(t.After(time.Now().Add(59 * time.Minute)))
			},
		},
		"should set a new retry time if the current has already expired": {
			Username:   "néfix",
			CategoryID: "default",
			Provider:   "form",
			PrepareCache: func(cache *ttlcache.Cache[rateLimitedKey, rateLimitedValue]) {
				cache.Set(rateLimitedKey{
					Username:   "néfix",
					CategoryID: "default",
					Provider:   "form",
				}, rateLimitedValue{
					Attempts:   999,
					RetryAfter: time.Now().Add(-1 * time.Hour),
				}, ttlcache.NoTTL)
			},
			ExpectedErr:      "you have been rate limited, try again at '",
			ExpectedAttempts: 1000,
			CheckRetryTime: func(t time.Time) {
				assert.True(t.After(time.Now().Add(990 * time.Minute * 990).Add(-1 * time.Second)))
				assert.False(t.After(time.Now().Add(990 * time.Minute * 990)))
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			l := NewLimits(10, 1*time.Minute, 2)

			if tc.PrepareCache != nil {
				tc.PrepareCache(l.cache)
			}

			err := l.RecordFailedAttempt(tc.Username, tc.CategoryID, tc.Provider)

			if tc.ExpectedErr != "" {
				assert.True(strings.HasPrefix(err.Error(), tc.ExpectedErr))
			} else {
				assert.NoError(err)
			}

			entry := l.cache.Get(rateLimitedKey{
				Username:   tc.Username,
				CategoryID: tc.CategoryID,
				Provider:   tc.Provider,
			})

			val := entry.Value()
			assert.Equal(tc.ExpectedAttempts, val.Attempts)
			if tc.CheckRetryTime != nil {
				tc.CheckRetryTime(val.RetryAfter)
			}
		})
	}
}
