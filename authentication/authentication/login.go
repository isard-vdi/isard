package authentication

import (
	"context"
	"errors"
	"fmt"
	"time"

	"gitlab.com/isard/isardvdi/authentication/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/authentication/token"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/pkg/db"
	sessionsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/sessions/v1"
)

func (a *Authentication) Login(ctx context.Context, remoteAddr string, prv, categoryID string, args map[string]string) (string, string, error) {
	// Check if the user sends a token
	if args[provider.TokenArgsKey] != "" {
		typ, err := token.GetTokenType(args[provider.TokenArgsKey])
		if err != nil {
			return "", "", fmt.Errorf("get the JWT token type: %w", err)
		}

		switch typ {
		case token.TypeRegister:
			return a.finishRegister(ctx, remoteAddr, args[provider.TokenArgsKey], args[provider.RedirectArgsKey])

		case token.TypeDisclaimerAcknowledgementRequired:
			return a.finishDisclaimerAcknowledgement(ctx, remoteAddr, args[provider.TokenArgsKey], args[provider.RedirectArgsKey])

		case token.TypePasswordResetRequired:
			return a.finishPasswordReset(ctx, remoteAddr, args[provider.TokenArgsKey], args[provider.RedirectArgsKey])
		}
	}

	// Get the provider and log in
	p := a.Provider(prv)
	g, u, redirect, lErr := p.Login(ctx, categoryID, args)
	if lErr != nil {
		a.Log.Info().Str("prv", p.String()).Err(lErr).Msg("login failed")

		return "", "", fmt.Errorf("login: %w", lErr)
	}

	// If the provider forces us to redirect, do it
	if redirect != "" {
		return "", redirect, nil
	}

	// Remove weird characters from the user and group names
	normalizeIdentity(g, u)

	uExists, err := u.Exists(ctx, a.DB)
	if err != nil {
		return "", "", fmt.Errorf("check if user exists: %w", err)
	}

	if !uExists {
		// Manual registration
		if !p.AutoRegister() {
			// If the user has logged in correctly, but doesn't exist in the DB, they have to register first!
			ss, err := token.SignRegisterToken(a.Secret, u)

			a.Log.Info().Err(err).Str("usr", u.UID).Str("tkn", ss).Msg("register token signed")

			return ss, "", err
		}

		// Automatic group registration!
		gExists, err := g.Exists(ctx, a.DB)
		if err != nil {
			return "", "", fmt.Errorf("check if group exists: %w", err)
		}

		if !gExists {
			if err := a.registerGroup(g); err != nil {
				return "", "", fmt.Errorf("auto register group: %w", err)
			}
		}

		// Set the user group to the new group created
		u.Group = g.ID

		// Automatic registration!
		if err := a.registerUser(u); err != nil {
			return "", "", fmt.Errorf("auto register user: %w", err)
		}
	}

	return a.finishLogin(ctx, remoteAddr, u, args[provider.RedirectArgsKey])
}

func (a *Authentication) Callback(ctx context.Context, remoteAddr string, ss string, args map[string]string) (string, string, error) {
	claims, err := token.ParseCallbackToken(a.Secret, ss)
	if err != nil {
		return "", "", fmt.Errorf("parse callback state: %w", err)
	}

	p := a.Provider(claims.Provider)

	// TODO: Add autoregister for more providers?
	_, u, redirect, cErr := p.Callback(ctx, claims, args)
	if cErr != nil {
		a.Log.Info().Str("prv", p.String()).Err(cErr).Msg("callback failed")

		return "", "", fmt.Errorf("callback: %w", cErr)
	}

	exists, err := u.Exists(ctx, a.DB)
	if err != nil {
		return "", "", fmt.Errorf("check if user exists: %w", err)
	}

	if redirect == "" {
		redirect = claims.Redirect
	}

	// Remove weird characters from the user name
	normalizeIdentity(nil, u)

	if !exists {
		ss, err = token.SignRegisterToken(a.Secret, u)
		if err != nil {
			return "", "", err
		}

		a.Log.Info().Str("usr", u.UID).Str("tkn", ss).Msg("register token signed")

		return ss, redirect, nil
	}

	return a.finishLogin(ctx, remoteAddr, u, redirect)
}

func (a *Authentication) finishLogin(ctx context.Context, remoteAddr string, u *model.User, redirect string) (string, string, error) {
	// Check if the user is disabled
	if !u.Active {
		return "", "", provider.ErrUserDisabled
	}

	// Check if the user needs to acknowledge the disclaimer
	dscl, err := a.API.AdminUserRequiredDisclaimerAcknowledgement(ctx, u.ID)
	if err != nil {
		return "", "", fmt.Errorf("check if the user needs to accept the disclaimer: %w", err)
	}
	if dscl {
		ss, err := token.SignDisclaimerAcknowledgementRequiredToken(a.Secret, u.ID)
		if err != nil {
			return "", "", err
		}

		return ss, redirect, nil
	}

	// Check if the user has the email verified
	vfEmail, err := a.API.AdminUserRequiredEmailVerification(ctx, u.ID)
	if err != nil {
		return "", "", fmt.Errorf("check if the user needs to verify the email: %w", err)
	}
	if vfEmail {
		ss, err := token.SignEmailVerificationRequiredToken(a.Secret, u)
		if err != nil {
			return "", "", err
		}

		return ss, redirect, nil
	}

	pwdRst, err := a.API.AdminUserRequiredPasswordReset(ctx, u.ID)
	if err != nil {
		return "", "", fmt.Errorf("check if the user needs to reset the password: %w", err)
	}
	if pwdRst {
		ss, err := token.SignPasswordResetRequiredToken(a.Secret, u.ID)
		if err != nil {
			return "", "", err
		}

		return ss, redirect, nil
	}

	// Set the last accessed time of the user
	u.Accessed = float64(time.Now().Unix())

	// Load the rest of the data of the user from the DB without overriding the data provided by the
	// login provider
	u2 := &model.User{ID: u.ID}
	if err := u2.Load(ctx, a.DB); err != nil {
		return "", "", fmt.Errorf("load user from DB: %w", err)
	}

	u.LoadWithoutOverride(u2)
	normalizeIdentity(nil, u)

	// Update the user in the DB with the latest data
	if err := u.Update(ctx, a.DB); err != nil {
		return "", "", fmt.Errorf("update user in the DB: %w", err)
	}

	// Create the session
	sess, err := a.Sessions.New(ctx, &sessionsv1.NewRequest{
		UserId:     u.ID,
		RemoteAddr: remoteAddr,
	})
	if err != nil {
		return "", "", fmt.Errorf("create the session: %w", err)
	}

	ss, err := token.SignLoginToken(a.Secret, sess.Time.ExpirationTime.AsTime(), sess.GetId(), u)
	if err != nil {
		return "", "", err
	}

	a.Log.Info().Str("usr", u.ID).Str("tkn", ss).Str("redirect", redirect).Msg("login succeeded")

	return ss, redirect, nil
}

func (a *Authentication) finishRegister(ctx context.Context, remoteAddr, ss, redirect string) (string, string, error) {
	claims, err := token.ParseRegisterToken(a.Secret, ss)
	if err != nil {
		return "", "", err
	}

	u := &model.User{
		Provider: claims.Provider,
		Category: claims.CategoryID,
		UID:      claims.UserID,
	}
	if err := u.LoadWithoutID(ctx, a.DB); err != nil {
		if errors.Is(err, db.ErrNotFound) {
			return "", "", errors.New("user not registered")
		}

		return "", "", fmt.Errorf("load user from db: %w", err)
	}

	ss, redirect, err = a.finishLogin(ctx, remoteAddr, u, redirect)
	if err != nil {
		return "", "", err
	}

	a.Log.Info().Str("usr", u.ID).Str("tkn", ss).Msg("register succeeded")

	return ss, redirect, nil
}

func (a *Authentication) finishDisclaimerAcknowledgement(ctx context.Context, remoteAddr, ss, redirect string) (string, string, error) {
	claims, err := token.ParseDisclaimerAcknowledgementRequiredToken(a.Secret, ss)
	if err != nil {
		return "", "", err
	}

	u := &model.User{ID: claims.UserID}
	if err := u.Load(ctx, a.DB); err != nil {
		return "", "", fmt.Errorf("load user from db: %w", err)
	}

	return a.finishLogin(ctx, remoteAddr, u, redirect)
}

func (a *Authentication) finishPasswordReset(ctx context.Context, remoteAddr, ss, redirect string) (string, string, error) {
	claims, err := token.ParsePasswordResetRequiredToken(a.Secret, ss)
	if err != nil {
		return "", "", err
	}

	u := &model.User{ID: claims.UserID}
	if err := u.Load(ctx, a.DB); err != nil {
		return "", "", fmt.Errorf("load user from db: %w", err)
	}

	return a.finishLogin(ctx, remoteAddr, u, redirect)
}
