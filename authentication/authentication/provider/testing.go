package provider

import (
	"context"

	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/authentication/model"

	"github.com/stretchr/testify/mock"
)

var _ Provider = &ProviderMock{}

type ProviderMock struct {
	mock.Mock
}

func (m *ProviderMock) Login(ctx context.Context, categoryID string, args map[string]string) (g *model.Group, u *model.User, redirect string, err error) {
	mArgs := m.Called(ctx, categoryID, args)
	return mArgs.Get(0).(*model.Group), mArgs.Get(1).(*model.User), mArgs.String(2), mArgs.Error(3)
}

func (m *ProviderMock) Callback(ctx context.Context, claims *token.CallbackClaims, args map[string]string) (g *model.Group, u *model.User, redirect string, err error) {
	mArgs := m.Called(ctx, claims, args)
	return mArgs.Get(0).(*model.Group), mArgs.Get(1).(*model.User), mArgs.String(2), mArgs.Error(3)
}

func (m *ProviderMock) AutoRegister() bool {
	mArgs := m.Called()
	return mArgs.Bool(0)
}

func (m *ProviderMock) String() string {
	return "mock"
}
