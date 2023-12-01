package authentication

import (
	"context"

	"github.com/crewjam/saml/samlsp"
	"github.com/stretchr/testify/mock"
	"gitlab.com/isard/isardvdi/authentication/authentication/provider"
)

var _ Interface = &AuthenticationMock{}

func NewAuthenticationMock() *AuthenticationMock {
	return &AuthenticationMock{
		AuthProvider: &provider.ProviderMock{},
	}
}

type AuthenticationMock struct {
	mock.Mock
	AuthProvider provider.Provider
}

func (m *AuthenticationMock) Login(ctx context.Context, provider string, categoryID string, args map[string]string) (string, string, error) {
	mArgs := m.Called(ctx, provider, categoryID, args)
	return mArgs.String(0), mArgs.String(1), mArgs.Error(2)
}

func (m *AuthenticationMock) Callback(ctx context.Context, args map[string]string) (string, string, error) {
	mArgs := m.Called(ctx, args)
	return mArgs.String(0), mArgs.String(1), mArgs.Error(2)
}

func (m *AuthenticationMock) Check(ctx context.Context, tkn string) error {
	mArgs := m.Called(ctx, tkn)
	return mArgs.Error(0)
}

func (m *AuthenticationMock) Providers() []string {
	return []string{"local", "google", "ldap", "saml"}
}

func (m *AuthenticationMock) Provider(prv string) provider.Provider {
	m.Called(prv)
	return m.AuthProvider
}

func (m *AuthenticationMock) AcknowledgeDisclaimer(ctx context.Context, tkn string) error {
	mArgs := m.Called(ctx, tkn)
	return mArgs.Error(0)
}

func (m *AuthenticationMock) RequestEmailVerification(ctx context.Context, tkn, email string) error {
	mArgs := m.Called(ctx, tkn, email)
	return mArgs.Error(0)
}

func (m *AuthenticationMock) VerifyEmail(ctx context.Context, tkn string) error {
	mArgs := m.Called(ctx, tkn)
	return mArgs.Error(0)
}

func (m *AuthenticationMock) ForgotPassword(ctx context.Context, categoryID, email string) error {
	mArgs := m.Called(ctx, categoryID, email)
	return mArgs.Error(0)
}

func (m *AuthenticationMock) ResetPassword(ctx context.Context, tkn, pwd string) error {
	mArgs := m.Called(ctx, tkn, pwd)
	return mArgs.Error(0)
}

func (m *AuthenticationMock) SAML() *samlsp.Middleware {
	mArgs := m.Called()
	return mArgs.Get(0).(*samlsp.Middleware)
}
