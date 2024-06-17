package token_test

import (
	"encoding/base64"
	"encoding/json"
	"math"
	"strings"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"

	"github.com/stretchr/testify/assert"
)

func TestSignLoginToken(t *testing.T) {
	assert := assert.New(t)
	now := float64(time.Now().Unix())

	cases := map[string]struct {
		Expiration  time.Time
		SessionID   string
		User        *model.User
		ExpectedErr string
		CheckToken  func(string)
	}{
		"should work as expected": {
			Expiration: time.Now().Add(time.Hour),
			SessionID:  "ThoJuroQueEsUnID",
			User: &model.User{
				ID:                     "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
				UID:                    "nefix",
				Username:               "nefix",
				Password:               "$2y$12$/T3oB8wJOkA1Aq0A02ofL.dfVkGBr.08MnPdBNJP0gl/9OeumzTTm", // f0kt3Rf$
				Provider:               "local",
				Active:                 true,
				Category:               "default",
				Role:                   "user",
				Group:                  "default-default",
				Name:                   "Néfix Estrada",
				Email:                  "nefix@example.org",
				EmailVerified:          &now,
				DisclaimerAcknowledged: true,
			},
			CheckToken: func(ss string) {
				// Ensure the JWT token has 3 parts (type, claims, and signature)
				parts := strings.Split(ss, ".")
				assert.Len(parts, 3)

				// Decode the claims to a JSON
				b, err := base64.RawURLEncoding.DecodeString(parts[1])
				assert.NoError(err)

				claims := map[string]any{}
				err = json.Unmarshal(b, &claims)
				assert.NoError(err)

				// Exctract the time fields
				round, frac := math.Modf(claims["exp"].(float64))
				exp := time.Unix(int64(round), int64(frac*1e9))

				round, frac = math.Modf(claims["iat"].(float64))
				iat := time.Unix(int64(round), int64(frac*1e9))

				round, frac = math.Modf(claims["nbf"].(float64))
				nbf := time.Unix(int64(round), int64(frac*1e9))

				// Ensure time vaildity
				assert.True(time.Now().Before(exp))
				assert.True(time.Now().After(iat))
				assert.True(time.Now().After(nbf))

				claims["exp"] = nil
				claims["iat"] = nil
				claims["nbf"] = nil

				assert.Equal(map[string]any{
					"kid":        "isardvdi",
					"iss":        "isard-authentication",
					"sub":        "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
					"exp":        nil,
					"iat":        nil,
					"nbf":        nil,
					"session_id": "ThoJuroQueEsUnID",
					"data": map[string]any{
						"provider":    "local",
						"user_id":     "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
						"role_id":     "user",
						"category_id": "default",
						"group_id":    "default-default",
						"name":        "Néfix Estrada",
					},
				}, claims)
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ss, err := token.SignLoginToken("", tc.Expiration, tc.SessionID, tc.User)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.CheckToken != nil {
				tc.CheckToken(ss)
			}
		})
	}
}

func TestSignPasswordResetToken(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		UserID      string
		ExpectedErr string
		CheckToken  func(string)
	}{
		"should work as expected": {
			UserID: "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
			CheckToken: func(ss string) {
				// Ensure the JWT token has 3 parts (type, claims, and signature)
				parts := strings.Split(ss, ".")
				assert.Len(parts, 3)

				// Decode the claims to a JSON
				b, err := base64.RawURLEncoding.DecodeString(parts[1])
				assert.NoError(err)

				claims := map[string]any{}
				err = json.Unmarshal(b, &claims)
				assert.NoError(err)

				// Exctract the time fields
				round, frac := math.Modf(claims["exp"].(float64))
				exp := time.Unix(int64(round), int64(frac*1e9))

				round, frac = math.Modf(claims["iat"].(float64))
				iat := time.Unix(int64(round), int64(frac*1e9))

				round, frac = math.Modf(claims["nbf"].(float64))
				nbf := time.Unix(int64(round), int64(frac*1e9))

				// Ensure time vaildity
				assert.True(time.Now().Before(exp))
				assert.True(time.Now().After(iat))
				assert.True(time.Now().After(nbf))

				claims["exp"] = nil
				claims["iat"] = nil
				claims["nbf"] = nil

				assert.Equal(map[string]any{
					"kid":     "isardvdi",
					"iss":     "isard-authentication",
					"exp":     nil,
					"iat":     nil,
					"nbf":     nil,
					"type":    "password-reset",
					"user_id": "08fff46e-cbd3-40d2-9d8e-e2de7a8da654",
				}, claims)
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ss, err := token.SignPasswordResetToken("", tc.UserID)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.CheckToken != nil {
				tc.CheckToken(ss)
			}
		})
	}
}

func TestSignCategorySelectToken(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		Categories  []*model.Category
		User        *types.ProviderUserData
		ExpectedErr string
		CheckToken  func(string)
	}{
		"should work as expected": {
			Categories: []*model.Category{
				{
					ID:          "HolaMelina:)",
					Name:        "Bon dia, Melina",
					Description: "Description test",
					// Photo: "https://clipground.com/images/potato-emoji-clipart-9.jpg",
				},
			},
			User: &types.ProviderUserData{
				Provider: "SAML",
				Category: "Test cat",
				UID:      "0000000",
			},
			CheckToken: func(ss string) {
				// Ensure the JWT token has 3 parts (type, claims, and signature)
				parts := strings.Split(ss, ".")
				assert.Len(parts, 3)

				// Decode the claims to a JSON
				b, err := base64.RawURLEncoding.DecodeString(parts[1])
				assert.NoError(err)

				claims := map[string]any{}
				err = json.Unmarshal(b, &claims)
				assert.NoError(err)

				// Exctract the time fields
				round, frac := math.Modf(claims["exp"].(float64))
				exp := time.Unix(int64(round), int64(frac*1e9))

				round, frac = math.Modf(claims["iat"].(float64))
				iat := time.Unix(int64(round), int64(frac*1e9))

				round, frac = math.Modf(claims["nbf"].(float64))
				nbf := time.Unix(int64(round), int64(frac*1e9))

				// Ensure time vaildity
				assert.True(time.Now().Before(exp))
				assert.True(time.Now().After(iat))
				assert.True(time.Now().After(nbf))

				claims["exp"] = nil
				claims["iat"] = nil
				claims["nbf"] = nil

				assert.Equal(map[string]any{
					"kid":  "isardvdi",
					"iss":  "isard-authentication",
					"exp":  nil,
					"iat":  nil,
					"nbf":  nil,
					"type": "category-select",
					"categories": []any{
						map[string]any{
							"id":    "HolaMelina:)",
							"name":  "Bon dia, Melina",
							"photo": "",
							// Photo: "https://clipground.com/images/potato-emoji-clipart-9.jpg",
						},
					},
					"user": map[string]any{
						"provider": "SAML",
						"category": "Test cat",
						"uid":      "0000000",
					},
				}, claims)
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			ss, err := token.SignCategorySelectToken("", tc.Categories, tc.User)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			if tc.CheckToken != nil {
				tc.CheckToken(ss)
			}
		})
	}
}
