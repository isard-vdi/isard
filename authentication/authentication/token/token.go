package token

import (
	"errors"
	"fmt"

	"github.com/golang-jwt/jwt"
	"gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type Type string

const (
	TypeUnknown                 Type = "unknown"
	TypeLogin                   Type = "login"
	TypeCallback                Type = "callback"
	TypeRegister                Type = "register"
	TypeExternal                Type = "external"
	TypeEmailValidationRequired Type = "email-validation-required"
	TypeEmailValidation         Type = "email-validation"
)

type TypeClaims struct {
	*jwt.StandardClaims
	KeyID string `json:"kid"`
	Type  Type   `json:"type"`
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

type CallbackClaims struct {
	TypeClaims
	Provider   string `json:"provider"`
	CategoryID string `json:"category_id"`
	Redirect   string `json:"redirect"`
}

type RegisterClaims struct {
	TypeClaims
	Provider   string `json:"provider"`
	UserID     string `json:"user_id"`
	Username   string `json:"username"`
	CategoryID string `json:"category_id"`
	Name       string `json:"name"`
	Email      string `json:"email"`
	Photo      string `json:"photo"`
}

type ExternalClaims struct {
	TypeClaims
	UserID   string `json:"user_id"`
	GroupID  string `json:"group_id"`
	Role     string `json:"role"`
	Username string `json:"username"`
	Name     string `json:"name"`
	Email    string `json:"email"`
	Photo    string `json:"photo"`

	CategoryID string `json:"-"`
}

type EmailValidationRequiredClaims struct {
	TypeClaims
	UserID string `json:"user_id"`
}

type EmailValidationClaims struct {
	TypeClaims
	UserID string `json:"user_id"`
	Email  string `json:"email"`
}

func VerifyToken(db rethinkdb.QueryExecutor, secret, ss string) (*jwt.Token, Type, error) {
	tkn, _, err := new(jwt.Parser).ParseUnverified(ss, &TypeClaims{})
	if err != nil {
		return nil, TypeUnknown, fmt.Errorf("parse the JWT token: %w", err)
	}

	claims := tkn.Claims.(*TypeClaims)

	switch typ := claims.Type; typ {
	// Register token
	case TypeRegister:
		tkn, err := ParseAuthenticationToken(secret, ss, &RegisterClaims{})
		if err != nil {
			return nil, TypeUnknown, err
		}

		return tkn, typ, nil

	// Callback token
	case TypeCallback:
		tkn, err := ParseAuthenticationToken(secret, ss, &CallbackClaims{})
		if err != nil {
			return nil, TypeUnknown, err
		}

		return tkn, typ, nil

	// External token
	case TypeExternal:
		tkn, err := ParseExternalToken(db, ss)
		if err != nil {
			return nil, TypeUnknown, err
		}

		return tkn, typ, nil

	// Email validation required token
	case TypeEmailValidationRequired:
		tkn, err := ParseAuthenticationToken(secret, ss, &EmailValidationRequiredClaims{})
		if err != nil {
			return nil, TypeUnknown, err
		}

		return tkn, typ, nil

	// TODO: This should be replaced by type = "login"
	// Login token
	case "":
		tkn, err = ParseAuthenticationToken(secret, ss, &LoginClaims{})
		if err != nil {
			return nil, TypeUnknown, err
		}

		return tkn, TypeLogin, nil

	default:
		return nil, TypeUnknown, errors.New("unknown token type")
	}
}
