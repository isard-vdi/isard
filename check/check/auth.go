package check

import (
	"context"
	"errors"
	"fmt"

	"gitlab.com/isard/isardvdi/pkg/sdk"
)

type AuthMethod int

const (
	AuthMethodUnknown AuthMethod = iota
	AuthMethodForm
	AuthMethodToken
)

type Auth struct {
	Form  *AuthForm
	Token *AuthToken
}

type AuthForm struct {
	Category string
	Username string
	Password string
}

type AuthToken struct {
	Token string
}

func (c *Check) auth(ctx context.Context, cli sdk.Interface, method AuthMethod, auth Auth) error {
	switch method {
	case AuthMethodForm:
		tkn, err := cli.AuthForm(ctx, auth.Form.Category, auth.Form.Username, auth.Form.Password)
		if err != nil {
			return fmt.Errorf("error authenticating: %w", err)
		}

		cli.SetToken(tkn)

	case AuthMethodToken:
		cli.SetToken(auth.Token.Token)

	default:
		return errors.New("unknown authentication method")
	}

	return nil
}
