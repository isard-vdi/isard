package authentication

import (
	"context"
	"errors"
	"fmt"
	"net/mail"
	"net/url"
	"path"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/token"
	"gitlab.com/isard/isardvdi/pkg/gen/oas/notifier"
)

var (
	ErrInvalidEmail      = errors.New("invalid email")
	ErrEmailAlreadyInUse = errors.New("email address already in use")
)

// RequestEmailVerification requests a new email verification. This generates a temporary token
// that gets sent to the provided email
func (a *Authentication) RequestEmailVerification(ctx context.Context, ss, email string) error {
	tkn, err := token.ParseEmailVerificationRequiredToken(a.Secret, ss)
	if err != nil {
		return err
	}

	addr, err := mail.ParseAddress(email)
	if err != nil {
		return ErrInvalidEmail
	}

	u := &model.User{
		ID:       tkn.UserID,
		Category: tkn.CategoryID,
		Email:    addr.Address,
	}
	exists, err := u.ExistsWithVerifiedEmail(ctx, a.DB)
	if err != nil {
		return fmt.Errorf("check if email is unique: %w", err)
	}

	if exists {
		// Check if the email is already being used by the same user that's requesting the verification
		// and ensure it has already been verified earlier
		if u.ID != tkn.UserID || u.EmailVerified == nil {
			return ErrEmailAlreadyInUse
		}
	}

	verificationTkn, err := token.SignEmailVerificationToken(a.Secret, tkn.UserID, addr.Address)
	if err != nil {
		return err
	}

	u.Email = addr.Address
	u.EmailVerified = nil
	u.EmailVerificationToken = verificationTkn

	if err := u.UpdateEmail(ctx, a.DB); err != nil {
		return fmt.Errorf("save the email verification token: %w", err)
	}

	verifyURL := *a.BaseURL
	verifyURL.Path = path.Join(verifyURL.Path, "/verify-email")

	params := url.Values{}
	params.Add("token", u.EmailVerificationToken)
	verifyURL.RawQuery = params.Encode()

	rsp, err := a.Notifier.PostNotifierMailEmailVerify(ctx, &notifier.NotifyEmailVerifyMailRequest0bf6af6{
		UserID: u.ID,
		Email:  u.Email,
		URL:    verifyURL.String(),
	})
	if err != nil {
		return fmt.Errorf("error calling the notifier service: %w", err)
	}

	switch r := rsp.(type) {
	case *notifier.NotifyEmailVerifyMailResponse0bf6af6:
		a.Log.Info().Str("user_id", u.ID).Str("email", u.Email).Str("task_id", r.TaskID.String()).Msg("email verification email sent")

	default:
		return fmt.Errorf("unknown response from the notifier service: %v", r)
	}

	return nil
}

// VerifyEmail verificates a email for a user using a token generated by the RequestEmailVerification
func (a *Authentication) VerifyEmail(ctx context.Context, ss string) error {
	tkn, err := token.ParseEmailVerificationToken(a.Secret, ss)
	if err != nil {
		return err
	}

	u := &model.User{
		ID: tkn.UserID,
	}
	if err := u.Load(ctx, a.DB); err != nil {
		return fmt.Errorf("load the user from the DB: %w", err)
	}

	if ss != u.EmailVerificationToken {
		return errors.New("token mismatch")
	}

	u.Email = tkn.Email
	now := float64(time.Now().Unix())
	u.EmailVerified = &now
	u.EmailVerificationToken = ""

	if err := u.UpdateEmail(ctx, a.DB); err != nil {
		return fmt.Errorf("update the DB: %w", err)
	}

	return nil
}
