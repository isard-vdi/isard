package token

import (
	"context"
	"errors"
	"fmt"

	"gitlab.com/isard/isardvdi/authentication/model"

	"github.com/golang-jwt/jwt/v5"
	"gopkg.in/rethinkdb/rethinkdb-go.v6"
)

var ErrInvalidToken = errors.New("invalid JWT token")

func parseAuthenticationToken[T jwt.Claims](secret, ss string, claims jwt.Claims) (T, error) {
	var ret T

	tkn, err := jwt.ParseWithClaims(ss, claims, func(tkn *jwt.Token) (interface{}, error) {
		if _, ok := tkn.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", tkn.Header["alg"])
		}

		return []byte(secret), nil
	})
	if err != nil {
		// If the claims were recovered, return them
		if tkn != nil {
			claims, ok := tkn.Claims.(T)
			if ok {
				ret = claims
			}
		}

		return ret, fmt.Errorf("error parsing the JWT token: %w", err)
	}

	if !tkn.Valid {
		return ret, ErrInvalidToken
	}

	ret, ok := tkn.Claims.(T)
	if !ok {
		return ret, ErrInvalidTokenType
	}

	return ret, nil
}

func ParseLoginToken(secret, ss string) (*LoginClaims, error) {
	return parseAuthenticationToken[*LoginClaims](secret, ss, &LoginClaims{})
}

func ParseCallbackToken(secret, ss string) (*CallbackClaims, error) {
	return parseAuthenticationToken[*CallbackClaims](secret, ss, &CallbackClaims{})
}

func ParseRegisterToken(secret, ss string) (*RegisterClaims, error) {
	return parseAuthenticationToken[*RegisterClaims](secret, ss, &RegisterClaims{})
}

func ParseExternalToken(db rethinkdb.QueryExecutor, ss string) (*ExternalClaims, error) {
	tkn, err := jwt.ParseWithClaims(ss, &ExternalClaims{}, func(tkn *jwt.Token) (interface{}, error) {
		if _, ok := tkn.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", tkn.Header["alg"])
		}

		claims, ok := tkn.Claims.(*ExternalClaims)
		if !ok {
			return nil, ErrInvalidTokenType
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
		return nil, ErrInvalidToken
	}

	claims, ok := tkn.Claims.(*ExternalClaims)
	if !ok {
		return claims, ErrInvalidTokenType
	}

	return claims, nil
}

func ParseDisclaimerAcknowledgementRequiredToken(secret, ss string) (*DisclaimerAcknowledgementRequiredClaims, error) {
	return parseAuthenticationToken[*DisclaimerAcknowledgementRequiredClaims](secret, ss, &DisclaimerAcknowledgementRequiredClaims{})
}

func ParseEmailVerificationRequiredToken(secret, ss string) (*EmailVerificationRequiredClaims, error) {
	return parseAuthenticationToken[*EmailVerificationRequiredClaims](secret, ss, &EmailVerificationRequiredClaims{})
}

func ParseEmailVerificationToken(secret, ss string) (*EmailVerificationClaims, error) {
	return parseAuthenticationToken[*EmailVerificationClaims](secret, ss, &EmailVerificationClaims{})
}

func ParsePasswordResetRequiredToken(secret, ss string) (*PasswordResetRequiredClaims, error) {
	return parseAuthenticationToken[*PasswordResetRequiredClaims](secret, ss, &PasswordResetRequiredClaims{})
}

func ParsePasswordResetToken(secret, ss string) (*PasswordResetClaims, error) {
	return parseAuthenticationToken[*PasswordResetClaims](secret, ss, &PasswordResetClaims{})
}

func ParseCategorySelectToken(secret, ss string) (*CategorySelectClaims, error) {
	return parseAuthenticationToken[*CategorySelectClaims](secret, ss, &CategorySelectClaims{})
}
