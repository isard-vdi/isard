package http

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/authentication/authentication"
	"gitlab.com/isard/isardvdi/authentication/limits"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"
	"gitlab.com/isard/isardvdi/pkg/db"
	oasAuthentication "gitlab.com/isard/isardvdi/pkg/gen/oas/authentication"

	"github.com/crewjam/saml/samlsp"
	"github.com/golang-jwt/jwt/v5"
	"github.com/jellydator/ttlcache/v3"
	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi-sdk-go"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"
)

var _ oasAuthentication.Handler = &AuthenticationServer{}

const healthcheckCacheKey = "healthcheck"

type AuthenticationServer struct {
	Addr           string
	Authentication authentication.Interface

	healthcheckCache *ttlcache.Cache[string, error]

	Log *zerolog.Logger
	WG  *sync.WaitGroup
}

func Serve(ctx context.Context, wg *sync.WaitGroup, log *zerolog.Logger, addr string, auth authentication.Interface) {
	a := &AuthenticationServer{
		Addr:           addr,
		Authentication: auth,
		healthcheckCache: ttlcache.New[string, error](
			// Set the cache duration to 30 seconds
			ttlcache.WithTTL[string, error](30*time.Second),
			// Disable the time extension when getting the values
			ttlcache.WithDisableTouchOnHit[string, error](),
		),
		Log: log,
		WG:  wg,
	}

	// Start the cache eviction process
	go a.healthcheckCache.Start()

	sec := &SecurityHandler{}

	// TODO: Security handler
	oas, err := oasAuthentication.NewServer(
		a,
		sec,
		oasAuthentication.WithMiddleware(
			RequestMetadataOAS,
			Logging(log),
		),
	)
	if err != nil {
		log.Fatal().Err(err).Msg("create the OpenAPI authentication server")
	}

	m := http.NewServeMux()

	// Observability endpoints
	m.Handle("/healthcheck", requestMetadataHandler(http.HandlerFunc(a.healthcheck)))

	// SAML authentication
	m.Handle("/authentication/saml/login", requestMetadataHandler(http.HandlerFunc(a.loginSAML)))
	m.Handle("/authentication/saml/metadata", requestMetadataHandler(http.HandlerFunc(a.Authentication.SAML().ServeMetadata)))
	m.Handle("/authentication/saml/acs", requestMetadataHandler(http.HandlerFunc(a.Authentication.SAML().ServeACS)))
	m.Handle("/authentication/saml/slo", requestMetadataHandler(http.HandlerFunc(a.logoutSAML)))

	// The OpenAPI specification server
	m.Handle("/authentication/", http.StripPrefix("/authentication", oas))

	s := http.Server{
		Addr:    a.Addr,
		Handler: m,
	}

	go func() {
		if err := s.ListenAndServe(); err != nil {
			log.Fatal().Err(err).Str("addr", addr).Msg("serve http")
		}
	}()

	<-ctx.Done()

	timeout, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	s.Shutdown(timeout)
	a.healthcheckCache.Stop()

	a.WG.Done()
}

func (a *AuthenticationServer) healthcheck(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.WriteHeader(http.StatusBadRequest)
		return
	}

	status := a.healthcheckCache.Get(healthcheckCacheKey)
	if status == nil || status.IsExpired() {
		err := a.Authentication.Healthcheck()

		status = a.healthcheckCache.Set(healthcheckCacheKey, err, ttlcache.DefaultTTL)
	}

	if status.Value() != nil {
		w.WriteHeader(http.StatusServiceUnavailable)
		return
	}

	w.WriteHeader(http.StatusOK)
}

func (a *AuthenticationServer) loginSAML(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.WriteHeader(http.StatusMethodNotAllowed)
		w.Write([]byte("method not allowed"))
		return
	}

	// Get the login parameters
	var provider oasAuthentication.Providers
	if err := provider.UnmarshalText([]byte(r.URL.Query().Get("provider"))); err != nil {
		w.WriteHeader(http.StatusBadRequest)
		w.Write([]byte("invalid provider"))
		return
	}

	categoryID := r.URL.Query().Get("category_id")

	redirect := oasAuthentication.OptString{}
	if red := r.URL.Query().Get("redirect"); red != "" {
		redirect = oasAuthentication.NewOptString(red)
	}

	var tkn oasAuthentication.OptString
	c, _ := r.Cookie("token")
	if c != nil {
		tkn = oasAuthentication.NewOptString(c.Value)
	}

	// Ensure the user has logged in through SAML
	a.Authentication.SAML().RequireAccount(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Call the login function with the correct parameters
		rsp, err := a.Login(r.Context(), oasAuthentication.OptLoginRequestMultipart{}, oasAuthentication.LoginParams{
			Provider:   provider,
			CategoryID: categoryID,
			Redirect:   redirect,
			Token:      tkn,
		})
		if err != nil {
			a.Log.Error().Err(err).Msg("SAML login error")
			w.WriteHeader(http.StatusInternalServerError)
			w.Write([]byte("internal server error"))
			return
		}

		switch t := rsp.(type) {
		case *oasAuthentication.LoginFound:
			w.Header().Add("Authorization", t.Authorization)

			if t.SetCookie.Set {
				w.Header().Set("Set-Cookie", t.SetCookie.Value)
			}

			http.Redirect(w, r, t.Location, http.StatusFound)
			return

		case *oasAuthentication.LoginOKHeaders:
			w.Header().Add("Authorization", t.Authorization)
			w.Header().Set("Set-Cookie", t.SetCookie)

			w.WriteHeader(http.StatusOK)
			b, err := io.ReadAll(t.Response.Data)
			if err == nil {
				w.Write(b)
			}

		default:
			// TODO: This shouldn't really be here...
			w.WriteHeader(http.StatusInternalServerError)
			w.Write([]byte("internal server error"))
			return
		}

	})).ServeHTTP(w, r)
}

func (a *AuthenticationServer) logoutSAML(w http.ResponseWriter, r *http.Request) {
	if err := a.Authentication.SAML().Session.DeleteSession(w, r); err != nil {
		a.Log.Error().Err(err).Msg("delete SAML session")

		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte("internal server error"))
		return
	}

	// TODO: This should be an endpoint to logout
	http.Redirect(w, r, "/", http.StatusFound)
}

func (a *AuthenticationServer) Login(ctx context.Context, req oasAuthentication.OptLoginRequestMultipart, params oasAuthentication.LoginParams) (oasAuthentication.LoginRes, error) {
	// Remote address is injected in the RequestMetadata middleware
	remoteAddr := ctx.Value(requestMetadataRemoteAddrCtxKey).(string)

	args := provider.LoginArgs{}

	// Token provided in the Authorization header
	tkn, ok := ctx.Value(tokenCtxKey).(string)
	if ok {
		args.Token = &tkn
	}

	// Redirect the user after login
	if params.Redirect.Set {
		args.Redirect = &params.Redirect.Value
	}

	// Form parameters (username + password)
	if req.Set && req.Value.Username.Set {
		args.FormUsername = &req.Value.Username.Value
	}

	if req.Set && req.Value.Password.Set {
		args.FormPassword = &req.Value.Password.Value
	}

	log := a.Log.With().Str("provider", string(params.Provider)).Logger()

	p := a.Authentication.Provider(string(params.Provider))
	if p.String() == types.ProviderSAML {
		c := &http.Cookie{
			Name:  "token",
			Value: params.Token.Value,
		}
		r := &http.Request{
			Header: http.Header{
				"Cookie": []string{c.String()},
			},
		}

		if _, err := a.Authentication.SAML().Session.GetSession(r); err != nil {
			if !errors.Is(err, samlsp.ErrNoSession) {
				log.Error().Err(err).Msg("unknown error")

				return nil, provider.ErrInternal
			}

			// Prepeare the redirection
			q := url.Values{}
			q.Add("provider", string(params.Provider))
			q.Add("category_id", params.CategoryID)
			if params.Redirect.Set {
				q.Add("redirect", params.Redirect.Value)
			}

			u, _ := url.Parse("/authentication/saml/login")
			u.RawQuery = q.Encode()

			// Redirect to the correct SAML endpoint
			return &oasAuthentication.LoginFound{
				Location: u.String(),
			}, nil
		}
	}

	tkn, redirect, err := a.Authentication.Login(ctx, p.String(), params.CategoryID, args, remoteAddr)
	if err != nil {
		if errors.Is(err, provider.ErrInvalidCredentials) {
			return &oasAuthentication.LoginUnauthorized{
				Error: oasAuthentication.LoginErrorErrorInvalidCredentials,
				Msg:   provider.ErrInvalidCredentials.Error(),
			}, nil
		}

		if errors.Is(err, provider.ErrUserDisabled) {
			return &oasAuthentication.LoginForbidden{
				Error: oasAuthentication.LoginErrorErrorUserDisabled,
				Msg:   provider.ErrUserDisabled.Error(),
			}, nil
		}

		if errors.Is(err, provider.ErrUserDisallowed) {
			return &oasAuthentication.LoginForbidden{
				Error: oasAuthentication.LoginErrorErrorUserDisallowed,
				Msg:   provider.ErrUserDisallowed.Error(),
			}, nil
		}

		var rateLimitErr *limits.RateLimitError
		if errors.As(err, &rateLimitErr) {
			retryAfter := rateLimitErr.RetryAfter.UTC().Format(http.TimeFormat)

			return &oasAuthentication.LoginTooManyRequestsHeaders{
				RetryAfter: retryAfter,
				Response: oasAuthentication.LoginTooManyRequests{
					Data: bytes.NewBufferString("Retry after: " + retryAfter),
				},
			}, nil
		}

		// If it's a provider error, return the user-facing error
		var prvErr *provider.ProviderError
		if errors.As(err, &prvErr) {
			log.Error().Err(err).Msg("provider error")
			return nil, prvErr.User
		}

		log.Error().Err(err).Msg("unknown error")
		return nil, provider.ErrInternal
	}

	c := &http.Cookie{
		Name:    "authorization",
		Path:    "/",
		Value:   tkn,
		Expires: time.Now().Add(5 * time.Minute),
	}
	cookie := c.String()

	if redirect != "" {
		return &oasAuthentication.LoginFound{
			Location:      redirect,
			Authorization: fmt.Sprintf("Bearer %s", tkn),
			SetCookie:     oasAuthentication.NewOptString(cookie),
		}, nil
	}

	return &oasAuthentication.LoginOKHeaders{
		Authorization: fmt.Sprintf("Bearer %s", tkn),
		SetCookie:     cookie,
		Response: oasAuthentication.LoginOK{
			Data: bytes.NewReader([]byte(tkn)),
		},
	}, nil
}

func (a *AuthenticationServer) Callback(ctx context.Context, params oasAuthentication.CallbackParams) (oasAuthentication.CallbackRes, error) {
	// Remote address is injected in the RequestMetadata middleware
	remoteAddr := ctx.Value(requestMetadataRemoteAddrCtxKey).(string)

	args := provider.CallbackArgs{}

	// OAuth2
	if params.Code.Set {
		args.Oauth2Code = &params.Code.Value
	}

	// SAML
	if params.Token.Set {
		c := &http.Cookie{
			Name:  "token",
			Value: params.Token.Value,
		}

		ctx = context.WithValue(ctx, provider.HTTPRequest, &http.Request{
			Header: http.Header{
				"Cookie": []string{c.String()},
			},
		})
	}

	tkn, redirect, err := a.Authentication.Callback(ctx, params.State, args, remoteAddr)
	if err != nil {
		if errors.Is(err, provider.ErrUserDisabled) {
			return &oasAuthentication.CallbackFound{
				Location: "/login?error=user_disabled",
			}, nil
		}

		if errors.Is(err, provider.ErrUserDisallowed) {
			return &oasAuthentication.CallbackFound{
				Location: "/login?error=user_disallowed",
			}, nil
		}

		// If it's a provider error, return the user-facing error
		var prvErr *provider.ProviderError
		if errors.As(err, &prvErr) {
			a.Log.Error().Err(err).Msg("provider error")
			return nil, prvErr.User
		}

		a.Log.Error().Err(err).Msg("unknown callback error")
		return nil, provider.ErrInternal
	}

	c := &http.Cookie{
		Name:    "authorization",
		Path:    "/",
		Value:   tkn,
		Expires: time.Now().Add(5 * time.Minute),
	}
	cookie := c.String()

	if redirect != "" {
		return &oasAuthentication.CallbackFound{
			Location:      redirect,
			Authorization: fmt.Sprintf("Bearer %s", tkn),
			SetCookie:     oasAuthentication.NewOptString(cookie),
		}, nil
	}

	return &oasAuthentication.CallbackOKHeaders{
		Authorization: fmt.Sprintf("Bearer %s", tkn),
		SetCookie:     cookie,
		Response: oasAuthentication.CallbackOK{
			Data: bytes.NewReader([]byte(tkn)),
		},
	}, nil
}

func (a *AuthenticationServer) Renew(ctx context.Context, req *oasAuthentication.RenewRequest) (oasAuthentication.RenewRes, error) {
	// Remote address is injected in the RequestMetadata middleware
	remoteAddr := ctx.Value(requestMetadataRemoteAddrCtxKey).(string)

	ss, ok := ctx.Value(tokenCtxKey).(string)
	if !ok {
		return &oasAuthentication.RenewUnauthorized{
			Error: oasAuthentication.RenewErrorErrorMissingToken,
			Msg:   "missing JWT token",
		}, nil
	}

	tkn, err := a.Authentication.Renew(ctx, ss, remoteAddr)
	if err != nil {
		if status, ok := status.FromError(err); ok {
			switch status.Code() {
			case codes.NotFound, codes.Unauthenticated:
				return &oasAuthentication.RenewUnauthorized{
					Error: oasAuthentication.RenewErrorErrorInvalidSession,
					Msg:   "session expired",
				}, nil

			default:
				a.Log.Error().Err(err).Str("code", status.Code().String()).Msg("unknown renew sessions status code error")

				return &oasAuthentication.RenewInternalServerError{
					Error: oasAuthentication.RenewErrorErrorInternalServer,
					Msg:   "unknown renew sessions error",
				}, nil
			}
		}

		a.Log.Error().Err(err).Msg("unknown renew error")

		return &oasAuthentication.RenewInternalServerError{
			Error: oasAuthentication.RenewErrorErrorInternalServer,
			Msg:   "unknown error",
		}, nil
	}

	return &oasAuthentication.RenewResponse{
		Token: tkn,
	}, nil
}

func (a *AuthenticationServer) Logout(ctx context.Context, req *oasAuthentication.LogoutRequest) (oasAuthentication.LogoutRes, error) {
	ss, ok := ctx.Value(tokenCtxKey).(string)
	if !ok {
		return &oasAuthentication.LogoutUnauthorized{
			Error: oasAuthentication.LogoutErrorErrorMissingToken,
			Msg:   "missing JWT token",
		}, nil
	}

	if err := a.Authentication.Logout(ctx, ss); err != nil {
		if errors.Is(err, jwt.ErrTokenExpired) {
			return &oasAuthentication.LogoutUnauthorized{
				Error: oasAuthentication.LogoutErrorErrorInvalidSession,
				Msg:   "session has expired",
			}, nil
		}

		if status, ok := status.FromError(err); ok {
			a.Log.Error().Err(err).Str("code", status.Code().String()).Msg("unknown logout sessions status code error")

			return &oasAuthentication.LogoutInternalServerError{
				Error: oasAuthentication.LogoutErrorErrorInternalServer,
				Msg:   "unknown logout sessions error",
			}, nil
		}

		a.Log.Error().Err(err).Msg("unknown logout error")

		return &oasAuthentication.LogoutInternalServerError{
			Error: oasAuthentication.LogoutErrorErrorInternalServer,
			Msg:   "unknown error",
		}, nil
	}

	return &oasAuthentication.LogoutResponse{}, nil
}

func (a *AuthenticationServer) Providers(ctx context.Context) (*oasAuthentication.ProvidersResponse, error) {
	providers := []oasAuthentication.Providers{}
	for _, p := range a.Authentication.Providers() {
		if p == types.ProviderLocal || p == types.ProviderLDAP {
			continue
		}

		var i oasAuthentication.Providers
		if err := i.UnmarshalText([]byte(p)); err != nil {
			a.Log.Error().Err(err).Msg("list providers")
			continue
		}

		providers = append(providers, i)
	}

	return &oasAuthentication.ProvidersResponse{
		Providers: providers,
	}, nil
}

func (a *AuthenticationServer) Check(ctx context.Context) (oasAuthentication.CheckRes, error) {
	// Remote address is injected in the RequestMetadata middleware
	remoteAddr := ctx.Value(requestMetadataRemoteAddrCtxKey).(string)

	tkn, ok := ctx.Value(tokenCtxKey).(string)
	if !ok {
		return &oasAuthentication.CheckUnauthorized{
			Error: oasAuthentication.CheckErrorErrorMissingToken,
			Msg:   "missing JWT token",
		}, nil
	}

	if err := a.Authentication.Check(ctx, tkn, remoteAddr); err != nil {
		if !errors.Is(err, token.ErrInvalidToken) || !errors.Is(err, token.ErrInvalidTokenType) {
			return nil, fmt.Errorf("check JWT: %w", err)
		}

		if status, ok := status.FromError(err); ok {
			switch status.Code() {
			case codes.NotFound, codes.Unauthenticated:
				return &oasAuthentication.CheckForbidden{
					Error: oasAuthentication.CheckErrorErrorInvalidToken,
					Msg:   "session expired",
				}, nil

			default:
				a.Log.Error().Err(err).Str("code", status.Code().String()).Msg("unknown check sessions status code error")

				return &oasAuthentication.CheckInternalServerError{
					Error: oasAuthentication.CheckErrorErrorInternalServer,
					Msg:   "unknown check sessions error",
				}, nil
			}
		}

		return &oasAuthentication.CheckForbidden{
			Error: oasAuthentication.CheckErrorErrorInvalidToken,
			Msg:   err.Error(),
		}, nil
	}

	return &oasAuthentication.CheckResponse{}, nil
}

func (a *AuthenticationServer) AcknowledgeDisclaimer(ctx context.Context, req *oasAuthentication.AcknowledgeDisclaimerRequest) (oasAuthentication.AcknowledgeDisclaimerRes, error) {
	tkn, ok := ctx.Value(tokenCtxKey).(string)
	if !ok {
		return &oasAuthentication.AcknowledgeDisclaimerUnauthorized{
			Error: oasAuthentication.AcknowledgeDisclaimerErrorErrorMissingToken,
			Msg:   "missing JWT token",
		}, nil
	}

	if err := a.Authentication.AcknowledgeDisclaimer(ctx, tkn); err != nil {
		if errors.Is(err, token.ErrInvalidToken) || errors.Is(err, token.ErrInvalidTokenType) {
			return &oasAuthentication.AcknowledgeDisclaimerForbidden{
				Error: oasAuthentication.AcknowledgeDisclaimerErrorErrorInvalidToken,
				Msg:   err.Error(),
			}, nil
		}

		var dbErr *db.Err
		if !errors.As(err, &dbErr) {
			return &oasAuthentication.AcknowledgeDisclaimerInternalServerError{
				Error: oasAuthentication.AcknowledgeDisclaimerErrorErrorInternalServer,
				Msg:   "database error",
			}, nil
		}

		a.Log.Error().Err(err).Msg("unknown acknowledge disclaimer error")

		return &oasAuthentication.AcknowledgeDisclaimerInternalServerError{
			Error: oasAuthentication.AcknowledgeDisclaimerErrorErrorInternalServer,
			Msg:   "unknown error",
		}, nil
	}

	return &oasAuthentication.AcknowledgeDisclaimerResponse{}, nil
}

func (a *AuthenticationServer) RequestEmailVerification(ctx context.Context, req *oasAuthentication.RequestEmailVerificationRequest) (oasAuthentication.RequestEmailVerificationRes, error) {
	tkn, ok := ctx.Value(tokenCtxKey).(string)
	if !ok {
		return &oasAuthentication.RequestEmailVerificationUnauthorized{
			Error: oasAuthentication.RequestEmailVerificationErrorErrorMissingToken,
			Msg:   "missing JWT token",
		}, nil
	}

	if err := a.Authentication.RequestEmailVerification(ctx, tkn, req.Email); err != nil {
		if errors.Is(err, token.ErrInvalidToken) || errors.Is(err, token.ErrInvalidTokenType) {
			return &oasAuthentication.RequestEmailVerificationForbidden{
				Error: oasAuthentication.RequestEmailVerificationErrorErrorInvalidToken,
				Msg:   err.Error(),
			}, nil
		}

		if errors.Is(err, authentication.ErrInvalidEmail) {
			return &oasAuthentication.RequestEmailVerificationBadRequest{
				Error: oasAuthentication.RequestEmailVerificationErrorErrorInvalidEmail,
				Msg:   "invalid email",
			}, nil
		}

		if errors.Is(err, authentication.ErrEmailAlreadyInUse) {
			return &oasAuthentication.RequestEmailVerificationConflict{
				Error: oasAuthentication.RequestEmailVerificationErrorErrorEmailAlreadyInUse,
				Msg:   err.Error(),
			}, nil
		}

		var dbErr *db.Err
		if errors.As(err, &dbErr) {
			return &oasAuthentication.RequestEmailVerificationInternalServerError{
				Error: oasAuthentication.RequestEmailVerificationErrorErrorInternalServer,
				Msg:   "database error",
			}, nil
		}

		a.Log.Error().Err(err).Msg("unknown request email verification error")

		return &oasAuthentication.RequestEmailVerificationInternalServerError{
			Error: oasAuthentication.RequestEmailVerificationErrorErrorInternalServer,
			Msg:   "unknown error",
		}, nil
	}

	return &oasAuthentication.RequestEmailVerificationResponse{}, nil
}

func (a *AuthenticationServer) VerifyEmail(ctx context.Context, req *oasAuthentication.VerifyEmailRequest) (oasAuthentication.VerifyEmailRes, error) {
	tkn, ok := ctx.Value(tokenCtxKey).(string)
	if !ok {
		return &oasAuthentication.VerifyEmailUnauthorized{
			Error: oasAuthentication.VerifyEmailErrorErrorMissingToken,
			Msg:   "missing JWT token",
		}, nil
	}

	if err := a.Authentication.VerifyEmail(ctx, tkn); err != nil {
		if errors.Is(err, token.ErrInvalidToken) || errors.Is(err, token.ErrInvalidTokenType) {
			return &oasAuthentication.VerifyEmailForbidden{
				Error: oasAuthentication.VerifyEmailErrorErrorInvalidToken,
				Msg:   err.Error(),
			}, nil
		}

		var dbErr *db.Err
		if errors.As(err, &dbErr) {
			return &oasAuthentication.VerifyEmailInternalServerError{
				Error: oasAuthentication.VerifyEmailErrorErrorInternalServer,
				Msg:   "database error",
			}, nil
		}

		a.Log.Error().Err(err).Msg("unknown verify email error")

		return &oasAuthentication.VerifyEmailInternalServerError{
			Error: oasAuthentication.VerifyEmailErrorErrorInternalServer,
			Msg:   "unknown error",
		}, nil
	}

	return &oasAuthentication.VerifyEmailResponse{}, nil
}

func (a *AuthenticationServer) ForgotPassword(ctx context.Context, req *oasAuthentication.ForgotPasswordRequest) (oasAuthentication.ForgotPasswordRes, error) {
	if err := a.Authentication.ForgotPassword(ctx, req.CategoryID, req.Email); err != nil {
		if errors.Is(err, token.ErrInvalidToken) || errors.Is(err, token.ErrInvalidTokenType) {
			return &oasAuthentication.ForgotPasswordForbidden{
				Error: oasAuthentication.ForgotPasswordErrorErrorInvalidToken,
				Msg:   err.Error(),
			}, nil
		}

		if errors.Is(err, authentication.ErrUserNotFound) {
			return &oasAuthentication.ForgotPasswordNotFound{
				Error: oasAuthentication.ForgotPasswordErrorErrorUserNotFound,
				Msg:   "user not found",
			}, nil
		}

		var dbErr *db.Err
		if errors.As(err, &dbErr) {
			return &oasAuthentication.ForgotPasswordInternalServerError{
				Error: oasAuthentication.ForgotPasswordErrorErrorInternalServer,
				Msg:   "database error",
			}, nil
		}

		a.Log.Error().Err(err).Msg("unknown forgot password error")

		return &oasAuthentication.ForgotPasswordInternalServerError{
			Error: oasAuthentication.ForgotPasswordErrorErrorInternalServer,
			Msg:   "unknown error",
		}, nil
	}

	return &oasAuthentication.ForgotPasswordResponse{}, nil
}

func (a *AuthenticationServer) ResetPassword(ctx context.Context, req *oasAuthentication.ResetPasswordRequest) (oasAuthentication.ResetPasswordRes, error) {
	// Remote address is injected in the RequestMetadata middleware
	remoteAddr := ctx.Value(requestMetadataRemoteAddrCtxKey).(string)

	tkn, ok := ctx.Value(tokenCtxKey).(string)
	if !ok {
		return &oasAuthentication.ResetPasswordUnauthorized{
			Error: oasAuthentication.ResetPasswordErrorErrorMissingToken,
			Msg:   "missing JWT token",
		}, nil
	}

	if err := a.Authentication.ResetPassword(ctx, tkn, req.Password, remoteAddr); err != nil {
		if errors.Is(err, token.ErrInvalidToken) || errors.Is(err, token.ErrInvalidTokenType) {
			return &oasAuthentication.ResetPasswordForbidden{
				Error: oasAuthentication.ResetPasswordErrorErrorInvalidToken,
				Msg:   err.Error(),
			}, nil
		}

		if status, ok := status.FromError(err); ok {
			switch status.Code() {
			case codes.NotFound, codes.Unauthenticated:
				return &oasAuthentication.ResetPasswordForbidden{
					Error: oasAuthentication.ResetPasswordErrorErrorInvalidToken,
					Msg:   "session expired",
				}, nil

			default:
				a.Log.Error().Err(err).Str("code", status.Code().String()).Msg("unknown reset password sessions status code error")

				return &oasAuthentication.ResetPasswordInternalServerError{
					Error: oasAuthentication.ResetPasswordErrorErrorInternalServer,
					Msg:   "unknown reset password sessions error",
				}, nil
			}
		}

		var apiErr *isardvdi.Err
		if errors.As(err, &apiErr) {
			// Extract the extra description_code and params from the error
			var (
				descCode oasAuthentication.OptResetPasswordErrorDescriptionCode
				params   oasAuthentication.OptResetPasswordErrorParams
			)

			if apiErr.DescriptionCode != nil {
				var code oasAuthentication.ResetPasswordErrorDescriptionCode
				// Only set the code if there's no error unmarshaling it
				if err := code.UnmarshalText([]byte(*apiErr.DescriptionCode)); err == nil {
					descCode = oasAuthentication.NewOptResetPasswordErrorDescriptionCode(code)
				}
			}

			if apiErr.Params != nil {
				params = oasAuthentication.NewOptResetPasswordErrorParams(oasAuthentication.ResetPasswordErrorParams{})
				rawNum, ok := (*apiErr.Params)["num"]
				if ok {
					num, ok := rawNum.(float64)
					if ok {
						params.Value.Num = oasAuthentication.NewOptFloat64(num)
					}
				}
			}

			// Handle the error
			if errors.Is(err, isardvdi.ErrBadRequest) {
				return &oasAuthentication.ResetPasswordBadRequest{
					Error:           oasAuthentication.ResetPasswordErrorErrorBadRequest,
					DescriptionCode: descCode,
					Params:          params,
					Msg:             "bad request",
				}, nil
			}

			if errors.Is(err, isardvdi.ErrInternalServer) {
				return &oasAuthentication.ResetPasswordInternalServerError{
					Error:           oasAuthentication.ResetPasswordErrorErrorInternalServer,
					DescriptionCode: descCode,
					Params:          params,
					Msg:             "api error",
				}, nil
			}

			a.Log.Error().Err(err).Msg("unknown reset password api error")

			return &oasAuthentication.ResetPasswordInternalServerError{
				Error:           oasAuthentication.ResetPasswordErrorErrorInternalServer,
				DescriptionCode: descCode,
				Params:          params,
				Msg:             "unknown api error",
			}, nil
		}

		a.Log.Error().Err(err).Msg("unknown reset password error")

		return &oasAuthentication.ResetPasswordInternalServerError{
			Error: oasAuthentication.ResetPasswordErrorErrorInternalServer,
			Msg:   "unknown error",
		}, nil
	}

	return &oasAuthentication.ResetPasswordResponse{}, nil
}
