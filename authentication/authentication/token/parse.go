package token

import (
	"context"
	"errors"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/model"

	"github.com/golang-jwt/jwt"
	"gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func ParseAuthenticationToken(secret, ss string, claims jwt.Claims) (*jwt.Token, error) {
	tkn, err := jwt.ParseWithClaims(ss, claims, func(tkn *jwt.Token) (interface{}, error) {
		if _, ok := tkn.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", tkn.Header["alg"])
		}

		return []byte(secret), nil
	})
	if err != nil {
		return nil, fmt.Errorf("error parsing the JWT token: %w", err)
	}

	if !tkn.Valid {
		return nil, errors.New("invalid JWT token")
	}

	return tkn, nil
}

func ParseExternalToken(db rethinkdb.QueryExecutor, ss string) (*jwt.Token, error) {
	tkn, err := jwt.ParseWithClaims(ss, &ExternalClaims{}, func(tkn *jwt.Token) (interface{}, error) {
		if _, ok := tkn.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", tkn.Header["alg"])
		}

		claims, ok := tkn.Claims.(*ExternalClaims)
		if !ok {
			return nil, errors.New("unexpected claims type")
		}

		secret := &model.Secret{ID: claims.KeyID}
		if err := secret.Load(context.Background(), db); err != nil {
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
