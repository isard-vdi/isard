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
	"regexp"

	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"

	"github.com/crewjam/saml/samlsp"
)

const SAMLString = "saml"

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
	metadataURL, err := url.Parse(cfg.SAML.MetadataURL)
	if err != nil {
		log.Fatalf("parse metadata URL: %v", err)
	}

	metadata, err := samlsp.FetchMetadata(context.Background(), http.DefaultClient, *metadataURL)
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

	url, err := url.Parse(fmt.Sprintf("https://%s/authentication/callback", cfg.Host))
	if err != nil {
		log.Fatalf("parse root URL: %v", err)
	}

	middleware, _ := samlsp.New(samlsp.Options{
		URL:                *url,
		Key:                k.PrivateKey.(*rsa.PrivateKey),
		Certificate:        k.Leaf,
		IDPMetadata:        metadata,
		DefaultRedirectURI: "/authentication/callback",
	})

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

func (s *SAML) Login(ctx context.Context, categoryID string, args map[string]string) (*model.Group, *model.User, string, error) {
	redirect := ""
	if r, ok := args["redirect"]; ok {
		redirect = r
	}

	ss, err := signCallbackToken(s.cfg.Secret, SAMLString, categoryID, redirect)
	if err != nil {
		return nil, nil, "", err
	}

	u, _ := url.Parse("/authentication/callback")
	v := url.Values{
		"state": []string{ss},
	}
	u.RawQuery = v.Encode()

	return nil, nil, u.String(), nil
}

func (s *SAML) Callback(ctx context.Context, claims *CallbackClaims, args map[string]string) (*model.Group, *model.User, string, error) {
	r := ctx.Value(HTTPRequest).(*http.Request)

	sess, err := s.Middleware.Session.GetSession(r)
	if err != nil {
		return nil, nil, "", fmt.Errorf("get SAML session: %w", err)
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
	return SAMLString
}
