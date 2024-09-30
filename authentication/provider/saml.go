package provider

import (
	"context"
	"crypto/rsa"
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"net/http"
	"net/url"
	"path"
	"regexp"
	"slices"

	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"

	"github.com/crewjam/saml"
	"github.com/crewjam/saml/samlsp"
	"github.com/rs/zerolog"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

const (
	ACSRoute      = "/saml/acs"
	MetadataRoute = "/saml/metadata"
	SLORoute      = "/saml/slo"
)

var _ Provider = &SAML{}

type SAML struct {
	Cfg        cfg.Authentication
	log        *zerolog.Logger
	db         r.QueryExecutor
	Middleware *samlsp.Middleware

	ReUID      *regexp.Regexp
	ReUsername *regexp.Regexp
	ReName     *regexp.Regexp
	ReEmail    *regexp.Regexp
	RePhoto    *regexp.Regexp
	ReCategory *regexp.Regexp
	ReGroup    *regexp.Regexp
	ReRole     *regexp.Regexp
}

func InitSAML(cfg cfg.Authentication, log *zerolog.Logger, db r.QueryExecutor) *SAML {
	remoteMetadataURL, err := url.Parse(cfg.SAML.MetadataURL)
	if err != nil {
		log.Fatal().Err(err).Msg("parse metadata URL")
	}

	metadata, err := samlsp.FetchMetadata(context.Background(), http.DefaultClient, *remoteMetadataURL)
	if err != nil {
		log.Fatal().Err(err).Msg("fetch metadata")
	}

	k, err := tls.LoadX509KeyPair(cfg.SAML.CertFile, cfg.SAML.KeyFile)
	if err != nil {
		log.Fatal().Err(err).Msg("load key pair")
	}

	k.Leaf, err = x509.ParseCertificate(k.Certificate[0])
	if err != nil {
		log.Fatal().Err(err).Msg("parse certificate")
	}

	baseURL, err := url.Parse(fmt.Sprintf("https://%s/authentication", cfg.Host))
	if err != nil {
		log.Fatal().Err(err).Msg("parse root URL")
	}

	url := *baseURL
	url.Path = path.Join(baseURL.Path, "/callback")

	// Set the maximum time between the initial login request and the
	// response
	saml.MaxIssueDelay = cfg.SAML.MaxIssueDelay

	middleware, _ := samlsp.New(samlsp.Options{
		URL:                url,
		Key:                k.PrivateKey.(*rsa.PrivateKey),
		Certificate:        k.Leaf,
		IDPMetadata:        metadata,
		DefaultRedirectURI: "/authentication/callback",
	})
	middleware.OnError = samlOnError(log)

	// Configure the full path of the SAML endpoints
	acsURL := *baseURL
	acsURL.Path = path.Join(baseURL.Path, ACSRoute)
	middleware.ServiceProvider.AcsURL = acsURL

	metadataURL := *baseURL
	metadataURL.Path = path.Join(baseURL.Path, MetadataRoute)
	middleware.ServiceProvider.MetadataURL = metadataURL

	sloURL := *baseURL
	sloURL.Path = path.Join(baseURL.Path, SLORoute)
	middleware.ServiceProvider.SloURL = sloURL

	s := &SAML{
		Cfg:        cfg,
		log:        log,
		db:         db,
		Middleware: middleware,
	}

	re, err := regexp.Compile(cfg.SAML.RegexUID)
	if err != nil {
		log.Fatal().Err(err).Msg("invalid UID regex")
	}
	s.ReUID = re

	re, err = regexp.Compile(cfg.SAML.RegexUsername)
	if err != nil {
		log.Fatal().Err(err).Msg("invalid username regex")
	}
	s.ReUsername = re

	re, err = regexp.Compile(cfg.SAML.RegexName)
	if err != nil {
		log.Fatal().Err(err).Msg("invalid name regex")
	}
	s.ReName = re

	re, err = regexp.Compile(cfg.SAML.RegexEmail)
	if err != nil {
		log.Fatal().Err(err).Msg("invalid email regex")
	}
	s.ReEmail = re

	re, err = regexp.Compile(cfg.SAML.RegexPhoto)
	if err != nil {
		log.Fatal().Err(err).Msg("invalid photo regex")
	}
	s.RePhoto = re

	if s.Cfg.SAML.GuessCategory {
		re, err = regexp.Compile(cfg.SAML.RegexCategory)
		if err != nil {
			log.Fatal().Err(err).Msg("invalid category regex")
		}
		s.ReCategory = re
	}

	if s.Cfg.SAML.AutoRegister {
		re, err = regexp.Compile(cfg.SAML.RegexGroup)
		if err != nil {
			log.Fatal().Err(err).Msg("invalid category regex")
		}
		s.ReGroup = re

		re, err = regexp.Compile(cfg.SAML.RegexRole)
		if err != nil {
			log.Fatal().Err(err).Msg("invalid role regex")
		}
		s.ReRole = re
	}

	return s
}

func samlOnError(log *zerolog.Logger) func(http.ResponseWriter, *http.Request, error) {
	return func(w http.ResponseWriter, r *http.Request, err error) {
		if parsedErr, ok := err.(*saml.InvalidResponseError); ok {
			log.Warn().Err(parsedErr.PrivateErr).Str("rsp", parsedErr.Response).Time("now", parsedErr.Now).Msg("received invalid SAML response")
		} else {
			log.Error().Err(err).Msg("unexpected SAML error")
		}

		http.Redirect(w, r, "/login?error=unknown", http.StatusFound)
	}
}

func (s *SAML) Login(ctx context.Context, categoryID string, args LoginArgs) (*model.Group, []*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	redirect := ""
	if args.Redirect != nil {
		redirect = *args.Redirect
	}

	ss, err := token.SignCallbackToken(s.Cfg.Secret, types.ProviderSAML, categoryID, redirect)
	if err != nil {
		return nil, nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: fmt.Errorf("sign the callback token: %w", err),
		}
	}

	u, _ := url.Parse("/authentication/callback")
	v := url.Values{
		"state": []string{ss},
	}
	u.RawQuery = v.Encode()

	return nil, []*model.Group{}, nil, u.String(), "", nil
}

func (s *SAML) Callback(ctx context.Context, claims *token.CallbackClaims, args CallbackArgs) (*model.Group, []*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	r := ctx.Value(HTTPRequest).(*http.Request)

	sess, err := s.Middleware.Session.GetSession(r)
	if err != nil {
		return nil, nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: fmt.Errorf("get SAML session: %w", err),
		}
	}

	attrs := sess.(samlsp.SessionWithAttributes).GetAttributes()

	var logAttrs any = attrs
	s.log.Debug().Any("attributes", logAttrs).Msg("recieved attributes from SAML server")

	username := matchRegex(s.ReUsername, attrs.Get(s.Cfg.SAML.FieldUsername))
	name := matchRegex(s.ReName, attrs.Get(s.Cfg.SAML.FieldName))
	email := matchRegex(s.ReEmail, attrs.Get(s.Cfg.SAML.FieldEmail))
	photo := matchRegex(s.RePhoto, attrs.Get(s.Cfg.SAML.FieldPhoto))

	u := &types.ProviderUserData{
		Provider: claims.Provider,
		Category: claims.CategoryID,
		UID:      matchRegex(s.ReUID, attrs.Get(s.Cfg.SAML.FieldUID)),

		Username: &username,
		Name:     &name,
		Email:    &email,
		Photo:    &photo,
	}

	if s.Cfg.SAML.GuessCategory {
		attrCategories := attrs[s.Cfg.SAML.FieldCategory]
		if attrCategories == nil {
			return nil, nil, nil, "", "", &ProviderError{
				User:   ErrInternal,
				Detail: fmt.Errorf("missing category attribute: '%s'", s.Cfg.SAML.FieldCategory),
			}
		}

		tkn, err := guessCategory(ctx, s.log, s.db, s.Cfg.Secret, s.ReCategory, attrCategories, u)
		if err != nil {
			return nil, nil, nil, "", "", err
		}

		if tkn != "" {
			return nil, []*model.Group{}, nil, "/", tkn, nil
		}
	}

	var g *model.Group
	secondary := []*model.Group{}
	if s.Cfg.SAML.AutoRegister {
		//
		// Guess group
		//
		attrGroups := attrs[s.Cfg.SAML.FieldGroup]
		if attrGroups == nil {
			s.log.Debug().Msg("missing groups attribute, will fallback to the default if defined")
			attrGroups = []string{}
		}

		var err *ProviderError
		g, secondary, err = guessGroup(ctx, s.db, guessGroupOpts{
			Provider:     s,
			ReGroup:      s.ReGroup,
			DefaultGroup: s.Cfg.SAML.GroupDefault,
		}, u, attrGroups)
		if err != nil {
			return nil, nil, nil, "", "", err
		}

		//
		// Guess role
		//
		attrRole := attrs[s.Cfg.SAML.FieldRole]
		if attrRole == nil {
			s.log.Debug().Msg("missing role attribute, will fallback to the default if defined")
			attrRole = []string{}
		}

		u.Role, err = guessRole(guessRoleOpts{
			ReRole:          s.ReRole,
			RoleAdminIDs:    s.Cfg.SAML.RoleAdminIDs,
			RoleManagerIDs:  s.Cfg.SAML.RoleManagerIDs,
			RoleAdvancedIDs: s.Cfg.SAML.RoleAdvancedIDs,
			RoleUserIDs:     s.Cfg.SAML.RoleUserIDs,
			RoleDefault:     s.Cfg.SAML.RoleDefault,
		}, attrRole)
		if err != nil {
			return nil, nil, nil, "", "", err
		}
	}

	return g, secondary, u, "", "", nil
}

func (s *SAML) AutoRegister(u *model.User) bool {
	if s.Cfg.SAML.AutoRegister {
		if len(s.Cfg.SAML.AutoRegisterRoles) != 0 {
			// If the user role is in the autoregister roles list, auto register
			return slices.Contains(s.Cfg.SAML.AutoRegisterRoles, string(u.Role))
		}

		return true
	}

	return false
}

func (SAML) String() string {
	return types.ProviderSAML
}

func (s *SAML) Healthcheck() error {
	var binding, bindingLocation string
	if s.Middleware.Binding != "" {
		binding = s.Middleware.Binding
		bindingLocation = s.Middleware.ServiceProvider.GetSSOBindingLocation(binding)
	} else {
		binding = saml.HTTPRedirectBinding
		bindingLocation = s.Middleware.ServiceProvider.GetSSOBindingLocation(binding)
		if bindingLocation == "" {
			binding = saml.HTTPPostBinding
			bindingLocation = s.Middleware.ServiceProvider.GetSSOBindingLocation(binding)
		}
	}

	_, err := http.Get(bindingLocation)
	if err != nil {
		return fmt.Errorf("unable to get the SAML binding location: %w", err)
	}

	return nil
}
