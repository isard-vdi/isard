package limits

import (
	"fmt"
	"math"
	"time"

	"github.com/jellydator/ttlcache/v3"
)

type Limits struct {
	// TODO: Should this be stored in redis instead of locally?
	cache           *ttlcache.Cache[rateLimitedKey, rateLimitedValue]
	maxAttempts     int
	retryAfter      time.Duration
	incrementFactor int
	maxTime         time.Duration
}

func NewLimits(maxAttempts int, retryAfter time.Duration, incrementFactor int, maxTime time.Duration) *Limits {
	cache := ttlcache.New[rateLimitedKey, rateLimitedValue](
		ttlcache.WithTTL[rateLimitedKey, rateLimitedValue](maxTime),
	)

	go cache.Start()

	return &Limits{
		cache:           cache,
		maxAttempts:     maxAttempts,
		retryAfter:      retryAfter,
		incrementFactor: incrementFactor,
		maxTime:         maxTime,
	}
}

type rateLimitedKey struct {
	Username   string
	CategoryID string
	Provider   string
}

type rateLimitedValue struct {
	Attempts   int
	RetryAfter time.Time
}

// IsRateLimited returns an error of type ErrRateLimited if the user is currently rate limited
func (l *Limits) IsRateLimited(username, categoryID string, provider string) error {
	key := rateLimitedKey{
		Username:   username,
		CategoryID: categoryID,
		Provider:   provider,
	}

	limit := l.cache.Get(key)

	// If the user is not in the cache, it's not rate limited
	if limit == nil {
		return nil
	}

	val := limit.Value()

	// If the retry after has already arrived, we can let the user try again
	if val.RetryAfter.Before(time.Now()) {
		return nil
	}

	// Otherwise, return the time when the user can try again
	return &RateLimitError{
		username:   username,
		categoryID: categoryID,
		provider:   provider,

		RetryAfter: val.RetryAfter,
	}
}

// ReordFailedAttempt increases by 1 the failed attempts. If there's an active rate
// limit, it returns an ErrRateLimited error
func (l *Limits) RecordFailedAttempt(username, categoryID string, provider string) error {
	key := rateLimitedKey{
		Username:   username,
		CategoryID: categoryID,
		Provider:   provider,
	}

	limit := l.cache.Get(key)

	// If there's no limit, record the attempt
	if limit == nil {
		l.cache.Set(key, rateLimitedValue{
			Attempts: 1,
		}, ttlcache.NoTTL)

		return nil
	}

	// Increase the attempts number
	val := limit.Value()
	val.Attempts += 1

	// Ensure the cache gets updated
	// Not sure why, without the defer being in a separate function, the value doesn't get always set
	defer func() {
		l.cache.Set(key, val, ttlcache.NoTTL)
	}()

	// If the failed attempts are less than the limit, don't do anything
	if limit.Value().Attempts < l.maxAttempts {
		return nil
	}

	// Check if the retry time has already arrived
	if val.RetryAfter.Before(time.Now()) {
		// Here we calculate the exponential backoff (nth attempt after max attempts ^ increment factor)
		duration := (time.Duration(
			math.Round(math.Pow(
				float64(val.Attempts-l.maxAttempts),
				float64(l.incrementFactor),
			)),

		// And we use the backoff value against the default ban duration
		) * l.retryAfter)

		// If the duration exceeds the max time, set the max time as the rate limiting duration
		if duration > l.maxTime {
			duration = l.maxTime
		}

		// Set the configured timeout
		val.RetryAfter = time.Now().Add(duration)
	}

	return &RateLimitError{
		username:   username,
		categoryID: categoryID,
		provider:   provider,

		RetryAfter: val.RetryAfter,
	}
}

// CleanRateLimit resets the rate limit count for a user
func (l *Limits) CleanRateLimit(username, categoryID string, provider string) {
	key := rateLimitedKey{
		Username:   username,
		CategoryID: categoryID,
		Provider:   provider,
	}

	l.cache.Delete(key)
}

// RateLimitError is an error that gets returned when the user has failed the login
// too much times
type RateLimitError struct {
	username   string
	categoryID string
	provider   string

	RetryAfter time.Time
}

func (e *RateLimitError) Error() string {
	return fmt.Sprintf("you have been rate limited, try again at '%s'", e.RetryAfter.String())
}
