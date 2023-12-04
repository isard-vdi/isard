package authentication

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"path"

	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/pkg/gen/oas/notifier"

	"gitlab.com/isard/isardvdi-sdk-go"
)

var ErrUserNotFound = errors.New("user not found")

// ForgotPassword sends a password reset email with a password-reset token
func (a *Authentication) ForgotPassword(ctx context.Context, categoryID, email string) error {
	u := &model.User{
		Category: categoryID,
		Email:    email,
	}
	exists, err := u.ExistsWithEmail(ctx, a.DB)
	if err != nil {
		return fmt.Errorf("check if user exists with email: %w", err)
	}

	if !exists {
		return ErrUserNotFound
	}

	pwdResetTkn, err := token.SignPasswordResetToken(a.Secret, u.ID)
	if err != nil {
		return err
	}

	u.PasswordResetToken = pwdResetTkn

	if err := u.UpdatePasswordResetToken(ctx, a.DB); err != nil {
		return fmt.Errorf("save the password reset token: %w", err)
	}

	resetURL := *a.BaseURL
	resetURL.Path = path.Join(resetURL.Path, "/reset-password")

	params := url.Values{}
	params.Add("token", u.PasswordResetToken)
	resetURL.RawQuery = params.Encode()

	rsp, err := a.Notifier.PostNotifierMailPasswordResetWithResponse(ctx, notifier.PostNotifierMailPasswordResetJSONRequestBody{
		Email: u.Email,
		Url:   resetURL.String(),
	})
	if err != nil {
		return fmt.Errorf("error calling the notifier service: %w", err)
	}

	a.Log.Info().Str("user_id", u.ID).Str("email", u.Email).Str("task_id", rsp.JSON200.TaskId.String()).Msg("password reset email sent")

	if rsp.StatusCode() != http.StatusOK {
		return fmt.Errorf("error calling the notifier service: HTTP status code %d", rsp.StatusCode())
	}

	return nil
}

// ResetPassword resets a password for a user
func (a *Authentication) ResetPassword(ctx context.Context, tkn, pwd string) error {
	typ, err := token.GetTokenType(tkn)
	if err != nil {
		return fmt.Errorf("get the JWT token type: %w", err)
	}

	var userID string

	switch typ {
	case token.TypeLogin:
		claims, err := token.ParseLoginToken(a.Secret, tkn)
		if err != nil {
			return err
		}

		userID = claims.Data.ID

	case token.TypePasswordReset:
		claims, err := token.ParsePasswordResetToken(a.Secret, tkn)
		if err != nil {
			return err
		}

		userID = claims.UserID

	default:
		return token.ErrInvalidTokenType
	}

	if err := a.Client.AdminUserResetPassword(ctx, userID, pwd); err != nil {
		var apiErr isardvdi.Err
		if !errors.As(err, &apiErr) {
			return fmt.Errorf("unknown API error: %w", err)
		}

		return err
	}

	a.Log.Info().Str("user_id", userID).Msg("reset password")

	return nil
}
