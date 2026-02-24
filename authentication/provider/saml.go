package provider

import (
	"context"
	"crypto/rsa"
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"path"
	"regexp"
	"slices"
	"strings"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/token"
	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/crewjam/saml"
	"github.com/crewjam/saml/samlsp"
	"github.com/patrickmn/go-cache"
	"github.com/rs/zerolog"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

const (
	ACSRoute      = "/saml/acs"
	MetadataRoute = "/saml/metadata"
	SLORoute      = "/saml/slo"
)

var _ Provider = &SAML{}

type SAMLConfig struct {
	MetadataURL     string `rethinkdb:"metadata_url"`
	MetadataFile    string `rethinkdb:"metadata_file"`
	EntityID        string `rethinkdb:"entity_id"`
	SignatureMethod string `rethinkdb:"signature_method"`
	KeyFile         string `rethinkdb:"key_file"`
	CertFile        string `rethinkdb:"cert_file"`
	MaxIssueDelay   string `rethinkdb:"max_issue_delay"`

	FieldUID      string `rethinkdb:"field_uid"`
	RegexUID      string `rethinkdb:"regex_uid"`
	FieldUsername string `rethinkdb:"field_username"`
	RegexUsername string `rethinkdb:"regex_username"`
	FieldName     string `rethinkdb:"field_name"`
	RegexName     string `rethinkdb:"regex_name"`
	FieldEmail    string `rethinkdb:"field_email"`
	RegexEmail    string `rethinkdb:"regex_email"`
	FieldPhoto    string `rethinkdb:"field_photo"`
	RegexPhoto    string `rethinkdb:"regex_photo"`

	AutoRegister      bool   `rethinkdb:"auto_register"`
	AutoRegisterRoles string `rethinkdb:"auto_register_roles"`

	GuessCategory bool   `rethinkdb:"guess_category"`
	FieldCategory string `rethinkdb:"field_category"`
	RegexCategory string `rethinkdb:"regex_category"`

	FieldGroup   string `rethinkdb:"field_group"`
	RegexGroup   string `rethinkdb:"regex_group"`
	GroupDefault string `rethinkdb:"group_default"`

	FieldRole       string     `rethinkdb:"field_role"`
	RegexRole       string     `rethinkdb:"regex_role"`
	RoleAdminIDs    string     `rethinkdb:"role_admin_ids"`
	RoleManagerIDs  string     `rethinkdb:"role_manager_ids"`
	RoleAdvancedIDs string     `rethinkdb:"role_advanced_ids"`
	RoleUserIDs     string     `rethinkdb:"role_user_ids"`
	RoleDefault     model.Role `rethinkdb:"role_default"`

	LogoutRedirectURL string `rethinkdb:"logout_redirect_url"`
	SaveEmail         bool   `rethinkdb:"save_email"`
}

type SAML struct {
	cfg        *SAMLConfig
	secret     string
	host       string
	log        *zerolog.Logger
	db         r.QueryExecutor
	Middleware *samlsp.Middleware

	MaxIssueDelay time.Duration

	ReUID      *regexp.Regexp
	ReUsername *regexp.Regexp
	ReName     *regexp.Regexp
	ReEmail    *regexp.Regexp
	RePhoto    *regexp.Regexp
	ReCategory *regexp.Regexp
	ReGroup    *regexp.Regexp
	ReRole     *regexp.Regexp

	AutoRegisterRoles []string

	RoleAdminIDs    []string
	RoleManagerIDs  []string
	RoleAdvancedIDs []string
	RoleUserIDs     []string
}

func InitSAML(secret string, host string, log *zerolog.Logger, db r.QueryExecutor) *SAML {
	s := &SAML{
		secret: secret,
		host:   host,
		log:    log,
		db:     db,
	}
	s.SAMLConfig()
	return s
}

func (s *SAML) SAMLConfig() error {
	var metadata *saml.EntityDescriptor
	var err error
	var maxIssueDelay time.Duration

	s.cfg = &SAMLConfig{}
	if val, found := c.Get("saml_config"); found {
		s.cfg = val.(*SAMLConfig)
	} else {
		res, err := r.Table("config").Get(1).Field("auth").Field("saml").Field("saml_config").Run(s.db)
		if err != nil {
			return &db.Err{
				Err: err,
			}
		}
		if res.IsNil() {
			return db.ErrNotFound
		}
		defer res.Close()
		if err := res.One(s.cfg); err != nil {
			return &db.Err{
				Msg: "read db response",
				Err: err,
			}
		}
		c.Set("saml_config", s.cfg, cache.DefaultExpiration)
	}

	maxIssueDelay, err = time.ParseDuration(s.cfg.MaxIssueDelay)
	if err != nil {
		s.log.Fatal().Err(err).Msg("invalid max issue delay")
	}
	s.MaxIssueDelay = maxIssueDelay

	// Try to load metadata from local file first (if configured)
	if s.cfg.MetadataFile != "" {
		s.log.Info().Str("file", s.cfg.MetadataFile).Msg("attempting to load IdP metadata from local file")

		data, readErr := os.ReadFile(s.cfg.MetadataFile)
		if readErr == nil {
			metadata, err = samlsp.ParseMetadata(data)
			if err == nil {
				s.log.Info().Str("file", s.cfg.MetadataFile).Msg("successfully loaded IdP metadata from local file")
			} else {
				s.log.Warn().Err(err).Str("file", s.cfg.MetadataFile).Msg("failed to parse local metadata file, falling back to URL")
			}
		} else {
			s.log.Info().Err(readErr).Str("file", s.cfg.MetadataFile).Msg("local metadata file not found, falling back to URL")
		}
	}

	// Fall back to URL fetch if local file didn't work or wasn't configured
	if metadata == nil {
		if s.cfg.MetadataURL == "" {
			s.log.Fatal().Msg("neither metadata file nor metadata URL is configured")
		}

		remoteMetadataURL, err := url.Parse(s.cfg.MetadataURL)
		if err != nil {
			s.log.Fatal().Err(err).Msg("parse metadata URL")
		}

		s.log.Info().Str("url", s.cfg.MetadataURL).Msg("fetching IdP metadata from URL")
		metadata, err = samlsp.FetchMetadata(context.Background(), http.DefaultClient, *remoteMetadataURL)
		if err != nil {
			s.log.Fatal().Err(err).Msg("fetch metadata from URL failed")
		}
		s.log.Info().Str("url", s.cfg.MetadataURL).Msg("successfully fetched IdP metadata from URL")
	}

	k, err := tls.LoadX509KeyPair(s.cfg.CertFile, s.cfg.KeyFile)
	if err != nil {
		s.log.Fatal().Err(err).Msg("load key pair")
	}

	k.Leaf, err = x509.ParseCertificate(k.Certificate[0])
	if err != nil {
		s.log.Fatal().Err(err).Msg("parse certificate")
	}

	baseURL, err := url.Parse(fmt.Sprintf("https://%s/authentication", s.host))
	if err != nil {
		s.log.Fatal().Err(err).Msg("parse root URL")
	}

	url := *baseURL
	url.Path = path.Join(baseURL.Path, "/callback")

	// Set the maximum time between the initial s.login request and the
	// response
	saml.MaxIssueDelay = s.MaxIssueDelay

	middleware, _ := samlsp.New(samlsp.Options{
		URL:                url,
		Key:                k.PrivateKey.(*rsa.PrivateKey),
		Certificate:        k.Leaf,
		IDPMetadata:        metadata,
		DefaultRedirectURI: "/authentication/callback",
	})
	middleware.OnError = samlOnError(s.log)

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

	// Set custom Entity ID if configured, otherwise it defaults to MetadataURL
	if s.cfg.EntityID != "" {
		middleware.ServiceProvider.EntityID = s.cfg.EntityID
		s.log.Info().Str("entity_id", s.cfg.EntityID).Msg("using custom SAML Entity ID")
	}

	// Enable SAML AuthnRequest signing if configured
	if s.cfg.SignatureMethod != "" {
		middleware.ServiceProvider.SignatureMethod = s.cfg.SignatureMethod
		s.log.Info().Str("signature_method", s.cfg.SignatureMethod).Msg("SAML request signing enabled")
	}

	s.Middleware = middleware

	re, err := regexp.Compile(s.cfg.RegexUID)
	if err != nil {
		s.log.Fatal().Err(err).Msg("invalid UID regex")
	}
	s.ReUID = re

	re, err = regexp.Compile(s.cfg.RegexUsername)
	if err != nil {
		s.log.Fatal().Err(err).Msg("invalid username regex")
	}
	s.ReUsername = re

	re, err = regexp.Compile(s.cfg.RegexName)
	if err != nil {
		s.log.Fatal().Err(err).Msg("invalid name regex")
	}
	s.ReName = re

	re, err = regexp.Compile(s.cfg.RegexEmail)
	if err != nil {
		s.log.Fatal().Err(err).Msg("invalid email regex")
	}
	s.ReEmail = re

	re, err = regexp.Compile(s.cfg.RegexPhoto)
	if err != nil {
		s.log.Fatal().Err(err).Msg("invalid photo regex")
	}
	s.RePhoto = re

	if s.cfg.GuessCategory {
		re, err = regexp.Compile(s.cfg.RegexCategory)
		if err != nil {
			s.log.Fatal().Err(err).Msg("invalid category regex")
		}
		s.ReCategory = re
	}

	if s.cfg.AutoRegister {
		re, err = regexp.Compile(s.cfg.RegexGroup)
		if err != nil {
			s.log.Fatal().Err(err).Msg("invalid category regex")
		}
		s.ReGroup = re

		re, err = regexp.Compile(s.cfg.RegexRole)
		if err != nil {
			s.log.Fatal().Err(err).Msg("invalid role regex")
		}
		s.ReRole = re
	}

	if s.cfg.AutoRegisterRoles != "" {
		s.AutoRegisterRoles = strings.Split(s.cfg.AutoRegisterRoles, ",")
	} else {
		s.AutoRegisterRoles = []string{}
	}

	s.RoleAdminIDs = strings.Split(s.cfg.RoleAdminIDs, ",")
	s.RoleManagerIDs = strings.Split(s.cfg.RoleManagerIDs, ",")
	s.RoleAdvancedIDs = strings.Split(s.cfg.RoleAdvancedIDs, ",")
	s.RoleUserIDs = strings.Split(s.cfg.RoleUserIDs, ",")

	return nil
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
	if err := s.SAMLConfig(); err != nil {
		return nil, nil, nil, "", "", &ProviderError{
			User:   ErrInternal,
			Detail: err,
		}
	}
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

	username := matchRegex(s.ReUsername, attrs.Get(s.cfg.FieldUsername))
	name := matchRegex(s.ReName, attrs.Get(s.cfg.FieldName))
	email := matchRegex(s.ReEmail, attrs.Get(s.cfg.FieldEmail))
	photo := matchRegex(s.RePhoto, attrs.Get(s.cfg.FieldPhoto))

	u := &types.ProviderUserData{
		Provider: claims.Provider,
		Category: claims.CategoryID,
		UID:      matchRegex(s.ReUID, attrs.Get(s.cfg.FieldUID)),

		Username: &username,
		Name:     &name,
		Email:    &email,
		Photo:    &photo,
	}

	if s.cfg.GuessCategory {
		attrCategories := attrs[s.cfg.FieldCategory]
		if attrCategories == nil {
			return nil, nil, nil, "", "", &ProviderError{
				User:   ErrInternal,
				Detail: fmt.Errorf("missing category attribute: '%s'", s.cfg.FieldCategory),
			}
		}

		var (
			attrGroups *[]string
			attrRole   *[]string
		)
		if s.cfg.AutoRegister {
			g := attrs[s.cfg.FieldGroup]
			attrGroups = &g
			r := attrs[s.cfg.FieldRole]
			attrRole = &r
		}

		tkn, err := guessCategory(ctx, s.log, s.db, s.secret, s.ReCategory, attrCategories, attrGroups, attrRole, u)
		if err != nil {
			return nil, nil, nil, "", "", err
		}

		if tkn != "" {
			return nil, []*model.Group{}, nil, "/", tkn, nil
		}
	}

	var g *model.Group
	secondary := []*model.Group{}
	if s.cfg.AutoRegister {
		//
		// Guess group
		//
		attrGroups := attrs[s.cfg.FieldGroup]
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
		attrRole := attrs[s.cfg.FieldRole]
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
	if err := s.SAMLConfig(); err != nil {
		return false
	}
	if s.cfg.AutoRegister {
		if len(s.AutoRegisterRoles) != 0 {
			// If the user role is in the autoregister roles list, auto register
			allowed := slices.Contains(s.AutoRegisterRoles, string(u.Role))
			if allowed {
				s.log.Info().Str("usr", u.UID).Str("role", string(u.Role)).Strs("allowed_roles", s.AutoRegisterRoles).Msg("auto-registration allowed: user role matches allowed roles list")
			} else {
				s.log.Info().Str("usr", u.UID).Str("role", string(u.Role)).Strs("allowed_roles", s.AutoRegisterRoles).Msg("auto-registration denied: user role not in allowed roles list")
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
	if err := s.SAMLConfig(); err != nil {
		return err
	}
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

	resp, err := http.Get(bindingLocation)
	if err != nil {
		return fmt.Errorf("unable to get the SAML binding location: %w", err)
	}
	defer resp.Body.Close()

	return nil
}

func (s SAML) Logout(context.Context, string) (string, error) {
	if err := s.SAMLConfig(); err != nil {
		return "", err
	}
	return s.cfg.LogoutRedirectURL, nil
}

func (s *SAML) SaveEmail() bool {
	if err := s.SAMLConfig(); err != nil {
		return true
	}
	return s.cfg.SaveEmail
}

func (s *SAML) GuessGroups(ctx context.Context, u *types.ProviderUserData, rawGroups []string) (*model.Group, []*model.Group, *ProviderError) {
	return guessGroup(ctx, s.db, guessGroupOpts{
		Provider:     s,
		ReGroup:      s.ReGroup,
		DefaultGroup: s.cfg.GroupDefault,
	}, u, rawGroups)
}

func (s *SAML) GuessRole(ctx context.Context, u *types.ProviderUserData, rawRoles []string) (*model.Role, *ProviderError) {
	return guessRole(guessRoleOpts{
		ReRole:          s.ReRole,
		RoleAdminIDs:    s.RoleAdminIDs,
		RoleManagerIDs:  s.RoleManagerIDs,
		RoleAdvancedIDs: s.RoleAdvancedIDs,
		RoleUserIDs:     s.RoleUserIDs,
		RoleDefault:     s.cfg.RoleDefault,
	}, rawRoles)
}
