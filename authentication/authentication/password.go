package authentication

import (
	"context"
	"errors"
	"fmt"
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
	exists, err := u.ExistsWithVerifiedEmail(ctx, a.DB)
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

	rsp, err := a.Notifier.PostNotifierMailPasswordReset(ctx, notifier.NewOptNotifyPasswordResetMailRequest0bf6af6(notifier.NotifyPasswordResetMailRequest0bf6af6{
		Category: u.Category,
		Email:    u.Email,
		URL:      resetURL.String(),
	}))
	if err != nil {
		return fmt.Errorf("error calling the notifier service: %w", err)
	}

	switch r := rsp.(type) {
	case *notifier.NotifyPasswordResetMailResponse0bf6af6:
		a.Log.Info().Str("user_id", u.ID).Str("email", u.Email).Str("task_id", r.TaskID.String()).Msg("password reset email sent")

	default:
		return fmt.Errorf("unknown response from the notifier service: %v", r)
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
	// Reset from the profile page in the frontend
	case token.TypeLogin:
		claims, err := token.ParseLoginToken(a.Secret, tkn)
		if err != nil {
			return err
		}

		userID = claims.Data.ID

	// Reset from the forgot password URL
	case token.TypePasswordReset:
		claims, err := token.ParsePasswordResetToken(a.Secret, tkn)
		if err != nil {
			return err
		}

		userID = claims.UserID

		u := &model.User{
			ID:                 userID,
			PasswordResetToken: tkn,
		}
		exists, err := u.ExistsWithPasswordResetToken(ctx, a.DB)
		if err != nil {
			return fmt.Errorf("check if the password reset token exists: %w", err)
		}

		if !exists {
			return token.ErrInvalidToken
		}

	// Reset when the password policy requires it
	case token.TypePasswordResetRequired:
		claims, err := token.ParsePasswordResetRequiredToken(a.Secret, tkn)
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

	u := &model.User{
		ID:                 userID,
		PasswordResetToken: "",
	}
	if err := u.UpdatePasswordResetToken(ctx, a.DB); err != nil {
		return fmt.Errorf("remove password reset token: %w", err)
	}

	a.Log.Info().Str("user_id", userID).Msg("reset password")

	return nil
}
