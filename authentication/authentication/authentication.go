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
	Provider(provider string) provider.Provider
	Login(ctx context.Context, provider string, categoryID string, args map[string]string) (tkn, redirect string, err error)
	Callback(ctx context.Context, args map[string]string) (tkn, redirect string, err error)
	Check(ctx context.Context, tkn string) error
	// Refresh()
	// Register()
}

type Authentication struct {
	Secret    string
	DB        r.QueryExecutor
	providers map[string]provider.Provider
}

func Init(cfg cfg.Authentication, db r.QueryExecutor) *Authentication {
	providers := map[string]provider.Provider{
		"unknown": &provider.Unknown{},
	}

	if cfg.Local {
		local := provider.InitLocal(db)
		providers[local.String()] = local
	}

	if cfg.Google.ClientID != "" && cfg.Google.ClientSecret != "" {
		google := provider.InitGoogle(cfg)
		providers[google.String()] = google
	}

	if cfg.LDAP.Host != "" && cfg.LDAP.BaseDN != "" {
		ldap := provider.InitLDAP(cfg.LDAP)
		providers[ldap.String()] = ldap
	}

	return &Authentication{
		Secret:    cfg.Secret,
		DB:        db,
		providers: providers,
	}
}

func (a *Authentication) Providers() []string {
	providers := []string{}
	for k := range a.providers {
		if k == provider.UnknownString || k == provider.LocalString || k == provider.LDAPString {
			continue
		}

		providers = append(providers, k)
	}

	return providers
}

func (a *Authentication) Provider(p string) provider.Provider {
	prv := a.providers[p]
	if prv == nil {
		return a.providers[provider.UnknownString]
	}

	return prv
}

type Claims struct {
	*jwt.StandardClaims
	KeyID string     `json:"kid"`
	Data  ClaimsData `json:"data"`
}

type ClaimsData struct {
	Provider   string `json:"provider"`
	ID         string `json:"user_id"`
	RoleID     string `json:"role_id"`
	CategoryID string `json:"category_id"`
	GroupID    string `json:"group_id"`
}

func (a *Authentication) signToken(u *model.User) (string, error) {
	tkn := jwt.NewWithClaims(jwt.SigningMethodHS256, &Claims{
		&jwt.StandardClaims{
			Issuer:    "isard-authentication",
			ExpiresAt: time.Now().Add(4 * time.Hour).Unix(),
		},
		// TODO: Other signing keys
		"isardvdi",
		ClaimsData{
			u.Provider,
			u.ID(),
			u.Role,
			u.Category,
			u.Group,
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

const claimsRegisterType = "register"

func (a *Authentication) signRegister(u *model.User) (string, error) {
	tkn := jwt.NewWithClaims(jwt.SigningMethodHS256, &RegisterClaims{
		&jwt.StandardClaims{
			Issuer:    "isard-authentication",
			ExpiresAt: time.Now().Add(4 * time.Hour).Unix(),
		},
		// TODO: Other signing keys
		"isardvdi",
		claimsRegisterType,
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

	// Handle the register flow
	if args[provider.TokenArgsKey] != "" {
		tkn, err := a.parseToken(args[provider.TokenArgsKey], &RegisterClaims{})
		if err != nil {
			return "", "", fmt.Errorf("parse register token: %w", err)
		}

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

		// Normal login flow
	} else {
		p := a.Provider(prv)
		u, redirect, err = p.Login(ctx, categoryID, args)
		if err != nil {
			p = a.Provider(provider.LDAPString)
			if prv != provider.LocalString || !errors.Is(err, provider.ErrInvalidCredentials) || p.String() != provider.LDAPString {
				return "", "", fmt.Errorf("login: %w", err)
			}

			u, redirect, err = p.Login(ctx, categoryID, args)
			if err != nil {
				return "", "", fmt.Errorf("login: %w", err)
			}
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
	tkn, err := a.parseToken(ss, &Claims{})
	if err != nil {
		return err
	}

	_, ok := tkn.Claims.(*Claims)
	if !ok {
		return errors.New("unknown JWT claims format")
	}

	return nil
}
