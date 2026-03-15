package provider

import (
	"context"
	"errors"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"
)

var _ Provider = &Unknown{}

type Unknown struct{}

func (Unknown) String() string {
	return types.ProviderUnknown
}

func (Unknown) Login(context.Context, string, LoginArgs) (*model.Group, []*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	return nil, nil, nil, "", "", &ProviderError{
		User:   ErrUnknownIDP,
		Detail: errors.New("unknown provider"),
	}
}

func (Unknown) Callback(context.Context, *token.CallbackClaims, CallbackArgs) (*model.Group, []*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	return nil, nil, nil, "", "", &ProviderError{
		User:   ErrUnknownIDP,
		Detail: errors.New("unknown provider"),
	}
}

func (Unknown) AutoRegister(*model.User) bool {
	return false
}

func (Unknown) Healthcheck() error {
	return nil
}

func (Unknown) Logout(context.Context, string) (string, error) {
	return "", nil
}

func (Unknown) SaveEmail() bool {
	return true
}

func (Unknown) GuessGroups(context.Context, *types.ProviderUserData, []string) (*model.Group, []*model.Group, *ProviderError) {
	return nil, nil, &ProviderError{
		User:   ErrUnknownIDP,
		Detail: errors.New("unknown provider"),
	}
}

func (Unknown) GuessRole(context.Context, *types.ProviderUserData, []string) (*model.Role, *ProviderError) {
	return nil, &ProviderError{
		User:   ErrUnknownIDP,
		Detail: errors.New("unknown provider"),
	}
}
