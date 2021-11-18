package authentication

import (
	"context"
	"errors"
	"fmt"
	"time"

	"gitlab.com/isard/isardvdi/authentication/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"

	"github.com/golang-jwt/jwt"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type Interface interface {
	Providers() []string
	ShowAdminButton() bool
	Provider(provider string) provider.Provider
	Login(ctx context.Context, provider string, categoryID string, args map[string]string) (tkn, redirect string, err error)
	Callback(ctx context.Context, args map[string]string) (tkn, redirect string, err error)
	Check(ctx context.Context, tkn string) error
	// Refresh()
	// Register()
}

type Authentication struct {
	Secret          string
	DB              r.QueryExecutor
	providers       map[string]provider.Provider
	showAdminButton bool
}

func Init(cfg cfg.Cfg, db r.QueryExecutor) *Authentication {
	providers := map[string]provider.Provider{
		provider.UnknownString: &provider.Unknown{},
		provider.FormString:    provider.InitForm(cfg.Authentication, db),
	}

	if cfg.Authentication.Google.Enabled {
		google := provider.InitGoogle(cfg.Authentication)
		providers[google.String()] = google
	}

	return &Authentication{
		Secret:          cfg.Authentication.Secret,
		DB:              db,
		providers:       providers,
		showAdminButton: cfg.ShowAdminButton,
	}
}

func (a *Authentication) Providers() []string {
	providers := []string{}
	for k := range a.providers {
		if k == provider.UnknownString || k == provider.FormString {
			continue
		}

		providers = append(providers, k)
	}

	return providers
}

func (a *Authentication) ShowAdminButton() bool {
	return a.showAdminButton
}

func (a *Authentication) Provider(p string) provider.Provider {
	prv := a.providers[p]
	if prv == nil {
		return a.providers[provider.UnknownString]
	}

	return prv
}

type tokenType string

const (
	tokenTypeUnknown  tokenType = "unknown"
	tokenTypeLogin    tokenType = "login"
	tokenTypeRegister tokenType = "register"
)

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

func (a *Authentication) signToken(u *model.User) (string, error) {
	tkn := jwt.NewWithClaims(jwt.SigningMethodHS256, &LoginClaims{
		&jwt.StandardClaims{
			Issuer:    "isard-authentication",
			ExpiresAt: time.Now().Add(4 * time.Hour).Unix(),
		},
		// TODO: Other signing keys
		"isardvdi",
		LoginClaimsData{
			u.Provider,
			u.ID(),
			u.Role,
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

func (a *Authentication) parseToken(ss string, claims jwt.Claims) (*jwt.Token, error) {
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

func (a *Authentication) getTokenType(ss string) (*jwt.Token, tokenType, error) {
	// Register token
	tkn, err := a.parseToken(ss, &RegisterClaims{})
	if err == nil {
		claims, ok := tkn.Claims.(*RegisterClaims)
		if ok && claims.Type == string(tokenTypeRegister) {
			return tkn, tokenTypeRegister, nil
		}

	} else {
		var e *jwt.ValidationError
		if !errors.As(err, &e) || e.Errors != jwt.ValidationErrorClaimsInvalid {
			return nil, tokenTypeUnknown, err
		}
	}

	// Login token
	tkn, err = a.parseToken(ss, &LoginClaims{})
	if err == nil {
		return tkn, tokenTypeLogin, nil
	} else {
		var e *jwt.ValidationError
		if !errors.As(err, &e) || e.Errors != jwt.ValidationErrorClaimsInvalid {
			return nil, tokenTypeUnknown, err
		}
	}

	return nil, tokenTypeUnknown, errors.New("unknown token type")
}

func (a *Authentication) signRegister(u *model.User) (string, error) {
	tkn := jwt.NewWithClaims(jwt.SigningMethodHS256, &RegisterClaims{
		&jwt.StandardClaims{
			Issuer:    "isard-authentication",
			ExpiresAt: time.Now().Add(4 * time.Hour).Unix(),
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

func (a *Authentication) Login(ctx context.Context, prv, categoryID string, args map[string]string) (string, string, error) {
	var u *model.User
	var redirect string
	var err error

	// Check if the user sends a token
	if args[provider.TokenArgsKey] != "" {
		tkn, tknType, err := a.getTokenType(args[provider.TokenArgsKey])
		if err == nil {
			switch tknType {
			case tokenTypeRegister:
				register, ok := tkn.Claims.(*RegisterClaims)
				if !ok {
					return "", "", errors.New("invalid register token")
				}

				u = &model.User{
					Provider: register.Provider,
					Category: register.CategoryID,
					UID:      register.UserID,
					Username: register.Username,
				}
				if err := u.Load(ctx, a.DB); err != nil {
					if errors.Is(err, model.ErrNotFound) {
						return "", "", errors.New("user not registered")
					}

					return "", "", fmt.Errorf("load user from db: %w", err)
				}

				ss, err := a.signToken(u)
				if err != nil {
					return "", "", err
				}

				return ss, redirect, nil
			}
		}
	}

	p := a.Provider(prv)
	u, redirect, err = p.Login(ctx, categoryID, args)
	if err != nil {
		return "", "", fmt.Errorf("login: %w", err)
	}

	if redirect != "" {
		return "", redirect, nil
	}

	exists, err := u.Exists(ctx, a.DB)
	if err != nil {
		return "", "", fmt.Errorf("check if user exists: %w", err)
	}

	if !exists {
		// If the user has logged in correctly, but doesn't exist in the DB, they have to register first!
		ss, err := a.signRegister(u)
		return ss, "", err
	}

	if err := u.Load(ctx, a.DB); err != nil {
		return "", "", fmt.Errorf("load user from DB: %w", err)
	}

	ss, err := a.signToken(u)
	if err != nil {
		return "", "", err
	}

	return ss, redirect, nil
}

func (a *Authentication) Callback(ctx context.Context, args map[string]string) (string, string, error) {
	ss := args["state"]
	if ss == "" {
		return "", "", errors.New("callback state not provided")
	}

	tkn, err := a.parseToken(ss, &provider.CallbackClaims{})
	if err != nil {
		return "", "", fmt.Errorf("parse callback state: %w", err)
	}

	claims, ok := tkn.Claims.(*provider.CallbackClaims)
	if !ok {
		return "", "", errors.New("unknown callback state claims format")
	}

	p := a.Provider(claims.Provider)

	u, redirect, err := p.Callback(ctx, claims, args)
	if err != nil {
		return "", "", fmt.Errorf("callback: %w", err)
	}

	exists, err := u.Exists(ctx, a.DB)
	if err != nil {
		return "", "", fmt.Errorf("check if user exists: %w", err)
	}

	if exists {
		if err := u.Load(ctx, a.DB); err != nil {
			return "", "", fmt.Errorf("load user from DB: %w", err)
		}

		ss, err = a.signToken(u)
		if err != nil {
			return "", "", err
		}
	} else {
		ss, err = a.signRegister(u)
		if err != nil {
			return "", "", err
		}
	}

	if redirect == "" {
		redirect = claims.Redirect
	}

	return ss, redirect, nil
}

func (a *Authentication) Check(ctx context.Context, ss string) error {
	tkn, err := a.parseToken(ss, &LoginClaims{})
	if err != nil {
		return err
	}

	_, ok := tkn.Claims.(*LoginClaims)
	if !ok {
		return errors.New("unknown JWT claims format")
	}

	return nil
}
