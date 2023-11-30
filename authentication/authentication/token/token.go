package token

import (
	"errors"
	"fmt"

	"github.com/golang-jwt/jwt/v5"
)

var ErrInvalidTokenType = errors.New("invalid token type")

type Type string

const (
	TypeUnknown                           Type = "unknown"
	TypeLogin                             Type = "login"
	TypeCallback                          Type = "callback"
	TypeRegister                          Type = "register"
	TypeExternal                          Type = "external"
	TypeDisclaimerAcknowledgementRequired Type = "disclaimer-acknowledgement-required"
	TypeEmailVerificationRequired         Type = "email-verification-required"
	TypeEmailVerification                 Type = "email-verification"
	TypePasswordResetRequired             Type = "password-reset-required"
)

type TypeClaims struct {
	*jwt.RegisteredClaims
	KeyID string `json:"kid"`
	Type  Type   `json:"type"`
}

type LoginClaims struct {
	*jwt.RegisteredClaims
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

func (c CallbackClaims) Validate() error {
	if c.Type != TypeCallback {
		return ErrInvalidTokenType
	}

	return nil
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

func (c RegisterClaims) Validate() error {
	if c.Type != TypeRegister {
		return ErrInvalidTokenType
	}

	return nil
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

func (c ExternalClaims) Validate() error {
	if c.Type != TypeExternal {
		return ErrInvalidTokenType
	}

	return nil
}

type DisclaimerAcknowledgementRequiredClaims struct {
	TypeClaims
	UserID string `json:"user_id"`
}

func (c DisclaimerAcknowledgementRequiredClaims) Validate() error {
	if c.Type != TypeDisclaimerAcknowledgementRequired {
		return ErrInvalidTokenType
	}

	return nil
}

type EmailVerificationRequiredClaims struct {
	TypeClaims
	UserID       string `json:"user_id"`
	CategoryID   string `json:"category_id"`
	CurrentEmail string `json:"current_email"`
}

func (c EmailVerificationRequiredClaims) Validate() error {
	if c.Type != TypeEmailVerificationRequired {
		return ErrInvalidTokenType
	}

	return nil
}

type EmailVerificationClaims struct {
	TypeClaims
	UserID string `json:"user_id"`
	Email  string `json:"email"`
}

func (c EmailVerificationClaims) Validate() error {
	if c.Type != TypeEmailVerification {
		return ErrInvalidTokenType
	}

	return nil
}

type PasswordResetRequiredClaims struct {
	TypeClaims
	UserID string `json:"user_id"`
}

func (c PasswordResetRequiredClaims) Validate() error {
	if c.Type != TypePasswordResetRequired {
		return ErrInvalidTokenType
	}

	return nil
}

func GetTokenType(ss string) (Type, error) {
	tkn, _, err := new(jwt.Parser).ParseUnverified(ss, &TypeClaims{})
	if err != nil {
		return TypeUnknown, fmt.Errorf("parse the JWT token: %w", err)
	}

	claims := tkn.Claims.(*TypeClaims)

	switch claims.Type {
	case TypeCallback,
		TypeRegister,
		TypeExternal,
		TypeDisclaimerAcknowledgementRequired,
		TypeEmailVerificationRequired,
		TypeEmailVerification,
		TypePasswordResetRequired:

		return claims.Type, nil

	// TODO: This should be replaced by type = "login"
	// Login token
	case "":
		return TypeLogin, nil

	default:
		return TypeUnknown, errors.New("unknown token type")
	}
}
