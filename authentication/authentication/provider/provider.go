package provider

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/authentication/model"

	"github.com/golang-jwt/jwt"
)

const (
	TokenArgsKey       = "token"
	ProviderArgsKey    = "provider"
	CategoryIDArgsKey  = "category_id"
	RequestBodyArgsKey = "request_body"
)

var ErrInvalidCredentials = errors.New("invalid credentials")

type CallbackClaims struct {
	*jwt.StandardClaims
	Provider   string `json:"provider"`
	CategoryID string `json:"category_id"`
	Redirect   string `json:"redirect"`
}

type Provider interface {
	Login(ctx context.Context, categoryID string, args map[string]string) (u *model.User, redirect string, err error)
	Callback(ctx context.Context, claims *CallbackClaims, args map[string]string) (u *model.User, redirect string, err error)
	String() string
}

var ErrUnknownIDP = errors.New("unknown identity provider")
var errInvalidIDP = errors.New("invalid identity provider for this operation")

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
