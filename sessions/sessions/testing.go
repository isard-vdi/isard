package sessions

import (
	"context"

	"gitlab.com/isard/isardvdi/sessions/model"

	"github.com/stretchr/testify/mock"
)

var _ Interface = &SessionsMock{}

func NewSessionsMock() *SessionsMock {
	return &SessionsMock{}
}

type SessionsMock struct {
	mock.Mock
}

func (m *SessionsMock) New(ctx context.Context, userID string) (*model.Session, error) {
	mArgs := m.Called(ctx, userID)
	return mArgs.Get(0).(*model.Session), mArgs.Error(1)
}

func (m *SessionsMock) Get(ctx context.Context, id string) (*model.Session, error) {
	mArgs := m.Called(ctx, id)
	return mArgs.Get(0).(*model.Session), mArgs.Error(1)
}

func (m *SessionsMock) Renew(ctx context.Context, id string) (*model.SessionTime, error) {
	mArgs := m.Called(ctx, id)
	return mArgs.Get(0).(*model.SessionTime), mArgs.Error(1)
}

func (m *SessionsMock) Revoke(ctx context.Context, id string) error {
	mArgs := m.Called(ctx, id)
	return mArgs.Error(0)
}
