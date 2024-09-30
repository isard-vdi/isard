package provider_test

import (
	"context"
	"net/http"
	"net/url"
	"testing"

	"github.com/crewjam/saml"
	"github.com/crewjam/saml/samlsp"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"
)

func TestSAMLLogin(t *testing.T) {
	assert := assert.New(t)

	redirect := "/hola"

	cases := map[string]struct {
		CategoryID        string
		Args              provider.LoginArgs
		ExpectedGrp       *model.Group
		ExpectedSecondary []*model.Group
		ExpectedUsr       *types.ProviderUserData
		CheckRedirect     func(string)
		ExpectedTkn       string
		ExpectedErr       string
	}{
		"should work as expected": {
			CategoryID: "default",
			Args: provider.LoginArgs{
				Redirect: &redirect,
			},
			ExpectedSecondary: []*model.Group{},
			CheckRedirect: func(redirect string) {
				u, err := url.Parse(redirect)
				assert.NoError(err)

				assert.Equal("/authentication/callback", u.Path)

				state := u.Query().Get("state")
				assert.NotEmpty(state)

				claims, err := token.ParseCallbackToken("", state)
				assert.NoError(err)

				// TODO: Check time

				assert.Equal(types.ProviderSAML, claims.Provider)
				assert.Equal("default", claims.CategoryID)
				assert.Equal("/hola", claims.Redirect)
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			s := &provider.SAML{}
			g, secondary, u, redirect, tkn, err := s.Login(context.Background(), tc.CategoryID, tc.Args)

			assert.Equal(tc.ExpectedGrp, g)
			assert.Equal(tc.ExpectedSecondary, secondary)
			assert.Equal(tc.ExpectedUsr, u)
			tc.CheckRedirect(redirect)
			assert.Equal(tc.ExpectedTkn, tkn)

			if tc.ExpectedErr == "" {
				assert.Nil(err)
			} else {
				assert.EqualError(err, tc.ExpectedErr)
			}
		})
	}
}

// func TestSAMLCallback(t *testing.T) {
// 	assert := assert.New(t)

// 	cases := map[string]struct {
// 		Cfg                     cfg.Authentication
// 		PrepeareSessionProvider func(*samlSessionProviderMock)
// 		Request                 *http.Request
// 		Claims                  *token.CallbackClaims
// 		Args                    provider.CallbackArgs
// 		ExpectedGrp             *model.Group
// 		ExpectedUsr             *types.ProviderUserData
// 		ExpectedRedirect        string
// 		ExpectedTkn             string
// 		ExpectedErr             string
// 	}{
// 		"should work as expected": {
// 			Cfg: cfg.Authentication{
// 				SAML: cfg.AuthenticationSAML{
// 					GuessCategory: true,
// 				},
// 			},
// 			PrepeareSessionProvider: func(m *samlSessionProviderMock) {
// 				sess := &samlSession{}
// 				sess.On("GetAttributes").Return(samlsp.Attributes{})

// 				m.On("GetSession", (*http.Request)(nil)).Return(sess, nil)
// 			},
// 			Claims: &token.CallbackClaims{
// 				Provider:   types.ProviderSAML,
// 				CategoryID: "default",
// 				Redirect:   "/hola",
// 			},
// 			Args: provider.CallbackArgs{},
// 		},
// 	}

// 	for name, tc := range cases {
// 		t.Run(name, func(t *testing.T) {
// 			sessProvider := &samlSessionProviderMock{}

// 			tc.PrepeareSessionProvider(sessProvider)

// 			s := provider.InitSAML(tc.Cfg, log.New("authentication", "debug"), nil)

// 			ctx := context.Background()
// 			ctx = context.WithValue(ctx, provider.HTTPRequest, tc.Request)

// 			g, u, redirect, tkn, err := s.Callback(ctx, tc.Claims, tc.Args)

// 			assert.Equal(tc.ExpectedGrp, g)
// 			assert.Equal(tc.ExpectedUsr, u)
// 			assert.Equal(tc.ExpectedRedirect, redirect)
// 			assert.Equal(tc.ExpectedTkn, tkn)

// 			if tc.ExpectedErr == "" {
// 				assert.Nil(err)
// 			} else {
// 				assert.EqualError(err, tc.ExpectedErr)
// 			}

// 			sessProvider.AssertExpectations(t)
// 		})
// 	}
// }

//
// Mock for the SAML session provider
//

var _ samlsp.SessionProvider = &samlSessionProviderMock{}

type samlSessionProviderMock struct {
	mock.Mock
}

func (s *samlSessionProviderMock) CreateSession(w http.ResponseWriter, r *http.Request, assertion *saml.Assertion) error {
	args := s.Called(w, r, assertion)
	return args.Error(0)
}

func (s *samlSessionProviderMock) DeleteSession(w http.ResponseWriter, r *http.Request) error {
	args := s.Called(w, r)
	return args.Error(0)
}

func (s *samlSessionProviderMock) GetSession(r *http.Request) (samlsp.Session, error) {
	args := s.Called(r)
	return args.Get(0).(samlsp.Session), args.Error(1)
}

type samlSession struct {
	mock.Mock
}

func (s *samlSession) GetAttributes() samlsp.Attributes {
	args := s.Called()
	return args.Get(0).(samlsp.Attributes)
}
