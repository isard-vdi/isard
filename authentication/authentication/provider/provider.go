package provider

import (
	"context"
	"errors"
	"regexp"

	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/authentication/model"
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

type Provider interface {
	Login(ctx context.Context, categoryID string, args map[string]string) (g *model.Group, u *model.User, redirect string, err error)
	Callback(ctx context.Context, claims *token.CallbackClaims, args map[string]string) (g *model.Group, u *model.User, redirect string, err error)
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

func (Unknown) Login(context.Context, string, map[string]string) (*model.Group, *model.User, string, error) {
	return nil, nil, "", ErrUnknownIDP
}

func (Unknown) Callback(context.Context, *token.CallbackClaims, map[string]string) (*model.Group, *model.User, string, error) {
	return nil, nil, "", ErrUnknownIDP
}

func (Unknown) AutoRegister() bool {
	return false
}

func matchRegex(re *regexp.Regexp, s string) string {
	result := re.FindStringSubmatch(s)
	// the first submatch is the whole match, the 2nd is the 1st group
	if len(result) > 1 {
		return result[1]
	}

	return re.FindString(s)
}
