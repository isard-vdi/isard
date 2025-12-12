package authentication

import (
	"context"
	"errors"
	"fmt"
	"net/mail"
	"slices"
	"strings"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"
	"gitlab.com/isard/isardvdi/pkg/db"
	sessionsv1 "gitlab.com/isard/isardvdi/pkg/gen/proto/go/sessions/v1"
)

func (a *Authentication) Login(ctx context.Context, prv, categoryID string, args provider.LoginArgs, remoteAddr string) (string, string, error) {
	if args.Redirect == nil {
		redirect := ""
		args.Redirect = &redirect
	}

	// Check if the user sends a token
	if args.Token != nil {
		typ, err := token.GetTokenType(*args.Token)
		if err != nil {
			return "", "", fmt.Errorf("get the JWT token type: %w", err)
		}

		switch typ {
		case token.TypeRegister:
			return a.finishRegister(ctx, remoteAddr, *args.Token, *args.Redirect)

		case token.TypeDisclaimerAcknowledgementRequired:
			return a.finishDisclaimerAcknowledgement(ctx, remoteAddr, *args.Token, *args.Redirect)

		case token.TypePasswordResetRequired:
			return a.finishPasswordReset(ctx, remoteAddr, *args.Token, *args.Redirect)

		case token.TypeCategorySelect:
			return a.finishCategorySelect(ctx, remoteAddr, categoryID, *args.Token, *args.Redirect)
		}
	}

	// Get the provider
	p := a.Provider(prv)

	// Log in
	g, secondary, u, redirect, ss, lErr := p.Login(ctx, categoryID, args)
	if lErr != nil {
		a.Log.Info().Str("prv", p.String()).Err(lErr).Msg("login failed")

		return "", "", fmt.Errorf("login: %w", lErr)
	}

	// If the provider forces us to redirect, do it
	if redirect != "" {
		return "", redirect, nil
	}

	// If the provider returns a token return it
	if ss != "" {
		return ss, redirect, nil
	}

	// Continue with the login process, passing the redirect path that has been
	// requested by the user
	return a.startLogin(ctx, remoteAddr, p, g, secondary, u, *args.Redirect)
}

func (a *Authentication) Callback(ctx context.Context, ss string, args provider.CallbackArgs, remoteAddr string) (string, string, error) {
	claims, err := token.ParseCallbackToken(a.Secret, ss)
	if err != nil {
		return "", "", fmt.Errorf("parse callback state: %w", err)
	}

	// Get the provider
	p := a.Provider(claims.Provider)

	// Callback
	g, secondary, u, redirect, ss, cErr := p.Callback(ctx, claims, args)
	if cErr != nil {
		a.Log.Info().Str("prv", p.String()).Err(cErr).Msg("callback failed")

		return "", "", fmt.Errorf("callback: %w", cErr)
	}

	if redirect == "" {
		redirect = claims.Redirect
	}

	// If the provider returns a token return it
	if ss != "" {
		return ss, redirect, nil
	}

	return a.startLogin(ctx, remoteAddr, p, g, secondary, u, redirect)
}

func (a *Authentication) startLogin(ctx context.Context, remoteAddr string, p provider.Provider, g *model.Group, secondary []*model.Group, data *types.ProviderUserData, redirect string) (string, string, error) {
	u := data.ToUser()

	c := &model.Category{ID: u.Category}
	c, err := c.Load(ctx, a.DB)
	if err != nil {
		return "", "", fmt.Errorf("get category: %w", err)
	}

	categoryAuth, ok := c.Authentication[u.Provider]

	// If there's specific configuration in the category for this provider, take it into account
	// Also, never lock out the default admin user, so it can recover fucked up configurations
	if ok && !isDefaultAdmin(u) {
		// If the category has this provider disabled, don't let the user in
		if categoryAuth.Enabled != nil && !*categoryAuth.Enabled {
			return "", "", provider.ErrUserDisallowed
		}

		// If there are allowed domains, check the user is in the allowed domains
		if categoryAuth.Enabled != nil && *categoryAuth.Enabled && categoryAuth.AllowedDomains != nil && len(*categoryAuth.AllowedDomains) != 0 {
			if u.Email != "" {
				// Parse the email address of the user
				addr, err := mail.ParseAddress(u.Email)
				if err != nil {
					return "", "", fmt.Errorf("parse user email address: '%s': %w", u.Email, err)
				}

				// Check the position of the last @ in the email address
				// We check for the last @ because `"user@something"@example.com` is a valid address https://stackoverflow.com/a/12355882
				at := strings.LastIndex(addr.Address, "@")
				// Get the domain from the email address after the last @
				domain := u.Email[at+1:]

				// If the domain is not in the allowed domains, return an error
				if !slices.Contains(*categoryAuth.AllowedDomains, domain) {
					return "", "", provider.ErrUserDisallowed
				}

			} else {
				// If the user doesn't have an email, and there are allowed domains, return an error
				if len(*categoryAuth.AllowedDomains) != 0 {
					return "", "", provider.ErrUserDisallowed
				}
			}

		}
	}

	// Call SaveEmail for user data provisioning provider, due to p is form when ldap and local
	if !a.Provider(u.Provider).SaveEmail() {
		u.Email = ""
	}
	providerName := u.Name
	dbUser, uExists, err := u.FindExisting(ctx, a.DB)
	if err != nil {
		return "", "", fmt.Errorf("check if user exists: %w", err)
	}

	// Remove weird characters from the user and group names
	normalizeIdentity(g, u)

	// Flag to track if we need to update existing user
	var needsUpdate bool
	if uExists {
		// Check if provider name differs from database name
		if dbUser.Name != providerName {
			needsUpdate = true
			*u = *dbUser
			// Keep the provider name
			u.Name = providerName
		} else {
			// Use the existing database user data
			*u = *dbUser
		}
	}

	if !uExists {
		// Manual registration
		if !p.AutoRegister(u) {
			// If the user has logged in correctly, but doesn't exist in the DB, they have to register first!
			ss, err := token.SignRegisterToken(a.Secret, u)

			a.Log.Info().Err(err).Str("usr", u.UID).Msg("register token signed")

			return ss, redirect, err
		}

		// Automatic group registration!
		if g != nil {
			for _, group := range append(secondary, g) {
				gExists, err := group.Exists(ctx, a.DB)
				if err != nil {
					return "", "", fmt.Errorf("check if group exists: %w", err)
				}

				if !gExists {
					if err := a.registerGroup(group); err != nil {
						return "", "", fmt.Errorf("auto register group: %w", err)
					}
				}
			}

			// Set the user group to the new group created
			u.Group = g.ID
			for _, group := range secondary {
				u.SecondaryGroups = append(u.SecondaryGroups, group.ID)
			}
		}

		// Automatic registration!
		if err := a.registerUser(u); err != nil {
			return "", "", fmt.Errorf("auto register user: %w", err)
		}
	} else if needsUpdate {
		// Update existing user if provider name has changed
		if err := u.Update(ctx, a.DB); err != nil {
			return "", "", fmt.Errorf("update user: %w", err)
		}
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

	// TODO: Check if the user needs to migrate themselves
	if false {
		ss, err := token.SignUserMigrationRequiredToken(a.Secret, u.ID)
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

	// Call API to check if the user has fullpage notifications pending, if so redirect to /notifications/login
	rsp, err := a.API.AdminUserNotificationsDisplays(ctx, u.ID)
	if err != nil {
		return "", "", fmt.Errorf("check if the user has notifications pending: %w", err)
	}

	a.Log.Info().Str("rsp", fmt.Sprintf("%v", rsp)).Msg("notifications displays")
	for _, display := range rsp {
		if display == "fullpage" {
			redirect = "/notifications/login"
			break
		}
	}

	a.Log.Info().Str("usr", u.ID).Str("redirect", redirect).Msg("login succeeded")

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

	a.Log.Info().Str("usr", u.ID).Msg("register succeeded")

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

func (a *Authentication) finishCategorySelect(ctx context.Context, remoteAddr, categoryID, ss, redirect string) (string, string, error) {
	claims, err := token.ParseCategorySelectToken(a.Secret, ss)
	if err != nil {
		return "", "", err
	}

	p := a.Provider(claims.User.Provider)

	u := &claims.User
	u.Category = categoryID

	var g *model.Group
	secondary := []*model.Group{}
	if claims.RawGroups != nil && len(*claims.RawGroups) != 0 {
		var err *provider.ProviderError
		g, secondary, err = p.GuessGroups(ctx, u, *claims.RawGroups)
		if err != nil && !errors.Is(err, provider.ErrInvalidIDP) {
			return "", "", fmt.Errorf("guess groups from token: %w", err)
		}
	}

	if claims.RawRoles != nil && len(*claims.RawRoles) != 0 {
		var err *provider.ProviderError
		u.Role, err = p.GuessRole(ctx, u, *claims.RawRoles)
		if err != nil && !errors.Is(err, provider.ErrInvalidIDP) {
			return "", "", fmt.Errorf("guess role from token: %w", err)
		}
	}

	return a.startLogin(ctx, remoteAddr, p, g, secondary, u, redirect)
}

func isDefaultAdmin(u *model.User) bool {
	return u.Provider == types.ProviderLocal &&
		u.Category == "default" &&
		u.UID == "admin"
}
