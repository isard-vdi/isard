package provider

import (
	"context"
	"crypto/rsa"
	"crypto/tls"
	"crypto/x509"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"path"
	"regexp"

	"gitlab.com/isard/isardvdi/authentication/authentication/provider/types"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/token"

	"github.com/crewjam/saml"
	"github.com/crewjam/saml/samlsp"
)

const (
	ACSRoute      = "/saml/acs"
	MetadataRoute = "/saml/metadata"
	SLORoute      = "/saml/slo"
)

var _ Provider = &SAML{}

type SAML struct {
	cfg        cfg.Authentication
	Middleware *samlsp.Middleware

	ReUID      *regexp.Regexp
	ReUsername *regexp.Regexp
	ReName     *regexp.Regexp
	ReEmail    *regexp.Regexp
	RePhoto    *regexp.Regexp
}

func InitSAML(cfg cfg.Authentication) *SAML {
	remoteMetadataURL, err := url.Parse(cfg.SAML.MetadataURL)
	if err != nil {
		log.Fatalf("parse metadata URL: %v", err)
	}

	metadata, err := samlsp.FetchMetadata(context.Background(), http.DefaultClient, *remoteMetadataURL)
	if err != nil {
		log.Fatalf("fetch metadata: %v", err)
	}

	k, err := tls.LoadX509KeyPair(cfg.SAML.CertFile, cfg.SAML.KeyFile)
	if err != nil {
		log.Fatalf("load key pair: %v", err)
	}

	k.Leaf, err = x509.ParseCertificate(k.Certificate[0])
	if err != nil {
		log.Fatalf("parse certificate: %v", err)
	}

	baseURL, err := url.Parse(fmt.Sprintf("https://%s/authentication", cfg.Host))
	if err != nil {
		log.Fatalf("parse root URL: %v", err)
	}

	url := *baseURL
	url.Path = path.Join(baseURL.Path, "/callback")

	middleware, _ := samlsp.New(samlsp.Options{
		URL:                url,
		Key:                k.PrivateKey.(*rsa.PrivateKey),
		Certificate:        k.Leaf,
		IDPMetadata:        metadata,
		DefaultRedirectURI: "/authentication/callback",
	})

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
		cfg:        cfg,
		Middleware: middleware,
	}

	re, err := regexp.Compile(cfg.SAML.RegexUID)
	if err != nil {
		log.Fatalf("invalid UID regex: %v", err)
	}
	s.ReUID = re

	re, err = regexp.Compile(cfg.SAML.RegexUsername)
	if err != nil {
		log.Fatalf("invalid username regex: %v", err)
	}
	s.ReUsername = re

	re, err = regexp.Compile(cfg.SAML.RegexName)
	if err != nil {
		log.Fatalf("invalid name regex: %v", err)
	}
	s.ReName = re

	re, err = regexp.Compile(cfg.SAML.RegexEmail)
	if err != nil {
		log.Fatalf("invalid email regex: %v", err)
	}
	s.ReEmail = re

	re, err = regexp.Compile(cfg.SAML.RegexPhoto)
	if err != nil {
		log.Fatalf("invalid photo regex: %v", err)
	}
	s.RePhoto = re

	return s
}

func (s *SAML) Login(ctx context.Context, categoryID string, args LoginArgs) (*model.Group, *model.User, string, *ProviderError) {
	redirect := ""
	if args.Redirect != nil {
		redirect = *args.Redirect
	}

	ss, err := token.SignCallbackToken(s.cfg.Secret, types.SAML, categoryID, redirect)
	if err != nil {
		return nil, nil, "", &ProviderError{
			User:   ErrInternal,
			Detail: fmt.Errorf("sign the callback token: %w", err),
		}
	}

	u, _ := url.Parse("/authentication/callback")
	v := url.Values{
		"state": []string{ss},
	}
	u.RawQuery = v.Encode()

	return nil, nil, u.String(), nil
}

func (s *SAML) Callback(ctx context.Context, claims *token.CallbackClaims, args CallbackArgs) (*model.Group, *model.User, string, *ProviderError) {
	r := ctx.Value(HTTPRequest).(*http.Request)

	sess, err := s.Middleware.Session.GetSession(r)
	if err != nil {
		return nil, nil, "", &ProviderError{
			User:   ErrInternal,
			Detail: fmt.Errorf("get SAML session: %w", err),
		}
	}

	attrs := sess.(samlsp.SessionWithAttributes).GetAttributes()

	u := &model.User{
		UID:      matchRegex(s.ReUID, attrs.Get(s.cfg.SAML.FieldUID)),
		Provider: claims.Provider,
		Category: claims.CategoryID,
		Username: matchRegex(s.ReUsername, attrs.Get(s.cfg.SAML.FieldUsername)),
		Name:     matchRegex(s.ReName, attrs.Get(s.cfg.SAML.FieldName)),
		Email:    matchRegex(s.ReEmail, attrs.Get(s.cfg.SAML.FieldEmail)),
		Photo:    matchRegex(s.RePhoto, attrs.Get(s.cfg.SAML.FieldPhoto)),
	}

	// // TODO: Autoregister
	// if s.AutoRegister() {

	// }

	return nil, u, "", nil
}

func (SAML) AutoRegister() bool {
	return false
}

func (SAML) String() string {
	return types.SAML
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
