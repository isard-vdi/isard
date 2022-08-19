package provider

import (
	"context"
	"errors"
	"fmt"
	"regexp"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"

	"github.com/golang-jwt/jwt"
)

const (
	TokenArgsKey       = "token"
	ProviderArgsKey    = "provider"
	CategoryIDArgsKey  = "category_id"
	RequestBodyArgsKey = "request_body"
	RedirectArgsKey    = "redirect"
)

var ErrInvalidCredentials = errors.New("invalid credentials")
var ErrUserDisabled = errors.New("disabled user")

type CallbackClaims struct {
	*jwt.StandardClaims
	Provider   string `json:"provider"`
	CategoryID string `json:"category_id"`
	Redirect   string `json:"redirect"`
}

type Provider interface {
	Login(ctx context.Context, categoryID string, args map[string]string) (u *model.User, redirect string, err error)
	Callback(ctx context.Context, claims *CallbackClaims, args map[string]string) (u *model.User, redirect string, err error)
	AutoRegister() bool
	String() string
}

var ErrUnknownIDP = errors.New("unknown identity provider")
var errInvalidIDP = errors.New("invalid identity provider for this operation")

type HTTPRequestType string

const HTTPRequest HTTPRequestType = "req"

const UnknownString = "unknown"

type Unknown struct{}

func (Unknown) String() string {
	return UnknownString
}

func (Unknown) Login(context.Context, string, map[string]string) (*model.User, string, error) {
	return nil, "", ErrUnknownIDP
}

func (Unknown) Callback(context.Context, *CallbackClaims, map[string]string) (*model.User, string, error) {
	return nil, "", ErrUnknownIDP
}

func (Unknown) AutoRegister() bool {
	return false
}

func signCallbackToken(secret, prv, cat, redirect string) (string, error) {
	tkn := jwt.NewWithClaims(jwt.SigningMethodHS256, &CallbackClaims{
		&jwt.StandardClaims{
			Issuer:    "isard-authentication",
			ExpiresAt: time.Now().Add(10 * time.Minute).Unix(),
		},
		prv,
		cat,
		redirect,
	})

	ss, err := tkn.SignedString([]byte(secret))
	if err != nil {
		return "", fmt.Errorf("sign the token: %w", err)
	}

	return ss, nil
}

func matchRegex(re *regexp.Regexp, s string) string {
	result := re.FindStringSubmatch(s)
	// the first submatch is the whole match, the 2nd is the 1st group
	if len(result) > 1 {
		return result[1]
	}

	return re.FindString(s)
}
