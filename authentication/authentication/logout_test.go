package authentication_test

import (
	"context"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/authentication"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/token"
	sessionsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/sessions/v1"
	"gitlab.com/isard/isardvdi/pkg/grpc"
	"gitlab.com/isard/isardvdi/pkg/log"
	"gitlab.com/isard/isardvdi/pkg/sdk"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"go.nhat.io/grpcmock"
	"google.golang.org/grpc/codes"
)

func TestLogout(t *testing.T) {
	assert := assert.New(t)
	require := require.New(t)

	cases := map[string]struct {
		PrepareSessions func(*grpcmock.Server)
		PrepareToken    func() string
		ExpectedErr     string
	}{
		"should work as expected": {
			PrepareSessions: func(s *grpcmock.Server) {
				s.ExpectUnary("/sessions.v1.SessionsService/Revoke").WithPayload(&sessionsv1.RevokeRequest{
					Id: "ThoJuroQueEsUnID",
				}).Return(&sessionsv1.RevokeResponse{})
			},
			PrepareToken: func() string {
				now := float64(time.Now().Unix())

				ss, err := token.SignLoginToken("", time.Now().Add(time.Hour), "ThoJuroQueEsUnID", &model.User{
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
		},
		"should NOT return an error if the session doesn't exist (it probably has already been revoked)": {
			PrepareSessions: func(s *grpcmock.Server) {
				s.ExpectUnary("/sessions.v1.SessionsService/Revoke").WithPayload(&sessionsv1.RevokeRequest{
					Id: "ThoJuroQueEsUnID",
				}).ReturnError(codes.NotFound, "session not found")
			},
			PrepareToken: func() string {
				now := float64(time.Now().Unix())

				ss, err := token.SignLoginToken("", time.Now().Add(time.Hour), "ThoJuroQueEsUnID", &model.User{
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
		},
		"should return an error if the token is expired": {
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
			ExpectedErr: "parse the login token: error parsing the JWT token: token has invalid claims: token is expired",
		},
		"should return an error if the token is invalid": {
			PrepareToken: func() string {
				return "BON DIA MELINA"
			},
			ExpectedErr: "parse the login token: error parsing the JWT token: token is malformed: token contains an invalid number of segments",
		},
		"should return an error if there's an error revoking the session": {
			PrepareSessions: func(s *grpcmock.Server) {
				s.ExpectUnary("/sessions.v1.SessionsService/Revoke").WithPayload(&sessionsv1.RevokeRequest{
					Id: "ThoJuroQueEsUnID",
				}).ReturnError(codes.Unavailable, "m'he cansat, masses peticions :(")
			},
			PrepareToken: func() string {
				now := float64(time.Now().Unix())

				ss, err := token.SignLoginToken("", time.Now().Add(time.Hour), "ThoJuroQueEsUnID", &model.User{
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
			ExpectedErr: "revoke session: rpc error: code = Unavailable desc = m'he cansat, masses peticions :(",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ctx := context.Background()

			cfg := cfg.New()
			log := log.New("authentication-test", "debug")
			apiMock := sdk.NewMockSdk(t)

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

			err = a.Logout(context.Background(), tc.PrepareToken())

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			apiMock.AssertExpectations(t)
		})
	}
}
