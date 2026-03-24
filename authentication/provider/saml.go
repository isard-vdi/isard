package provider

import (
	"context"
	"crypto/rsa"
	"crypto/tls"
	"crypto/x509"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"path"
	"regexp"
	"slices"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"
	httpErr "gitlab.com/isard/isardvdi/authentication/transport/http/error"

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

var _ ConfigurableProvider[model.SAMLConfig] = &SAML{}

type SAMLConfig struct {
	Middleware *samlsp.Middleware

	FieldUID      string
	ReUID         *regexp.Regexp
	FieldUsername string
	ReUsername    *regexp.Regexp
	FieldName     string
	ReName        *regexp.Regexp
	FieldEmail    string
	ReEmail       *regexp.Regexp
	FieldPhoto    string
	RePhoto       *regexp.Regexp

	AutoRegister      bool
	AutoRegisterRoles []string

	GuessCategory bool
	FieldCategory string
	ReCategory    *regexp.Regexp

	FieldGroup   string
	ReGroup      *regexp.Regexp
	GroupDefault string

	FieldRole string
	ReRole    *regexp.Regexp

	RoleAdminIDs    []string
	RoleManagerIDs  []string
	RoleAdvancedIDs []string
	RoleUserIDs     []string
	RoleDefault     model.Role

	LogoutRedirectURL string

	SaveEmail bool
}

type SAML struct {
	cfg *cfgManager[SAMLConfig]

	secret     string
	host       string
	categoryID *string
	log        *zerolog.Logger
	db         r.QueryExecutor
	httpClient *http.Client
}

func InitSAML(secret string, host string, categoryID *string, log *zerolog.Logger, db r.QueryExecutor) *SAML {
	s := &SAML{
		cfg:        &cfgManager[SAMLConfig]{cfg: &SAMLConfig{}},
		secret:     secret,
		host:       host,
		categoryID: categoryID,
		log:        log,
		db:         db,
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

		httpErr.LoginRedirect(w, r, httpErr.LoginUnknown)
	}
}

func (s *SAML) LoadConfig(ctx context.Context, cfg model.SAMLConfig) error {
	prvCfg := s.cfg.Cfg()

	var metadata *saml.EntityDescriptor
	var err error

	//
	// Middleware setup
	//

	// Try to load metadata from local file first (if configured)
	if cfg.MetadataFile != "" {
		s.log.Info().Str("file", cfg.MetadataFile).Msg("attempting to load IdP metadata from local file")

		data, readErr := os.ReadFile(cfg.MetadataFile)
		if readErr == nil {
			metadata, err = samlsp.ParseMetadata(data)
			if err == nil {
				s.log.Info().Str("file", cfg.MetadataFile).Msg("successfully loaded IdP metadata from local file")
			} else {
				s.log.Warn().Err(err).Str("file", cfg.MetadataFile).Msg("failed to parse local metadata file, falling back to URL")
			}
		} else {
			s.log.Info().Err(readErr).Str("file", cfg.MetadataFile).Msg("local metadata file not found, falling back to URL")
		}
	}

	// Fall back to URL fetch if local file didn't work or wasn't configured
	if metadata == nil {
		if cfg.MetadataURL == "" {
			return errors.New("neither metadata file nor metadata URL is configured")
		}

		if err := validateMetadataURL(cfg.MetadataURL); err != nil {
			s.log.Error().Err(err).Str("url", cfg.MetadataURL).Msg("invalid metadata URL")
			return fmt.Errorf("invalid metadata URL: %w", err)
		}

		remoteMetadataURL, err := url.Parse(cfg.MetadataURL)
		if err != nil {
			return fmt.Errorf("parse metadata URL: %w", err)
		}

		httpClient := s.httpClient
		if httpClient == nil {
			httpClient = &http.Client{Timeout: 30 * time.Second}
		}
		s.log.Info().Str("url", cfg.MetadataURL).Msg("fetching IdP metadata from URL")
		metadata, err = samlsp.FetchMetadata(ctx, httpClient, *remoteMetadataURL)
		if err != nil {
			return fmt.Errorf("fetch metadata from URL failed: %w", err)
		}

		s.log.Info().Str("url", cfg.MetadataURL).Msg("successfully fetched IdP metadata from URL")
	}

	k, err := tls.LoadX509KeyPair(cfg.CertFile, cfg.KeyFile)
	if err != nil {
		return fmt.Errorf("load key pair: %w", err)
	}

	k.Leaf, err = x509.ParseCertificate(k.Certificate[0])
	if err != nil {
		return fmt.Errorf("parse certificate: %w", err)
	}

	baseURL, err := url.Parse(fmt.Sprintf("https://%s/authentication", s.host))
	if err != nil {
		return fmt.Errorf("parse root URL: %w", err)
	}

	url := *baseURL
	url.Path = path.Join(baseURL.Path, "/callback")

	// Set the maximum time between the initial login request and the
	// response
	saml.MaxIssueDelay = time.Duration(cfg.MaxIssueDelay)

	middleware, _ := samlsp.New(samlsp.Options{
		URL:                url,
		Key:                k.PrivateKey.(*rsa.PrivateKey),
		Certificate:        k.Leaf,
		IDPMetadata:        metadata,
		DefaultRedirectURI: "/authentication/callback",
	})
	middleware.OnError = samlOnError(s.log)

	// Build category-aware SAML endpoint paths.
	acsSuffix := ACSRoute
	metadataSuffix := MetadataRoute
	sloSuffix := SLORoute
	if s.categoryID != nil {
		acsSuffix = path.Join("/saml", *s.categoryID, "acs")
		metadataSuffix = path.Join("/saml", *s.categoryID, "metadata")
		sloSuffix = path.Join("/saml", *s.categoryID, "slo")
	}

	acsURL := *baseURL
	acsURL.Path = path.Join(baseURL.Path, acsSuffix)
	middleware.ServiceProvider.AcsURL = acsURL

	metadataURL := *baseURL
	metadataURL.Path = path.Join(baseURL.Path, metadataSuffix)
	middleware.ServiceProvider.MetadataURL = metadataURL

	sloURL := *baseURL
	sloURL.Path = path.Join(baseURL.Path, sloSuffix)
	middleware.ServiceProvider.SloURL = sloURL

	// Set custom Entity ID if configured, otherwise it defaults to MetadataURL
	if cfg.EntityID != "" {
		middleware.ServiceProvider.EntityID = cfg.EntityID
		s.log.Info().Str("entity_id", cfg.EntityID).Msg("using custom SAML Entity ID")
	}

	// Enable SAML AuthnRequest signing if configured
	if cfg.SignatureMethod != "" {
		middleware.ServiceProvider.SignatureMethod = cfg.SignatureMethod
		s.log.Info().Str("signature_method", cfg.SignatureMethod).Msg("SAML request signing enabled")
	}

	prvCfg.Middleware = middleware

	//
	// Rest of the configuration
	//
	prvCfg.FieldUID = cfg.FieldUID
	re, err := regexp.Compile(cfg.RegexUID)
	if err != nil {
		return fmt.Errorf("invalid UID regex: %w", err)
	}
	prvCfg.ReUID = re

	prvCfg.FieldUsername = cfg.FieldUsername
	re, err = regexp.Compile(cfg.RegexUsername)
	if err != nil {
		return fmt.Errorf("invalid username regex: %w", err)
	}
	prvCfg.ReUsername = re

	prvCfg.FieldName = cfg.FieldName
	re, err = regexp.Compile(cfg.RegexName)
	if err != nil {
		return fmt.Errorf("invalid name regex: %w", err)
	}
	prvCfg.ReName = re

	prvCfg.FieldEmail = cfg.FieldEmail
	re, err = regexp.Compile(cfg.RegexEmail)
	if err != nil {
		return fmt.Errorf("invalid email regex: %w", err)
	}
	prvCfg.ReEmail = re

	prvCfg.FieldPhoto = cfg.FieldPhoto
	re, err = regexp.Compile(cfg.RegexPhoto)
	if err != nil {
		return fmt.Errorf("invalid photo regex: %w", err)
	}
	prvCfg.RePhoto = re

	prvCfg.AutoRegister = cfg.AutoRegister
	prvCfg.AutoRegisterRoles = cfg.AutoRegisterRoles

	prvCfg.GuessCategory = cfg.GuessCategory
	prvCfg.FieldCategory = cfg.FieldCategory
	if cfg.GuessCategory {
		re, err = regexp.Compile(cfg.RegexCategory)
		if err != nil {
			return fmt.Errorf("invalid category regex: %w", err)
		}
		prvCfg.ReCategory = re
	} else {
		prvCfg.ReCategory = nil
	}

	prvCfg.FieldGroup = cfg.FieldGroup
	prvCfg.GroupDefault = cfg.GroupDefault

	prvCfg.FieldRole = cfg.FieldRole
	if cfg.AutoRegister {
		re, err = regexp.Compile(cfg.RegexGroup)
		if err != nil {
			return fmt.Errorf("invalid group regex: %w", err)
		}
		prvCfg.ReGroup = re

		re, err = regexp.Compile(cfg.RegexRole)
		if err != nil {
			return fmt.Errorf("invalid role regex: %w", err)
		}
		prvCfg.ReRole = re

	} else {
		prvCfg.ReGroup = nil
		prvCfg.ReRole = nil
	}

	prvCfg.RoleAdminIDs = cfg.RoleAdminIDs
	prvCfg.RoleManagerIDs = cfg.RoleManagerIDs
	prvCfg.RoleAdvancedIDs = cfg.RoleAdvancedIDs
	prvCfg.RoleUserIDs = cfg.RoleUserIDs
	prvCfg.RoleDefault = cfg.RoleDefault

	prvCfg.LogoutRedirectURL = cfg.LogoutRedirectURL

	prvCfg.SaveEmail = cfg.SaveEmail

	s.cfg.LoadCfg(prvCfg)

	return nil
}

func validateMetadataURL(rawURL string) error {
	u, err := url.Parse(rawURL)
	if err != nil {
		return fmt.Errorf("malformed URL: %w", err)
	}
	if u.Scheme != "https" {
		return fmt.Errorf("metadata URL must use https scheme, got %q", u.Scheme)
	}
	return nil
}

func (s *SAML) Login(ctx context.Context, categoryID string, args LoginArgs) (*model.Group, []*model.Group, *types.ProviderUserData, string, string, *ProviderError) {
	redirect := ""
	if args.Redirect != nil {
		redirect = *args.Redirect
	}

	ss, err := token.SignCallbackToken(s.secret, types.ProviderSAML, categoryID, redirect)
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
	cfg := s.cfg.Cfg()

	r := ctx.Value(HTTPRequest).(*http.Request)

	sess, err := cfg.Middleware.Session.GetSession(r)
	if err != nil {
		return nil, nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: fmt.Errorf("get SAML session: %w", err),
		}
	}

	attrs := sess.(samlsp.SessionWithAttributes).GetAttributes()

	var logAttrs any = attrs
	s.log.Debug().Any("attributes", logAttrs).Msg("recieved attributes from SAML server")

	username := matchRegex(cfg.ReUsername, attrs.Get(cfg.FieldUsername))
	name := matchRegex(cfg.ReName, attrs.Get(cfg.FieldName))
	email := matchRegex(cfg.ReEmail, attrs.Get(cfg.FieldEmail))
	photo := matchRegex(cfg.RePhoto, attrs.Get(cfg.FieldPhoto))

	u := &types.ProviderUserData{
		Provider: claims.Provider,
		Category: claims.CategoryID,
		UID:      matchRegex(cfg.ReUID, attrs.Get(cfg.FieldUID)),

		Username: &username,
		Name:     &name,
		Email:    &email,
		Photo:    &photo,
	}

	if cfg.GuessCategory {
		attrCategories := attrs[cfg.FieldCategory]
		if attrCategories == nil {
			return nil, nil, nil, "", "", &ProviderError{
				User:   ErrInternal,
				Detail: fmt.Errorf("missing category attribute: '%s'", cfg.FieldCategory),
			}
		}

		var (
			attrGroups *[]string
			attrRole   *[]string
		)
		if cfg.AutoRegister {
			g := attrs[cfg.FieldGroup]
			attrGroups = &g
			r := attrs[cfg.FieldRole]
			attrRole = &r
		}

		tkn, err := guessCategory(ctx, s.log, s.db, s.secret, cfg.ReCategory, attrCategories, attrGroups, attrRole, u)
		if err != nil {
			return nil, nil, nil, "", "", err
		}

		if tkn != "" {
			return nil, []*model.Group{}, nil, "/", tkn, nil
		}
	}

	var g *model.Group
	secondary := []*model.Group{}
	if cfg.AutoRegister {
		//
		// Guess group
		//
		attrGroups := attrs[cfg.FieldGroup]
		if attrGroups == nil {
			s.log.Debug().Msg("missing groups attribute, will fallback to the default if defined")
			attrGroups = []string{}
		}

		var err *ProviderError
		g, secondary, err = s.GuessGroups(ctx, u, attrGroups)
		if err != nil {
			return nil, nil, nil, "", "", err
		}

		//
		// Guess role
		//
		attrRole := attrs[cfg.FieldRole]
		if attrRole == nil {
			s.log.Debug().Msg("missing role attribute, will fallback to the default if defined")
			attrRole = []string{}
		}

		u.Role, err = s.GuessRole(ctx, u, attrRole)
		if err != nil {
			return nil, nil, nil, "", "", err
		}

		s.log.Info().Strs("raw_role_attributes", attrRole).Str("assigned_role", string(*u.Role)).Msg("role extraction completed")
	}

	return g, secondary, u, "", "", nil
}

func (s *SAML) AutoRegister(u *model.User) bool {
	cfg := s.cfg.Cfg()

	if cfg.AutoRegister {
		if len(cfg.AutoRegisterRoles) != 0 {
			// If the user role is in the autoregister roles list, auto register
			allowed := slices.Contains(cfg.AutoRegisterRoles, string(u.Role))
			if allowed {
				s.log.Info().Str("usr", u.UID).Str("role", string(u.Role)).Strs("allowed_roles", cfg.AutoRegisterRoles).Msg("auto-registration allowed: user role matches allowed roles list")
			} else {
				s.log.Info().Str("usr", u.UID).Str("role", string(u.Role)).Strs("allowed_roles", cfg.AutoRegisterRoles).Msg("auto-registration denied: user role not in allowed roles list")
			}

			return allowed
		}

		s.log.Info().Str("usr", u.UID).Str("role", string(u.Role)).Msg("auto-registration allowed: no role restrictions configured")
		return true
	}

	s.log.Info().Str("usr", u.UID).Msg("auto-registration denied: auto_register is disabled in configuration")
	return false
}

func (SAML) String() string {
	return types.ProviderSAML
}

func (s *SAML) Healthcheck() error {
	cfg := s.cfg.Cfg()

	if cfg.Middleware == nil {
		return fmt.Errorf("SAML middleware not yet configured")
	}

	var binding, bindingLocation string
	if cfg.Middleware.Binding != "" {
		binding = cfg.Middleware.Binding
		bindingLocation = cfg.Middleware.ServiceProvider.GetSSOBindingLocation(binding)
	} else {
		binding = saml.HTTPRedirectBinding
		bindingLocation = cfg.Middleware.ServiceProvider.GetSSOBindingLocation(binding)
		if bindingLocation == "" {
			binding = saml.HTTPPostBinding
			bindingLocation = cfg.Middleware.ServiceProvider.GetSSOBindingLocation(binding)
		}
	}

	resp, err := http.Get(bindingLocation)
	if err != nil {
		return fmt.Errorf("unable to get the SAML binding location: %w", err)
	}
	defer resp.Body.Close()

	return nil
}

func (s SAML) Logout(context.Context, string) (string, error) {
	return s.cfg.Cfg().LogoutRedirectURL, nil
}

func (s *SAML) SaveEmail() bool {
	return s.cfg.Cfg().SaveEmail
}

func (s *SAML) GuessGroups(ctx context.Context, u *types.ProviderUserData, rawGroups []string) (*model.Group, []*model.Group, *ProviderError) {
	cfg := s.cfg.Cfg()

	return guessGroup(ctx, s.db, guessGroupOpts{
		Provider:     s,
		ReGroup:      cfg.ReGroup,
		DefaultGroup: cfg.GroupDefault,
	}, u, rawGroups)
}

func (s *SAML) GuessRole(ctx context.Context, u *types.ProviderUserData, rawRoles []string) (*model.Role, *ProviderError) {
	cfg := s.cfg.Cfg()

	return guessRole(guessRoleOpts{
		ReRole:          cfg.ReRole,
		RoleAdminIDs:    cfg.RoleAdminIDs,
		RoleManagerIDs:  cfg.RoleManagerIDs,
		RoleAdvancedIDs: cfg.RoleAdvancedIDs,
		RoleUserIDs:     cfg.RoleUserIDs,
		RoleDefault:     cfg.RoleDefault,
	}, rawRoles)
}

func (s *SAML) Middleware() *samlsp.Middleware {
	return s.cfg.Cfg().Middleware
}
