package authentication_test

import (
	"context"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/authentication"
	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	sessionsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/sessions/v1"
	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	apiMock "gitlab.com/isard/isardvdi-sdk-go/mock"
	"go.nhat.io/grpcmock"
	"google.golang.org/protobuf/types/known/timestamppb"
)

func TestRenew(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	now := time.Now()

	cases := map[string]struct {
		PrepareSessions func(*grpcmock.Server)
		PrepareToken    func() string
		CheckToken      func(string)
		RemoteAddr      string
		ExpectedErr     string
	}{
		"should work as expected": {
			PrepareSessions: func(s *grpcmock.Server) {
				s.ExpectUnary("/sessions.v1.SessionsService/Renew").WithPayload(&sessionsv1.RenewRequest{
					Id:         "ThoJuroQueEsUnID",
					RemoteAddr: "127.0.0.1",
				}).Return(&sessionsv1.RenewResponse{
					Time: &sessionsv1.RenewResponseTime{
						MaxTime:        timestamppb.New(now.Add(time.Hour)),
						MaxRenewTime:   timestamppb.New(now.Add(time.Hour)),
						ExpirationTime: timestamppb.New(now.Add(time.Hour)),
					},
				})
			},
			PrepareToken: func() string {
				now := float64(time.Now().Unix())

				ss, err := token.SignLoginToken("", time.Now().Add(-time.Hour), "ThoJuroQueEsUnID", &model.User{
					ID:                     "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					UID:                    "nefix",
					Username:               "nefix",
					Password:               "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
					Provider:               "local",
					Active:                 true,
					Category:               "default",
					Role:                   "user",
					Group:                  "default-default",
					Name:                   "Néfix Estrada",
					Email:                  "nefix@example.org",
					EmailVerified:          &now,
					DisclaimerAcknowledged: true,
				})
				require.NoError(err)

				return ss
			},
			RemoteAddr: "127.0.0.1",
			CheckToken: func(ss string) {
				claims, err := token.ParseLoginToken("", ss)
				assert.NoError(err)

				assert.Equal(&token.LoginClaims{
					RegisteredClaims: &jwt.RegisteredClaims{
						Issuer:    "isard-authentication",
						Subject:   "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
						ExpiresAt: jwt.NewNumericDate(now.Add(time.Hour)),
						IssuedAt:  jwt.NewNumericDate(now),
						NotBefore: jwt.NewNumericDate(now),
					},
					KeyID:     "isardvdi",
					SessionID: "ThoJuroQueEsUnID",
					Data: token.LoginClaimsData{
						Provider:   "local",
						ID:         "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
						RoleID:     "user",
						CategoryID: "default",
						GroupID:    "default-default",
						Name:       "Néfix Estrada",
					},
				}, claims)
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ctx := context.Background()

			cfg := cfg.New()
			log := log.New("authentication-test", "debug")
			apiMock := &apiMock.Client{}

			if tc.PrepareSessions == nil {
				tc.PrepareSessions = func(s *grpcmock.Server) {}
			}
			sessionsSrv := grpcmock.NewServer(
				grpcmock.RegisterService(sessionsv1.RegisterSessionsServiceServer),
				tc.PrepareSessions,
			)
			t.Cleanup(func() {
				sessionsSrv.Close()
			})

			sessionsCli, sessionsConn, err := grpc.NewClient(ctx, sessionsv1.NewSessionsServiceClient, sessionsSrv.Address())
			require.NoError(err)
			defer sessionsConn.Close()

			a := authentication.Init(cfg, log, nil, nil, nil, sessionsCli)

			tkn, err := a.Renew(context.Background(), tc.PrepareToken(), tc.RemoteAddr)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.CheckToken != nil {
				tc.CheckToken(tkn)
			} else {
				assert.Empty(tkn)
			}

			apiMock.AssertExpectations(t)
		})
	}
}
