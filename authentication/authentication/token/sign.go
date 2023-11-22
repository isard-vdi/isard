package token

import (
	"fmt"
	"time"

	"github.com/golang-jwt/jwt"
	"gitlab.com/isard/isardvdi/authentication/model"
)

const (
	issuer = "isard-authentication"
	// TODO: Other signing keys
	keyID = "isardvdi"
)

// TODO: Maybe this should be configuable
var signingMethod = jwt.SigningMethodHS256

func SignLoginToken(secret string, duration time.Duration, u *model.User) (string, error) {
	tkn := jwt.NewWithClaims(signingMethod, &LoginClaims{
		StandardClaims: &jwt.StandardClaims{
			Issuer:    issuer,
			ExpiresAt: time.Now().Add(duration).Unix(),
		},
		KeyID: keyID,
		Data: LoginClaimsData{
			Provider:   u.Provider,
			ID:         u.ID,
			RoleID:     string(u.Role),
			CategoryID: u.Category,
			GroupID:    u.Group,
			Name:       u.Name,
		},
	})

	ss, err := tkn.SignedString([]byte(secret))
	if err != nil {
		return "", fmt.Errorf("sign the token: %w", err)
	}

	return ss, nil
}

func SignRegisterToken(secret string, duration time.Duration, u *model.User) (string, error) {
	tkn := jwt.NewWithClaims(signingMethod, &RegisterClaims{
		TypeClaims: TypeClaims{
			StandardClaims: &jwt.StandardClaims{
				Issuer:    issuer,
				ExpiresAt: time.Now().Add(duration).Unix(),
			},
			KeyID: keyID,
			Type:  TypeRegister,
		},
		Provider:   u.Provider,
		UserID:     u.UID,
		Username:   u.Username,
		CategoryID: u.Category,
		Name:       u.Name,
		Email:      u.Email,
		Photo:      u.Photo,
	})

	ss, err := tkn.SignedString([]byte(secret))
	if err != nil {
		return "", fmt.Errorf("sign the register token: %w", err)
	}

	return ss, nil
}

func SignCallbackToken(secret, prv, cat, redirect string) (string, error) {
	tkn := jwt.NewWithClaims(signingMethod, &CallbackClaims{
		TypeClaims: TypeClaims{
			StandardClaims: &jwt.StandardClaims{
				Issuer: issuer,
				// TODO: This should be maybe configurable
				ExpiresAt: time.Now().Add(10 * time.Minute).Unix(),
			},
			KeyID: keyID,
			Type:  TypeCallback,
		},
		Provider:   prv,
		CategoryID: cat,
		Redirect:   redirect,
	})

	ss, err := tkn.SignedString([]byte(secret))
	if err != nil {
		return "", fmt.Errorf("sign the callback token: %w", err)
	}

	return ss, nil
}

func SignEmailValidationRequiredToken(secret string, u *model.User) (string, error) {
	tkn := jwt.NewWithClaims(signingMethod, &EmailValidationRequiredClaims{
		TypeClaims: TypeClaims{
			StandardClaims: &jwt.StandardClaims{
				Issuer: issuer,
				// TODO: This should be maybe configurable
				ExpiresAt: time.Now().Add(60 * time.Minute).Unix(),
			},
			KeyID: keyID,
			Type:  TypeEmailValidationRequired,
		},
		UserID: u.ID,
	})

	ss, err := tkn.SignedString([]byte(secret))
	if err != nil {
		return "", fmt.Errorf("sign the email validation required token: %w", err)
	}

	return ss, nil
}
