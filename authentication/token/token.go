package token

import (
	"errors"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/provider/types"

	"github.com/golang-jwt/jwt/v5"
)

var ErrInvalidTokenType = errors.New("invalid token type")
var ErrInvalidTokenRole = errors.New("invalid token role")
var ErrInvalidTokenCategory = errors.New("invalid token category")

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
	TypePasswordReset                     Type = "password-reset"
	TypeCategorySelect                    Type = "category-select"
	TypeUserMigrationRequired             Type = "user-migration-required"
	TypeUserMigration                     Type = "user-migration"
)

type TypeClaims struct {
	*jwt.RegisteredClaims
	KeyID string `json:"kid"`
	Type  Type   `json:"type"`
}

type LoginClaims struct {
	*jwt.RegisteredClaims
	KeyID     string          `json:"kid"`
	Type      Type            `json:"type,omitempty"`
	SessionID string          `json:"session_id"`
	Data      LoginClaimsData `json:"data"`
}

type LoginClaimsData struct {
	Provider   string `json:"provider"`
	ID         string `json:"user_id"`
	RoleID     string `json:"role_id"`
	CategoryID string `json:"category_id"`
	GroupID    string `json:"group_id"`
	Name       string `json:"name"`
}

func (c LoginClaims) Validate() error {
	// TODO: The empty type should be eventually removed
	if c.Type != TypeLogin && c.Type != "" {
		return ErrInvalidTokenType
	}

	return nil
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
	Role     string `json:"role_id"`
	Username string `json:"username"`
	Name     string `json:"name"`
	Email    string `json:"email"`
	Photo    string `json:"photo"`
	Domain   string `json:"domain"`

	CategoryID string `json:"category_id"`
}

func (c ExternalClaims) Validate() error {
	if c.Type != TypeExternal {
		return ErrInvalidTokenType
	}

	return nil
}

type ApiKeyClaims struct {
	TypeClaims
	SessionID string           `json:"session_id"`
	Data      ApiKeyClaimsData `json:"data"`
}

type ApiKeyClaimsData struct {
	Provider   string `json:"provider"`
	ID         string `json:"user_id"`
	RoleID     string `json:"role_id"`
	CategoryID string `json:"category_id"`
	GroupID    string `json:"group_id"`
	Name       string `json:"name"`
}

func (c ApiKeyClaims) Validate() error {
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

type PasswordResetClaims struct {
	TypeClaims
	UserID string `json:"user_id"`
}

func (c PasswordResetClaims) Validate() error {
	if c.Type != TypePasswordReset {
		return ErrInvalidTokenType
	}

	return nil
}

type CategorySelectClaims struct {
	TypeClaims
	Categories []CategorySelectClaimsCategory `json:"categories"`
	User       types.ProviderUserData         `json:"user"`
}

type CategorySelectClaimsCategory struct {
	ID    string `json:"id"`
	Name  string `json:"name"`
	Photo string `json:"photo"`
}

func (c CategorySelectClaims) Validate() error {
	if c.Type != TypeCategorySelect {
		return ErrInvalidTokenType
	}

	return nil
}

type UserMigrationRequiredClaims struct {
	TypeClaims
	UserID string `json:"user_id"`
}

func (u UserMigrationRequiredClaims) Validate() error {
	if u.Type != TypeUserMigrationRequired {
		return ErrInvalidTokenType
	}

	return nil
}

type UserMigrationClaims struct {
	TypeClaims
	UserID string `json:"user_id"`
}

func (u UserMigrationClaims) Validate() error {
	if u.Type != TypeUserMigration {
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
		TypePasswordResetRequired,
		TypePasswordReset,
		TypeCategorySelect,
		TypeUserMigrationRequired,
		TypeUserMigration:

		return claims.Type, nil

	// TODO: This should be replaced by type = "login"
	// Login token
	case TypeLogin, "":
		return TypeLogin, nil

	default:
		return TypeUnknown, errors.New("unknown token type")
	}
}

func TokenIsIsardvdiService(secret, ss string) error {
	tkn, err := ParseLoginToken(secret, ss)
	if err != nil {
		return err
	}

	if tkn.SessionID != "isardvdi-service" {
		return ErrInvalidTokenType
	}

	return nil
}
