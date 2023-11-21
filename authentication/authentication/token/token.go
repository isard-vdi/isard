package token

import (
	"fmt"

	"github.com/golang-jwt/jwt"
	"gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type Type string

const (
	TypeUnknown                 Type = "unknown"
	TypeLogin                   Type = "login"
	TypeRegister                Type = "register"
	TypeExternal                Type = "external"
	TypeEmailValidationRequired Type = "email-validation-required"
	TypeEmailValidation         Type = "email-validation"
)

type typeClaims struct {
	*jwt.StandardClaims
	Type Type
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

type EmailValidationRequiredClaims struct {
	*jwt.StandardClaims
	KeyID  string `json:"kid"`
	Type   string `json:"type"`
	UserID string `json:"user_id"`
}

type EmailValidationClaims struct {
	*jwt.StandardClaims
	KeyID  string `json:"kid"`
	Type   string `json:"type"`
	UserID string `json:"user_id"`
	Email  string `json:"email"`
}

func VerifyToken(db rethinkdb.QueryExecutor, secret, ss string) (*jwt.Token, Type, error) {
	tkn, _, err := new(jwt.Parser).ParseUnverified(ss, &typeClaims{})
	if err != nil {
		return nil, TypeUnknown, fmt.Errorf("parse the JWT token: %w", err)
	}

	claims := tkn.Claims.(*typeClaims)

	switch claims.Type {
	// Register token
	case TypeRegister:
		tkn, err := ParseAuthenticationToken(secret, ss, &RegisterClaims{})
		if err != nil {
			return nil, TypeUnknown, err
		}

		return tkn, TypeRegister, nil

	// External token
	case TypeExternal:
		tkn, err = ParseExternalToken(db, ss)
		if err != nil {
			return nil, TypeUnknown, err
		}

		return tkn, TypeExternal, nil

	// Login token
	default:
		tkn, err = ParseAuthenticationToken(secret, ss, &LoginClaims{})
		if err != nil {
			return nil, TypeUnknown, err
		}

		return tkn, TypeLogin, nil
	}
}
