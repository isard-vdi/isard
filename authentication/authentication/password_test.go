package authentication_test

import (
	"context"
	"net/http"
	"strings"
	"testing"

	"gitlab.com/isard/isardvdi/authentication/authentication"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/pkg/gen/oas/notifier"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func TestForgotPassword(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		PrepareDB       func(*r.Mock)
		PrepareNotifier func(*notifier.MockClientWithResponsesInterface)
		CategoryID      string
		Email           string
		ExpectedErr     string
	}{
		"should work as expected": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("category"), "default"),
					r.Eq(r.Row.Field("email"), "nefix@example.org"),
				))).Return([]interface{}{
					map[string]interface{}{
						"id":    "néfix imagine this is an UUID",
						"email": "nefix@example.org",
					},
				}, nil)
				m.On(r.Table("users").Get("néfix imagine this is an UUID").Update(map[string]interface{}{
					"password_reset_token": r.MockAnything(),
				})).Return(r.WriteResponse{
					Updated: 1,
				}, nil)
			},
			PrepareNotifier: func(c *notifier.MockClientWithResponsesInterface) {
				c.On("PostNotifierMailPasswordResetWithResponse", mock.AnythingOfType("context.backgroundCtx"), mock.MatchedBy(func(req notifier.PostNotifierMailPasswordResetJSONRequestBody) bool {
					return req.Email == "nefix@example.org" &&
						strings.HasPrefix(req.Url, "https://localhost/reset-password?token=e")
				})).Return(&notifier.PostNotifierMailPasswordResetResponse{
					HTTPResponse: &http.Response{
						StatusCode: http.StatusOK,
					},
					JSON200: &notifier.NotifyPasswordResetMailResponse0bf6af6{
						TaskId: uuid.New(),
					},
				}, nil)
			},
			CategoryID: "default",
			Email:      "nefix@example.org",
		},
		"should return an error if the user isn't found": {
			PrepareDB: func(m *r.Mock) {
				m.On(r.Table("users").Filter(r.And(
					r.Eq(r.Row.Field("category"), "default"),
					r.Eq(r.Row.Field("email"), "nefix@example.org"),
				))).Return([]interface{}{}, nil)
			},
			CategoryID:  "default",
			Email:       "nefix@example.org",
			ExpectedErr: "user not found",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			cfg := cfg.New()
			log := log.New("authentication-test", "debug")
			mock := r.NewMock()
			notifier := notifier.NewMockClientWithResponsesInterface(t)

			if tc.PrepareDB != nil {
				tc.PrepareDB(mock)
			}

			a := authentication.Init(cfg, log, mock)

			if tc.PrepareNotifier != nil {
				tc.PrepareNotifier(notifier)
			}
			a.Notifier = notifier

			err := a.ForgotPassword(context.Background(), tc.CategoryID, tc.Email)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			mock.AssertExpectations(t)
		})
	}
}
