package provider

import (
	"context"
	"errors"
	"fmt"
	"regexp"

	"gitlab.com/isard/isardvdi/authentication/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/authentication/model"
)

const (
	TokenArgsKey                        = "token"
	ProviderArgsKey                     = "provider"
	CategoryIDArgsKey                   = "category_id"
	RequestBodyArgsKey                  = "request_body"
	RedirectArgsKey                     = "redirect"
	FormUsernameArgsKey                 = "form_username"
	FormPasswordArgsKey                 = "form_password"
	HTTPRequest         HTTPRequestType = "req"
)

type HTTPRequestType string

type Provider interface {
	Login(ctx context.Context, categoryID string, args map[string]string) (g *model.Group, u *model.User, redirect string, err *ProviderError)
	Callback(ctx context.Context, claims *token.CallbackClaims, args map[string]string) (g *model.Group, u *model.User, redirect string, err *ProviderError)
	AutoRegister() bool
	String() string
	Healthcheck() error
}

type ProviderError struct {
	// The error that will be shown to the user
	User error
	// Detail of the error that will be logged in debug
	Detail error
}

func (p *ProviderError) Error() string {
	return fmt.Errorf("%w: %w", p.User, p.Detail).Error()
}

func (p *ProviderError) Is(target error) bool {
	return errors.Is(p.User, target)
}

var (
	ErrInternal           = errors.New("internal server error")
	ErrInvalidCredentials = errors.New("invalid credentials")
	ErrUserDisabled       = errors.New("disabled user")
	ErrUnknownIDP         = errors.New("unknown identity provider")
	errInvalidIDP         = errors.New("invalid identity provider for this operation")
)

type Unknown struct{}

func (Unknown) String() string {
	return types.Unknown
}

func (Unknown) Login(context.Context, string, map[string]string) (*model.Group, *model.User, string, *ProviderError) {
	return nil, nil, "", &ProviderError{
		User:   ErrUnknownIDP,
		Detail: errors.New("unknown provider"),
	}
}

func (Unknown) Callback(context.Context, *token.CallbackClaims, map[string]string) (*model.Group, *model.User, string, *ProviderError) {
	return nil, nil, "", &ProviderError{
		User:   ErrUnknownIDP,
		Detail: errors.New("unknown provider"),
	}
}

func (Unknown) AutoRegister() bool {
	return false
}

func (Unknown) Healthcheck() error {
	return nil
}

func matchRegex(re *regexp.Regexp, s string) string {
	result := re.FindStringSubmatch(s)
	// the first submatch is the whole match, the 2nd is the 1st group
	if len(result) > 1 {
		return result[1]
	}

	return re.FindString(s)
}
