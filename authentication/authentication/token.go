package authentication

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/golang-jwt/jwt"
	"gitlab.com/isard/isardvdi/authentication/model"
)

type tokenType string

const (
	tokenTypeUnknown  tokenType = "unknown"
	tokenTypeLogin    tokenType = "login"
	tokenTypeRegister tokenType = "register"
	tokenTypeExternal tokenType = "external"
)

type typeClaims struct {
	*jwt.StandardClaims
	Type tokenType
}

type LoginClaims struct {
	*jwt.StandardClaims
	KeyID string          `json:"kid"`
	Data  LoginClaimsData `json:"data"`
}

type LoginClaimsData struct {
	Provider   string `json:"provider"`
	ID         string `json:"user_id"`
	RoleID     string `json:"role_id"`
	CategoryID string `json:"category_id"`
	GroupID    string `json:"group_id"`
	Name       string `json:"name"`
}

type RegisterClaims struct {
	*jwt.StandardClaims
	KeyID      string `json:"kid"`
	Type       string `json:"type"`
	Provider   string `json:"provider"`
	UserID     string `json:"user_id"`
	Username   string `json:"username"`
	CategoryID string `json:"category_id"`
	Name       string `json:"name"`
	Email      string `json:"email"`
	Photo      string `json:"photo"`
}

type ExternalClaims struct {
	*jwt.StandardClaims
	KeyID    string `json:"kid"`
	Type     string `json:"type"`
	UserID   string `json:"user_id"`
	GroupID  string `json:"group_id"`
	Role     string `json:"role"`
	Username string `json:"username"`
	Name     string `json:"name"`
	Email    string `json:"email"`
	Photo    string `json:"photo"`

	CategoryID string `json:"-"`
}

func (a *Authentication) parseAuthenticationToken(ss string, claims jwt.Claims) (*jwt.Token, error) {
	tkn, err := jwt.ParseWithClaims(ss, claims, func(tkn *jwt.Token) (interface{}, error) {
		if _, ok := tkn.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", tkn.Header["alg"])
		}

		return []byte(a.Secret), nil
	})
	if err != nil {
		return nil, fmt.Errorf("error parsing the JWT token: %w", err)
	}

	if !tkn.Valid {
		return nil, errors.New("invalid JWT token")
	}

	return tkn, nil
}

func (a *Authentication) parseExternalToken(ss string) (*jwt.Token, error) {
	tkn, err := jwt.ParseWithClaims(ss, &ExternalClaims{}, func(tkn *jwt.Token) (interface{}, error) {
		if _, ok := tkn.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", tkn.Header["alg"])
		}

		claims, ok := tkn.Claims.(*ExternalClaims)
		if !ok {
			return nil, errors.New("unexpected claims type")
		}

		secret := &model.Secret{ID: claims.KeyID}
		if err := secret.Load(context.Background(), a.DB); err != nil {
			return nil, fmt.Errorf("load secret from the DB: %w", err)
		}

		claims.CategoryID = secret.CategoryID

		return []byte(secret.Secret), nil
	})

	if err != nil {
		return nil, fmt.Errorf("error parsing the JWT token: %w", err)
	}

	if !tkn.Valid {
		return nil, errors.New("invalid JWT token")
	}

	return tkn, nil
}

func (a *Authentication) verifyToken(ss string) (*jwt.Token, tokenType, error) {
	tkn, _, err := new(jwt.Parser).ParseUnverified(ss, &typeClaims{})
	if err != nil {
		return nil, tokenTypeUnknown, fmt.Errorf("parse the JWT token: %w", err)
	}

	claims := tkn.Claims.(*typeClaims)

	switch claims.Type {
	// Register token
	case tokenTypeRegister:
		tkn, err := a.parseAuthenticationToken(ss, &RegisterClaims{})
		if err != nil {
			return nil, tokenTypeUnknown, err
		}

		return tkn, tokenTypeRegister, nil

	// External token
	case tokenTypeExternal:
		tkn, err = a.parseExternalToken(ss)
		if err != nil {
			return nil, tokenTypeUnknown, err
		}

		return tkn, tokenTypeExternal, nil

	// Login token
	default:
		tkn, err = a.parseAuthenticationToken(ss, &LoginClaims{})
		if err != nil {
			return nil, tokenTypeUnknown, err
		}

		return tkn, tokenTypeLogin, nil
	}
}

func (a *Authentication) signLoginToken(u *model.User) (string, error) {
	tkn := jwt.NewWithClaims(jwt.SigningMethodHS256, &LoginClaims{
		&jwt.StandardClaims{
			Issuer:    "isard-authentication",
			ExpiresAt: time.Now().Add(a.Duration).Unix(),
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

	ss, err := tkn.SignedString([]byte(a.Secret))
	if err != nil {
		return "", fmt.Errorf("sign the token: %w", err)
	}

	return ss, nil
}

func (a *Authentication) signRegisterToken(u *model.User) (string, error) {
	tkn := jwt.NewWithClaims(jwt.SigningMethodHS256, &RegisterClaims{
		&jwt.StandardClaims{
			Issuer:    "isard-authentication",
			ExpiresAt: time.Now().Add(a.Duration).Unix(),
		},
		// TODO: Other signing keys
		"isardvdi",
		string(tokenTypeRegister),
		u.Provider,
		u.UID,
		u.Username,
		u.Category,
		u.Name,
		u.Email,
		u.Photo,
	})

	ss, err := tkn.SignedString([]byte(a.Secret))
	if err != nil {
		return "", fmt.Errorf("sign the register token: %w", err)
	}

	return ss, nil
}
