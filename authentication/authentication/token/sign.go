package token

import (
	"fmt"
	"time"

	"github.com/golang-jwt/jwt"
	"gitlab.com/isard/isardvdi/authentication/model"
)

const issuer = "isard-authentication"

func SignLoginToken(secret string, duration time.Duration, u *model.User) (string, error) {
	tkn := jwt.NewWithClaims(jwt.SigningMethodHS256, &LoginClaims{
		&jwt.StandardClaims{
			Issuer:    issuer,
			ExpiresAt: time.Now().Add(duration).Unix(),
		},
		// TODO: Other signing keys
		"isardvdi",
		LoginClaimsData{
			u.Provider,
			u.ID,
			string(u.Role),
			u.Category,
			u.Group,
			u.Name,
		},
	})

	ss, err := tkn.SignedString([]byte(secret))
	if err != nil {
		return "", fmt.Errorf("sign the token: %w", err)
	}

	return ss, nil
}

func SignRegisterToken(secret string, duration time.Duration, u *model.User) (string, error) {
	tkn := jwt.NewWithClaims(jwt.SigningMethodHS256, &RegisterClaims{
		&jwt.StandardClaims{
			Issuer:    issuer,
			ExpiresAt: time.Now().Add(duration).Unix(),
		},
		// TODO: Other signing keys
		"isardvdi",
		string(TypeRegister),
		u.Provider,
		u.UID,
		u.Username,
		u.Category,
		u.Name,
		u.Email,
		u.Photo,
	})

	ss, err := tkn.SignedString([]byte(secret))
	if err != nil {
		return "", fmt.Errorf("sign the register token: %w", err)
	}

	return ss, nil
}
