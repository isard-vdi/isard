package authentication

import (
	"context"
	"errors"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/token"
)

var (
	ErrUserNotEnabled = errors.New("user not enabled")
)

func (a *Authentication) GenerateUserToken(ctx context.Context, tkn string, userID string) (userTkn string, err error) {
	tokenType, err := token.GetTokenType(tkn)
	if err != nil {
		return "", err
	}

	if tokenType != token.TypeLogin && tokenType != token.TypeExternal {
		return "", token.ErrInvalidTokenType
	}

	var parsedToken interface{}

	if tokenType == token.TypeExternal {
		// Parse the token
		parsedToken, err = token.ParseExternalToken(a.DB, tkn)
		if err != nil {
			return "", err
		}

	} else if tokenType == token.TypeLogin {
		// Parse the token
		parsedToken, err = token.ParseLoginToken(a.Secret, tkn)
		if err != nil {
			return "", err
		}

	}

	var roleID string
	var categoryID string

	switch t := parsedToken.(type) {
	case *token.ExternalClaims:
		roleID = t.Role
		categoryID = t.CategoryID
	case *token.LoginClaims:
		roleID = t.Data.RoleID
		categoryID = t.Data.CategoryID
	default:
		return "", token.ErrInvalidTokenType
	}
	tknRole := model.Role(roleID)

	// Check if the token role is admin or manager. These are the only roles
	// that can generate a token for another user
	if !tknRole.HasEqualOrMorePrivileges(model.RoleManager) {
		return "", token.ErrInvalidTokenRole
	}

	// Retrieve the user
	u := &model.User{
		ID: userID,
	}
	err = u.Load(ctx, a.DB)
	if err != nil {
		return "", err
	}

	// Check if the user is active
	if !u.Active {
		return "", ErrUserNotEnabled
	}

	// If the token is manager the user must be from the same category
	if tknRole.HasEqualPrivileges(model.RoleManager) {
		if categoryID != u.Category {
			return "", token.ErrInvalidTokenCategory
		}
	}

	// Generate a token for the user
	usrTkn, err := token.SignLoginToken(a.Secret, time.Now().Add(time.Hour), "isardvdi-service", u)
	if err != nil {
		return "", err
	}

	return usrTkn, nil

}
