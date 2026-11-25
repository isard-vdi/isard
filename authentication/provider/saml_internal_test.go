package provider

import (
	"bytes"
	"compress/flate"
	"context"
	"crypto"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"slices"
	"sync"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/pkg/db"
	"gitlab.com/isard/isardvdi/pkg/log"
	pkgTls "gitlab.com/isard/isardvdi/pkg/tls"

	"github.com/crewjam/saml"
	"github.com/crewjam/saml/samlsp"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestSAMLLoadConfig(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	type expected struct {
		Err           string
		Cfg           *SAMLConfig
		MaxIssueDelay time.Duration
	}

	cases := map[string]struct {
		PreviousInput             func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig
		Input                     func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig
		NeedTLS                   bool
		ValidateURL               func(string) error
		CategoryID                *string
		BrandingHosts             map[string]string
		SkippedBrandingCategories []string
		Expected                  expected
	}{
		"should load config with all fields from local metadata file": {
			NeedTLS: true,
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile:    metadataPath,
					EntityID:        "https://sp.example.com",
					SignatureMethod: "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
					KeyFile:         keyPath,
					CertFile:        certPath,
					MaxIssueDelay:   db.Duration(5 * time.Minute),

					FieldUID:      "uid",
					RegexUID:      "^(.+)$",
					FieldUsername: "cn",
					RegexUsername: "^(.+)$",
					FieldName:     "displayName",
					RegexName:     "^(.+)$",
					FieldEmail:    "mail",
					RegexEmail:    "^(.+)$",
					FieldPhoto:    "jpegPhoto",
					RegexPhoto:    "^(.+)$",

					AutoRegister:      true,
					AutoRegisterRoles: []string{"admin", "user"},

					GuessCategory: true,
					FieldCategory: "ou",
					RegexCategory: "^(.+)$",

					FieldGroup:   "memberOf",
					RegexGroup:   "cn=([^,]+)",
					GroupDefault: "default-group",

					FieldRole:       "role",
					RegexRole:       "^(.+)$",
					RoleAdminIDs:    []string{"admin-group"},
					RoleManagerIDs:  []string{"manager-group"},
					RoleAdvancedIDs: []string{"advanced-group"},
					RoleUserIDs:     []string{"user-group"},
					RoleDefault:     model.RoleUser,

					LogoutRedirectURL: "https://idp.example.com/logout",

					SaveEmail: true,
				}
			},
			Expected: expected{
				Cfg: &SAMLConfig{
					FieldUID:      "uid",
					FieldUsername: "cn",
					FieldName:     "displayName",
					FieldEmail:    "mail",
					FieldPhoto:    "jpegPhoto",

					AutoRegister:      true,
					AutoRegisterRoles: []string{"admin", "user"},

					GuessCategory: true,
					FieldCategory: "ou",

					FieldGroup:   "memberOf",
					GroupDefault: "default-group",

					FieldRole: "role",

					RoleAdminIDs:    []string{"admin-group"},
					RoleManagerIDs:  []string{"manager-group"},
					RoleAdvancedIDs: []string{"advanced-group"},
					RoleUserIDs:     []string{"user-group"},
					RoleDefault:     model.RoleUser,

					LogoutRedirectURL: "https://idp.example.com/logout",

					SaveEmail: true,
				},
				MaxIssueDelay: 5 * time.Minute,
			},
		},
		"should use the library default max issue delay if it is negative": {
			NeedTLS: true,
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile:  metadataPath,
					KeyFile:       keyPath,
					CertFile:      certPath,
					MaxIssueDelay: db.Duration(-time.Second),

					RegexUID:      ".*",
					RegexUsername: ".*",
					RegexName:     ".*",
					RegexEmail:    ".*",
					RegexPhoto:    ".*",
				}
			},
			Expected: expected{Cfg: &SAMLConfig{}},
		},
		"should return error when neither metadata file nor URL is configured": {
			NeedTLS: false,
			Input: func(t *testing.T, _, _, _ string) model.SAMLConfig {
				return model.SAMLConfig{}
			},
			Expected: expected{
				Err: "neither metadata file nor metadata URL is configured",
			},
		},
		"should return error for invalid UID regex": {
			NeedTLS: true,
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath, KeyFile: keyPath, CertFile: certPath,
					RegexUID: "[invalid",
				}
			},
			Expected: expected{Err: "invalid UID regex"},
		},
		"should return error for invalid username regex": {
			NeedTLS: true,
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath, KeyFile: keyPath, CertFile: certPath,
					RegexUID: ".*", RegexUsername: "[invalid",
				}
			},
			Expected: expected{Err: "invalid username regex"},
		},
		"should return error for invalid name regex": {
			NeedTLS: true,
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath, KeyFile: keyPath, CertFile: certPath,
					RegexUID: ".*", RegexUsername: ".*", RegexName: "[invalid",
				}
			},
			Expected: expected{Err: "invalid name regex"},
		},
		"should return error for invalid email regex": {
			NeedTLS: true,
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath, KeyFile: keyPath, CertFile: certPath,
					RegexUID: ".*", RegexUsername: ".*", RegexName: ".*",
					RegexEmail: "[invalid",
				}
			},
			Expected: expected{Err: "invalid email regex"},
		},
		"should return error for invalid photo regex": {
			NeedTLS: true,
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath, KeyFile: keyPath, CertFile: certPath,
					RegexUID: ".*", RegexUsername: ".*", RegexName: ".*",
					RegexEmail: ".*", RegexPhoto: "[invalid",
				}
			},
			Expected: expected{Err: "invalid photo regex"},
		},
		"should return error for invalid category regex": {
			NeedTLS: true,
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath, KeyFile: keyPath, CertFile: certPath,
					RegexUID: ".*", RegexUsername: ".*", RegexName: ".*",
					RegexEmail: ".*", RegexPhoto: ".*",
					GuessCategory: true, RegexCategory: "[invalid",
				}
			},
			Expected: expected{Err: "invalid category regex"},
		},
		"should return error for invalid group regex": {
			NeedTLS: true,
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath, KeyFile: keyPath, CertFile: certPath,
					RegexUID: ".*", RegexUsername: ".*", RegexName: ".*",
					RegexEmail: ".*", RegexPhoto: ".*",
					AutoRegister: true, RegexGroup: "[invalid",
				}
			},
			Expected: expected{Err: "invalid group regex"},
		},
		"should return error for invalid role regex": {
			NeedTLS: true,
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath, KeyFile: keyPath, CertFile: certPath,
					RegexUID: ".*", RegexUsername: ".*", RegexName: ".*",
					RegexEmail: ".*", RegexPhoto: ".*",
					AutoRegister: true, RegexGroup: ".*", RegexRole: "[invalid",
				}
			},
			Expected: expected{Err: "invalid role regex"},
		},
		"should set ReCategory to nil when GuessCategory is false": {
			NeedTLS: true,
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath, KeyFile: keyPath, CertFile: certPath,
					RegexUID: ".*", RegexUsername: ".*", RegexName: ".*",
					RegexEmail: ".*", RegexPhoto: ".*",
					GuessCategory: false,
				}
			},
			Expected: expected{Cfg: &SAMLConfig{}},
		},
		"should compile ReCategory when GuessCategory is true": {
			NeedTLS: true,
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath, KeyFile: keyPath, CertFile: certPath,
					RegexUID: ".*", RegexUsername: ".*", RegexName: ".*",
					RegexEmail: ".*", RegexPhoto: ".*",
					GuessCategory: true, RegexCategory: "(.*)",
				}
			},
			Expected: expected{Cfg: &SAMLConfig{GuessCategory: true}},
		},
		"should set ReGroup and ReRole to nil when AutoRegister is false": {
			NeedTLS: true,
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath, KeyFile: keyPath, CertFile: certPath,
					RegexUID: ".*", RegexUsername: ".*", RegexName: ".*",
					RegexEmail: ".*", RegexPhoto: ".*",
					AutoRegister: false,
				}
			},
			Expected: expected{Cfg: &SAMLConfig{}},
		},
		"should compile ReGroup and ReRole when AutoRegister is true": {
			NeedTLS: true,
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath, KeyFile: keyPath, CertFile: certPath,
					RegexUID: ".*", RegexUsername: ".*", RegexName: ".*",
					RegexEmail: ".*", RegexPhoto: ".*",
					AutoRegister: true, RegexGroup: "(.*)", RegexRole: "(.*)",
				}
			},
			Expected: expected{Cfg: &SAMLConfig{AutoRegister: true}},
		},
		"should return error when key pair cannot be generated": {
			NeedTLS: false,
			Input: func(t *testing.T, _, _, _ string) model.SAMLConfig {
				dir := t.TempDir()
				metadata := `<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="https://idp.example.com/metadata">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="https://idp.example.com/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>`
				metadataPath := filepath.Join(dir, "metadata.xml")
				require.NoError(t, os.WriteFile(metadataPath, []byte(metadata), 0644))

				return model.SAMLConfig{
					MetadataFile: metadataPath,
					KeyFile:      "/nonexistent/key.pem",
					CertFile:     "/nonexistent/cert.pem",
				}
			},
			Expected: expected{Err: "ensure SAML key pair"},
		},
		"should auto-generate key pair when files are missing": {
			NeedTLS: false,
			Input: func(t *testing.T, _, _, _ string) model.SAMLConfig {
				dir := t.TempDir()
				metadata := `<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="https://idp.example.com/metadata">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="https://idp.example.com/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>`
				metadataPath := filepath.Join(dir, "metadata.xml")
				require.NoError(t, os.WriteFile(metadataPath, []byte(metadata), 0644))

				return model.SAMLConfig{
					MetadataFile:  metadataPath,
					KeyFile:       filepath.Join(dir, "isardvdi.key"),
					CertFile:      filepath.Join(dir, "isardvdi.cert"),
					RegexUID:      ".*",
					RegexUsername: ".*",
					RegexName:     ".*",
					RegexEmail:    ".*",
					RegexPhoto:    ".*",
				}
			},
			Expected: expected{Cfg: &SAMLConfig{}},
		},
		"should fallback to URL when metadata file has invalid XML": {
			NeedTLS:     false,
			ValidateURL: func(string) error { return nil },
			Input: func(t *testing.T, _, _, _ string) model.SAMLConfig {
				dir := t.TempDir()
				invalidMetadata := filepath.Join(dir, "bad.xml")
				require.NoError(t, os.WriteFile(invalidMetadata, []byte("not xml"), 0644))

				return model.SAMLConfig{
					MetadataFile: invalidMetadata,
					MetadataURL:  "https://idp.example.com/metadata",
				}
			},
			Expected: expected{Err: "fetch metadata from URL failed"},
		},
		"should fallback to URL when metadata file does not exist": {
			NeedTLS:     false,
			ValidateURL: func(string) error { return nil },
			Input: func(t *testing.T, _, _, _ string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: "/nonexistent/metadata.xml",
					MetadataURL:  "https://idp.example.com/metadata",
				}
			},
			Expected: expected{Err: "fetch metadata from URL failed"},
		},
		"should return error for invalid metadata URL": {
			NeedTLS: false,
			Input: func(t *testing.T, _, _, _ string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataURL: "://invalid-url",
				}
			},
			Expected: expected{Err: "invalid metadata URL"},
		},
		"should fallback to URL and load config when metadata file does not exist": {
			NeedTLS:     true,
			ValidateURL: func(string) error { return nil },
			Input: func(t *testing.T, certPath, keyPath, _ string) model.SAMLConfig {
				idp := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					w.Header().Set("Content-Type", "application/xml")
					w.Write([]byte(`<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="https://idp.example.com/metadata">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="https://idp.example.com/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>`))
				}))
				t.Cleanup(idp.Close)

				return model.SAMLConfig{
					MetadataFile:    "/nonexistent/metadata.xml",
					MetadataURL:     idp.URL,
					EntityID:        "https://sp.example.com",
					SignatureMethod: "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
					KeyFile:         keyPath,
					CertFile:        certPath,
					MaxIssueDelay:   db.Duration(5 * time.Minute),

					FieldUID:      "uid",
					RegexUID:      "^(.+)$",
					FieldUsername: "cn",
					RegexUsername: "^(.+)$",
					FieldName:     "displayName",
					RegexName:     "^(.+)$",
					FieldEmail:    "mail",
					RegexEmail:    "^(.+)$",
					FieldPhoto:    "jpegPhoto",
					RegexPhoto:    "^(.+)$",

					AutoRegister:      true,
					AutoRegisterRoles: []string{"admin", "user"},

					GuessCategory: true,
					FieldCategory: "ou",
					RegexCategory: "^(.+)$",

					FieldGroup:   "memberOf",
					RegexGroup:   "cn=([^,]+)",
					GroupDefault: "default-group",

					FieldRole:       "role",
					RegexRole:       "^(.+)$",
					RoleAdminIDs:    []string{"admin-group"},
					RoleManagerIDs:  []string{"manager-group"},
					RoleAdvancedIDs: []string{"advanced-group"},
					RoleUserIDs:     []string{"user-group"},
					RoleDefault:     model.RoleUser,

					LogoutRedirectURL: "https://idp.example.com/logout",

					SaveEmail: true,

					AllowInsecureTLS: true,
				}
			},
			Expected: expected{
				Cfg: &SAMLConfig{
					FieldUID:      "uid",
					FieldUsername: "cn",
					FieldName:     "displayName",
					FieldEmail:    "mail",
					FieldPhoto:    "jpegPhoto",

					AutoRegister:      true,
					AutoRegisterRoles: []string{"admin", "user"},

					GuessCategory: true,
					FieldCategory: "ou",

					FieldGroup:   "memberOf",
					GroupDefault: "default-group",

					FieldRole: "role",

					RoleAdminIDs:    []string{"admin-group"},
					RoleManagerIDs:  []string{"manager-group"},
					RoleAdvancedIDs: []string{"advanced-group"},
					RoleUserIDs:     []string{"user-group"},
					RoleDefault:     model.RoleUser,

					LogoutRedirectURL: "https://idp.example.com/logout",

					SaveEmail: true,
				},
				MaxIssueDelay: 5 * time.Minute,
			},
		},
		"should fail to fetch metadata from self-signed URL when allow_insecure_tls is false": {
			NeedTLS:     true,
			ValidateURL: func(string) error { return nil },
			Input: func(t *testing.T, certPath, keyPath, _ string) model.SAMLConfig {
				idp := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					w.Header().Set("Content-Type", "application/xml")
					w.Write([]byte(`<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="https://idp.example.com/metadata">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="https://idp.example.com/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>`))
				}))
				t.Cleanup(idp.Close)

				return model.SAMLConfig{
					MetadataFile: "/nonexistent/metadata.xml",
					MetadataURL:  idp.URL,
					KeyFile:      keyPath,
					CertFile:     certPath,

					RegexUID:      ".*",
					RegexUsername: ".*",
					RegexName:     ".*",
					RegexEmail:    ".*",
					RegexPhoto:    ".*",

					AllowInsecureTLS: false,
				}
			},
			Expected: expected{Err: "fetch metadata from URL failed"},
		},
		"should fail to fetch metadata from self-signed URL when allow_insecure_tls is turned off": {
			NeedTLS:     true,
			ValidateURL: func(string) error { return nil },
			PreviousInput: func(t *testing.T, certPath, keyPath, _ string) model.SAMLConfig {
				idp := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					w.Header().Set("Content-Type", "application/xml")
					w.Write([]byte(`<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="https://idp.example.com/metadata">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="https://idp.example.com/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>`))
				}))
				t.Cleanup(idp.Close)

				return model.SAMLConfig{
					MetadataFile: "/nonexistent/metadata.xml",
					MetadataURL:  idp.URL,
					KeyFile:      keyPath,
					CertFile:     certPath,

					RegexUID:      ".*",
					RegexUsername: ".*",
					RegexName:     ".*",
					RegexEmail:    ".*",
					RegexPhoto:    ".*",

					AllowInsecureTLS: true,
				}
			},
			Input: func(t *testing.T, certPath, keyPath, _ string) model.SAMLConfig {
				idp := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					w.Header().Set("Content-Type", "application/xml")
					w.Write([]byte(`<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="https://idp.example.com/metadata">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="https://idp.example.com/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>`))
				}))
				t.Cleanup(idp.Close)

				return model.SAMLConfig{
					MetadataFile: "/nonexistent/metadata.xml",
					MetadataURL:  idp.URL,
					KeyFile:      keyPath,
					CertFile:     certPath,

					RegexUID:      ".*",
					RegexUsername: ".*",
					RegexName:     ".*",
					RegexEmail:    ".*",
					RegexPhoto:    ".*",

					AllowInsecureTLS: false,
				}
			},
			Expected: expected{Err: "fetch metadata from URL failed"},
		},
		"should use category-specific SAML endpoint paths when categoryID is set": {
			NeedTLS:    true,
			CategoryID: strPtr("my-category"),
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath,
					EntityID:     "https://sp.example.com",
					KeyFile:      keyPath,
					CertFile:     certPath,

					RegexUID:      ".*",
					RegexUsername: ".*",
					RegexName:     ".*",
					RegexEmail:    ".*",
					RegexPhoto:    ".*",
				}
			},
			Expected: expected{Cfg: &SAMLConfig{}},
		},
		"should create branding middleware when branding host is set": {
			NeedTLS:       true,
			CategoryID:    strPtr("my-category"),
			BrandingHosts: map[string]string{"my-category": "branding.example.com"},
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile:  metadataPath,
					EntityID:      "https://sp.example.com",
					KeyFile:       keyPath,
					CertFile:      certPath,
					MaxIssueDelay: db.Duration(5 * time.Minute),

					RegexUID:      ".*",
					RegexUsername: ".*",
					RegexName:     ".*",
					RegexEmail:    ".*",
					RegexPhoto:    ".*",
				}
			},
			Expected: expected{
				Cfg:           &SAMLConfig{},
				MaxIssueDelay: 5 * time.Minute,
			},
		},
		"should skip a branding host if its middleware cannot be built": {
			NeedTLS:    true,
			CategoryID: strPtr("my-category"),
			BrandingHosts: map[string]string{
				"my-category":    "branding.example.com",
				"other-category": "bad name.example.com",
			},
			SkippedBrandingCategories: []string{"other-category"},
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath,
					EntityID:     "https://sp.example.com",
					KeyFile:      keyPath,
					CertFile:     certPath,

					RegexUID:      ".*",
					RegexUsername: ".*",
					RegexName:     ".*",
					RegexEmail:    ".*",
					RegexPhoto:    ".*",
				}
			},
			Expected: expected{Cfg: &SAMLConfig{}},
		},
		"should not create branding middleware when branding host is nil": {
			NeedTLS:    true,
			CategoryID: strPtr("my-category"),
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath,
					EntityID:     "https://sp.example.com",
					KeyFile:      keyPath,
					CertFile:     certPath,

					RegexUID:      ".*",
					RegexUsername: ".*",
					RegexName:     ".*",
					RegexEmail:    ".*",
					RegexPhoto:    ".*",
				}
			},
			Expected: expected{Cfg: &SAMLConfig{}},
		},
		"should cache the model config after successful load": {
			NeedTLS: true,
			Input: func(t *testing.T, certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath,
					KeyFile:      keyPath,
					CertFile:     certPath,
					FieldUID:     "uid",

					RegexUID:      ".*",
					RegexUsername: ".*",
					RegexName:     ".*",
					RegexEmail:    ".*",
					RegexPhoto:    ".*",
				}
			},
			Expected: expected{Cfg: &SAMLConfig{FieldUID: "uid"}},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			var certPath string
			var keyPath string
			var metadataPath string
			if tc.NeedTLS {
				dir := t.TempDir()

				certPath = filepath.Join(dir, "cert.pem")
				keyPath = filepath.Join(dir, "key.pem")
				certCfg := pkgTls.CertConfig{CommonName: "sp.example.com", Duration: time.Hour}
				require.NoError(t, pkgTls.GenerateSelfSignedKeyPair(certPath, keyPath, certCfg))

				metadata := `<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="https://idp.example.com/metadata">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="https://idp.example.com/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>`
				metadataPath = filepath.Join(dir, "metadata.xml")
				require.NoError(t, os.WriteFile(metadataPath, []byte(metadata), 0644))
			}

			brandingHosts := tc.BrandingHosts
			if brandingHosts == nil {
				brandingHosts = map[string]string{}
			}

			validateURL := tc.ValidateURL
			if validateURL == nil {
				validateURL = validateMetadataURL
			}

			s := &SAML{
				cfg:           &cfgManager[SAMLConfig]{cfg: &SAMLConfig{}},
				host:          "sp.example.com",
				categoryID:    tc.CategoryID,
				log:           log.New("test", "debug"),
				validateURL:   validateURL,
				brandingHosts: brandingHosts,
			}

			if tc.PreviousInput != nil {
				prvInput := tc.PreviousInput(t, certPath, keyPath, metadataPath)
				require.NoError(t, s.LoadConfig(t.Context(), prvInput))
			}

			prvCfg := s.cfg.Cfg()

			input := tc.Input(t, certPath, keyPath, metadataPath)
			err := s.LoadConfig(t.Context(), input)

			if tc.Expected.Err != "" {
				assert.ErrorContains(err, tc.Expected.Err)
				assert.Equal(prvCfg, s.cfg.Cfg())
				return
			}

			assert.NoError(err)

			cfg := s.cfg.Cfg()
			exp := tc.Expected.Cfg

			require.NotNil(t, cfg.Middleware)
			assert.Equal(tc.Expected.MaxIssueDelay, cfg.Middleware.ServiceProvider.MaxIssueDelay)
			assert.Equal(90*time.Second, saml.MaxIssueDelay)

			if input.EntityID != "" {
				assert.NotNil(cfg.Middleware)
				assert.Equal(input.EntityID, cfg.Middleware.ServiceProvider.EntityID)
				assert.Equal(input.SignatureMethod, cfg.Middleware.ServiceProvider.SignatureMethod)

				if tc.CategoryID != nil {
					assert.Equal("https://sp.example.com/authentication/saml/"+*tc.CategoryID+"/acs", cfg.Middleware.ServiceProvider.AcsURL.String())
					assert.Equal("https://sp.example.com/authentication/saml/"+*tc.CategoryID+"/metadata", cfg.Middleware.ServiceProvider.MetadataURL.String())
					assert.Equal("https://sp.example.com/authentication/saml/"+*tc.CategoryID+"/slo", cfg.Middleware.ServiceProvider.SloURL.String())
				} else {
					assert.Equal("https://sp.example.com/authentication/saml/acs", cfg.Middleware.ServiceProvider.AcsURL.String())
					assert.Equal("https://sp.example.com/authentication/saml/metadata", cfg.Middleware.ServiceProvider.MetadataURL.String())
					assert.Equal("https://sp.example.com/authentication/saml/slo", cfg.Middleware.ServiceProvider.SloURL.String())
				}
			}

			assert.Equal(exp.FieldUID, cfg.FieldUID)
			assert.Equal(exp.FieldUsername, cfg.FieldUsername)
			assert.Equal(exp.FieldName, cfg.FieldName)
			assert.Equal(exp.FieldEmail, cfg.FieldEmail)
			assert.Equal(exp.FieldPhoto, cfg.FieldPhoto)

			if input.RegexUID != "" {
				assert.NotNil(cfg.ReUID)
				assert.Equal(input.RegexUID, cfg.ReUID.String())
			}
			if input.RegexUsername != "" {
				assert.NotNil(cfg.ReUsername)
				assert.Equal(input.RegexUsername, cfg.ReUsername.String())
			}
			if input.RegexName != "" {
				assert.NotNil(cfg.ReName)
				assert.Equal(input.RegexName, cfg.ReName.String())
			}
			if input.RegexEmail != "" {
				assert.NotNil(cfg.ReEmail)
				assert.Equal(input.RegexEmail, cfg.ReEmail.String())
			}
			if input.RegexPhoto != "" {
				assert.NotNil(cfg.RePhoto)
				assert.Equal(input.RegexPhoto, cfg.RePhoto.String())
			}

			assert.Equal(exp.AutoRegister, cfg.AutoRegister)
			assert.Equal(exp.AutoRegisterRoles, cfg.AutoRegisterRoles)

			assert.Equal(exp.GuessCategory, cfg.GuessCategory)
			assert.Equal(exp.FieldCategory, cfg.FieldCategory)
			if exp.GuessCategory {
				assert.NotNil(cfg.ReCategory)
			} else {
				assert.Nil(cfg.ReCategory)
			}

			assert.Equal(exp.FieldGroup, cfg.FieldGroup)
			assert.Equal(exp.GroupDefault, cfg.GroupDefault)
			if exp.AutoRegister {
				assert.NotNil(cfg.ReGroup)
				assert.NotNil(cfg.ReRole)
			} else {
				assert.Nil(cfg.ReGroup)
				assert.Nil(cfg.ReRole)
			}

			assert.Equal(exp.FieldRole, cfg.FieldRole)
			assert.Equal(exp.RoleAdminIDs, cfg.RoleAdminIDs)
			assert.Equal(exp.RoleManagerIDs, cfg.RoleManagerIDs)
			assert.Equal(exp.RoleAdvancedIDs, cfg.RoleAdvancedIDs)
			assert.Equal(exp.RoleUserIDs, cfg.RoleUserIDs)
			assert.Equal(exp.RoleDefault, cfg.RoleDefault)

			assert.Equal(exp.LogoutRedirectURL, cfg.LogoutRedirectURL)
			assert.Equal(exp.SaveEmail, cfg.SaveEmail)

			// Branding middleware assertions.
			if len(tc.BrandingHosts) > 0 {
				for catID, bHost := range tc.BrandingHosts {
					if slices.Contains(tc.SkippedBrandingCategories, catID) {
						assert.NotContains(cfg.BrandingMiddlewares, catID)
						assert.NotContains(cfg.BrandingHosts, catID)

						continue
					}

					assert.Contains(cfg.BrandingMiddlewares, catID)
					assert.NotNil(cfg.BrandingMiddlewares[catID])
					assert.Equal(bHost, cfg.BrandingHosts[catID])
					assert.Equal(tc.Expected.MaxIssueDelay, cfg.BrandingMiddlewares[catID].ServiceProvider.MaxIssueDelay)

					// Verify branding middleware uses the branding host.
					brandingACS := cfg.BrandingMiddlewares[catID].ServiceProvider.AcsURL.String()
					assert.Contains(brandingACS, bHost)
				}
			} else {
				assert.Empty(cfg.BrandingMiddlewares)
				assert.Empty(cfg.BrandingHosts)
			}

			// Model config cache assertion.
			s.brandingMux.RLock()
			assert.NotNil(s.lastModelCfg)
			s.brandingMux.RUnlock()

			// InsecureSkipVerify tracks AllowInsecureTLS.
			require.NotNil(t, cfg.HTTPClient)
			tr, ok := cfg.HTTPClient.Transport.(*http.Transport)
			require.True(t, ok, "httpClient.Transport should be *http.Transport")
			if input.AllowInsecureTLS {
				require.NotNil(t, tr.TLSClientConfig)
				assert.True(tr.TLSClientConfig.InsecureSkipVerify)
			} else if tr.TLSClientConfig != nil {
				assert.False(tr.TLSClientConfig.InsecureSkipVerify)
			}
		})
	}
}

func TestValidateMetadataURL(t *testing.T) {
	t.Parallel()

	cases := map[string]struct {
		URL         string
		ExpectedErr string
	}{
		"should accept a valid HTTPS URL with public IP": {
			// Use an IP literal to avoid relying on DNS in tests.
			// 203.0.113.1 is in TEST-NET-3 (RFC 5737), reserved for documentation.
			URL: "https://203.0.113.1/metadata",
		},
		"should reject an HTTP URL": {
			URL:         "http://203.0.113.1/metadata",
			ExpectedErr: "metadata URL must use https scheme",
		},
		"should reject a malformed URL": {
			URL:         "://invalid",
			ExpectedErr: "malformed URL",
		},
		"should reject an empty scheme": {
			URL:         "idp.example.com/metadata",
			ExpectedErr: "metadata URL must use https scheme",
		},
		"should reject a hostname that does not resolve": {
			URL:         "https://nxdomain.invalid/metadata",
			ExpectedErr: "resolve metadata URL host",
		},
		"should reject a loopback IP": {
			URL:         "https://127.0.0.1/metadata",
			ExpectedErr: "must not point to this server",
		},
		"should accept a private IP that is not this server": {
			URL: "https://10.255.255.254/metadata",
		},
		"should reject a link-local IP": {
			URL:         "https://169.254.1.1/metadata",
			ExpectedErr: "must not point to this server",
		},
		"should reject the unspecified address": {
			URL:         "https://0.0.0.0/metadata",
			ExpectedErr: "must not point to this server",
		},
		"should reject a hostname resolving to loopback": {
			URL:         "https://localhost/metadata",
			ExpectedErr: "must not point to this server",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			err := validateMetadataURL(tc.URL)

			if tc.ExpectedErr != "" {
				assert.ErrorContains(t, err, tc.ExpectedErr)
			} else {
				assert.NoError(t, err)
			}
		})
	}
}

func TestSAMLString(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Expected string
	}{
		"should return the SAML provider type": {
			Expected: types.ProviderSAML,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			s := SAML{}

			assert.Equal(tc.Expected, s.String())
		})
	}
}

func TestSAMLAutoRegister(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Cfg      SAMLConfig
		User     *model.User
		Expected bool
	}{
		"should return true when auto register is enabled and no role restrictions": {
			Cfg: SAMLConfig{
				AutoRegister: true,
			},
			User:     &model.User{UID: "test-user", Role: model.RoleUser},
			Expected: true,
		},
		"should return false when auto register is disabled": {
			Cfg: SAMLConfig{
				AutoRegister: false,
			},
			User:     &model.User{UID: "test-user", Role: model.RoleUser},
			Expected: false,
		},
		"should return true when user role is in the allowed roles list": {
			Cfg: SAMLConfig{
				AutoRegister:      true,
				AutoRegisterRoles: []string{"admin", "user"},
			},
			User:     &model.User{UID: "test-user", Role: model.RoleUser},
			Expected: true,
		},
		"should return false when user role is not in the allowed roles list": {
			Cfg: SAMLConfig{
				AutoRegister:      true,
				AutoRegisterRoles: []string{"admin"},
			},
			User:     &model.User{UID: "test-user", Role: model.RoleUser},
			Expected: false,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			s := &SAML{
				cfg: &cfgManager[SAMLConfig]{cfg: &tc.Cfg},
				log: log.New("test", "debug"),
			}

			assert.Equal(tc.Expected, s.AutoRegister(tc.User))
		})
	}
}

func TestSAMLSaveEmail(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Cfg      SAMLConfig
		Expected bool
	}{
		"should return true when SaveEmail is enabled": {
			Cfg:      SAMLConfig{SaveEmail: true},
			Expected: true,
		},
		"should return false when SaveEmail is disabled": {
			Cfg:      SAMLConfig{SaveEmail: false},
			Expected: false,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			s := &SAML{
				cfg: &cfgManager[SAMLConfig]{cfg: &tc.Cfg},
			}

			assert.Equal(tc.Expected, s.SaveEmail())
		})
	}
}

func TestSAMLLogout(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Cfg            SAMLConfig
		PrepareSAML    func(*testing.T) *SAML
		PrepareContext func(*testing.T, *SAML) context.Context
		CheckURL       func(*testing.T, *SAML, string)
		ExpectedURL    string
	}{
		"should work as expected": {
			PrepareSAML: func(t *testing.T) *SAML {
				dir := t.TempDir()

				certPath := filepath.Join(dir, "cert.pem")
				keyPath := filepath.Join(dir, "key.pem")
				certCfg := pkgTls.CertConfig{CommonName: "sp.example.com", Duration: time.Hour}
				require.NoError(t, pkgTls.GenerateSelfSignedKeyPair(certPath, keyPath, certCfg))

				metadata := `<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="https://idp.example.com/metadata">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="https://idp.example.com/sso"/>
    <md:SingleLogoutService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="https://idp.example.com/slo"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>`
				metadataPath := filepath.Join(dir, "metadata.xml")
				require.NoError(t, os.WriteFile(metadataPath, []byte(metadata), 0644))

				s := &SAML{
					cfg:           &cfgManager[SAMLConfig]{cfg: &SAMLConfig{}},
					host:          "sp.example.com",
					log:           log.New("test", "debug"),
					validateURL:   func(string) error { return nil },
					brandingHosts: map[string]string{},
				}

				cfg := model.SAMLConfig{
					MetadataFile:      metadataPath,
					EntityID:          "https://sp.example.com",
					SignatureMethod:   "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
					KeyFile:           keyPath,
					CertFile:          certPath,
					MaxIssueDelay:     db.Duration(5 * time.Minute),
					LogoutRedirectURL: "https://sp.example.com/fallback",
				}

				require.NoError(t, s.LoadConfig(t.Context(), cfg))

				return s
			},
			PrepareContext: func(t *testing.T, s *SAML) context.Context {
				mw := s.Middleware("sp.example.com")
				require.NotNil(t, mw)

				req := httptest.NewRequest(http.MethodGet, "https://sp.example.com/authentication/logout", nil)
				rec := httptest.NewRecorder()

				assertion := &saml.Assertion{
					Subject: &saml.Subject{
						NameID: &saml.NameID{
							Value: "test-name-id",
						},
					},
				}

				require.NoError(t, mw.Session.CreateSession(rec, req, assertion))

				for _, c := range rec.Result().Cookies() {
					// A browser drops the expired cookie that clears the legacy domain cookie.
					if !c.Expires.IsZero() && c.Expires.Before(time.Now()) {
						continue
					}

					req.AddCookie(c)
				}

				return context.WithValue(t.Context(), HTTPRequest, req)
			},
			CheckURL: func(t *testing.T, s *SAML, rawURL string) {
				logoutURL, err := url.Parse(rawURL)
				require.NoError(t, err)

				assert.Equal("https://idp.example.com/slo", logoutURL.Scheme+"://"+logoutURL.Host+logoutURL.Path)

				query := logoutURL.Query()

				require.NotEmpty(t, query.Get("SAMLRequest"))
				assert.Equal("http://www.w3.org/2001/04/xmldsig-more#rsa-sha256", query.Get("SigAlg"))
				require.NotEmpty(t, query.Get("Signature"))

				deflated, err := base64.StdEncoding.DecodeString(query.Get("SAMLRequest"))
				require.NoError(t, err)

				logoutReq, err := io.ReadAll(flate.NewReader(bytes.NewReader(deflated)))
				require.NoError(t, err)

				assert.Contains(string(logoutReq), "test-name-id")
				assert.NotContains(string(logoutReq), "Signature")

				signed := "SAMLRequest=" + url.QueryEscape(query.Get("SAMLRequest")) + "&SigAlg=" + url.QueryEscape(query.Get("SigAlg"))

				signature, err := base64.StdEncoding.DecodeString(query.Get("Signature"))
				require.NoError(t, err)

				hashed := sha256.Sum256([]byte(signed))

				pub, ok := s.Middleware("sp.example.com").ServiceProvider.Certificate.PublicKey.(*rsa.PublicKey)
				require.True(t, ok)

				assert.NoError(rsa.VerifyPKCS1v15(pub, crypto.SHA256, hashed[:], signature))
			},
		},
		"should return the configured logout redirect URL": {
			Cfg: SAMLConfig{
				LogoutRedirectURL: "https://idp.example.com/logout",
			},
			ExpectedURL: "https://idp.example.com/logout",
		},
		"should return empty string when no logout URL is configured": {
			Cfg:         SAMLConfig{},
			ExpectedURL: "",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			s := &SAML{
				cfg: &cfgManager[SAMLConfig]{cfg: &tc.Cfg},
			}
			if tc.PrepareSAML != nil {
				s = tc.PrepareSAML(t)
			}

			ctx := t.Context()
			if tc.PrepareContext != nil {
				ctx = tc.PrepareContext(t, s)
			}

			logoutURL, err := s.Logout(ctx, "")

			assert.NoError(err)

			if tc.CheckURL != nil {
				tc.CheckURL(t, s, logoutURL)

				return
			}

			assert.Equal(tc.ExpectedURL, logoutURL)
		})
	}
}

func TestSAMLGuessRole(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Cfg          SAMLConfig
		RawRoles     []string
		ExpectedRole model.Role
		ExpectedErr  string
	}{
		"should delegate to guessRole and return the correct role": {
			Cfg: SAMLConfig{
				ReRole:       regexp.MustCompile(".*"),
				RoleAdminIDs: []string{"admin"},
				RoleDefault:  model.RoleUser,
			},
			RawRoles:     []string{"admin"},
			ExpectedRole: model.RoleAdmin,
		},
		"should fallback to default role when no match": {
			Cfg: SAMLConfig{
				ReRole:      regexp.MustCompile(".*"),
				RoleDefault: model.RoleUser,
			},
			RawRoles:     []string{"unknown-role"},
			ExpectedRole: model.RoleUser,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			s := &SAML{
				cfg: &cfgManager[SAMLConfig]{cfg: &tc.Cfg},
			}

			role, err := s.GuessRole(context.Background(), nil, tc.RawRoles)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.Nil(err)
				assert.Equal(tc.ExpectedRole, *role)
			}
		})
	}
}

func TestSAMLSetBrandingHost(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareProvider    func(certPath, keyPath, metadataPath string) *SAML
		CategoryID         string
		Host               *string
		ExpectedHosts      map[string]string
		ExpectBrandingKeys []string
		ExpectReload       bool
	}{
		"should store host and reload when config is cached": {
			PrepareProvider: func(certPath, keyPath, metadataPath string) *SAML {
				return &SAML{
					cfg:           &cfgManager[SAMLConfig]{cfg: &SAMLConfig{}},
					host:          "sp.example.com",
					log:           log.New("test", "debug"),
					brandingHosts: map[string]string{},
					lastModelCfg: &model.SAMLConfig{
						MetadataFile:  metadataPath,
						KeyFile:       keyPath,
						CertFile:      certPath,
						RegexUID:      ".*",
						RegexUsername: ".*",
						RegexName:     ".*",
						RegexEmail:    ".*",
						RegexPhoto:    ".*",
					},
				}
			},
			CategoryID:         "cat1",
			Host:               strPtr("branding.example.com"),
			ExpectedHosts:      map[string]string{"cat1": "branding.example.com"},
			ExpectBrandingKeys: []string{"cat1"},
			ExpectReload:       true,
		},
		"should store host without reload when no config is cached": {
			PrepareProvider: func(certPath, keyPath, metadataPath string) *SAML {
				return &SAML{
					cfg:           &cfgManager[SAMLConfig]{cfg: &SAMLConfig{}},
					host:          "sp.example.com",
					log:           log.New("test", "debug"),
					brandingHosts: map[string]string{},
				}
			},
			CategoryID:    "cat1",
			Host:          strPtr("branding.example.com"),
			ExpectedHosts: map[string]string{"cat1": "branding.example.com"},
			ExpectReload:  false,
		},
		"should clear branding when host is nil and config is cached": {
			PrepareProvider: func(certPath, keyPath, metadataPath string) *SAML {
				return &SAML{
					cfg:           &cfgManager[SAMLConfig]{cfg: &SAMLConfig{}},
					host:          "sp.example.com",
					log:           log.New("test", "debug"),
					brandingHosts: map[string]string{"cat1": "old.example.com"},
					lastModelCfg: &model.SAMLConfig{
						MetadataFile:  metadataPath,
						KeyFile:       keyPath,
						CertFile:      certPath,
						RegexUID:      ".*",
						RegexUsername: ".*",
						RegexName:     ".*",
						RegexEmail:    ".*",
						RegexPhoto:    ".*",
					},
				}
			},
			CategoryID:    "cat1",
			Host:          nil,
			ExpectedHosts: map[string]string{},
			ExpectReload:  true,
		},
		"should not affect other categories when setting host": {
			PrepareProvider: func(certPath, keyPath, metadataPath string) *SAML {
				return &SAML{
					cfg:           &cfgManager[SAMLConfig]{cfg: &SAMLConfig{}},
					host:          "sp.example.com",
					log:           log.New("test", "debug"),
					brandingHosts: map[string]string{"other": "other.example.com"},
					lastModelCfg: &model.SAMLConfig{
						MetadataFile:  metadataPath,
						KeyFile:       keyPath,
						CertFile:      certPath,
						RegexUID:      ".*",
						RegexUsername: ".*",
						RegexName:     ".*",
						RegexEmail:    ".*",
						RegexPhoto:    ".*",
					},
				}
			},
			CategoryID:         "cat1",
			Host:               strPtr("branding.example.com"),
			ExpectedHosts:      map[string]string{"other": "other.example.com", "cat1": "branding.example.com"},
			ExpectBrandingKeys: []string{"other", "cat1"},
			ExpectReload:       true,
		},
		"should not affect other categories when clearing host": {
			PrepareProvider: func(certPath, keyPath, metadataPath string) *SAML {
				return &SAML{
					cfg:           &cfgManager[SAMLConfig]{cfg: &SAMLConfig{}},
					host:          "sp.example.com",
					log:           log.New("test", "debug"),
					brandingHosts: map[string]string{"other": "other.example.com", "cat1": "old.example.com"},
					lastModelCfg: &model.SAMLConfig{
						MetadataFile:  metadataPath,
						KeyFile:       keyPath,
						CertFile:      certPath,
						RegexUID:      ".*",
						RegexUsername: ".*",
						RegexName:     ".*",
						RegexEmail:    ".*",
						RegexPhoto:    ".*",
					},
				}
			},
			CategoryID:         "cat1",
			Host:               nil,
			ExpectedHosts:      map[string]string{"other": "other.example.com"},
			ExpectBrandingKeys: []string{"other"},
			ExpectReload:       true,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			dir := t.TempDir()

			certPath := filepath.Join(dir, "cert.pem")
			keyPath := filepath.Join(dir, "key.pem")
			certCfg := pkgTls.CertConfig{CommonName: "sp.example.com", Duration: time.Hour}
			require.NoError(t, pkgTls.GenerateSelfSignedKeyPair(certPath, keyPath, certCfg))

			metadata := `<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="https://idp.example.com/metadata">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="https://idp.example.com/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>`
			metadataPath := filepath.Join(dir, "metadata.xml")
			require.NoError(t, os.WriteFile(metadataPath, []byte(metadata), 0644))

			s := tc.PrepareProvider(certPath, keyPath, metadataPath)

			err := s.SetBrandingHost(t.Context(), tc.CategoryID, tc.Host)
			assert.NoError(err)

			assert.Equal(tc.ExpectedHosts, s.getBrandingHosts())

			cfg := s.cfg.Cfg()
			for _, key := range tc.ExpectBrandingKeys {
				assert.Contains(cfg.BrandingMiddlewares, key)
				assert.NotNil(cfg.BrandingMiddlewares[key])
				assert.Contains(cfg.BrandingHosts, key)
			}

			if len(tc.ExpectBrandingKeys) == 0 && tc.ExpectReload {
				assert.Empty(cfg.BrandingMiddlewares)
				assert.Empty(cfg.BrandingHosts)
			}
		})
	}
}

func TestSAMLMiddleware(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		BrandingHosts      map[string]string
		RequestHost        string
		ExpectBrandingUsed bool
		ExpectBrandingCat  string
	}{
		"should return branding middleware when host matches branding": {
			BrandingHosts:      map[string]string{"cat1": "branding.example.com"},
			RequestHost:        "branding.example.com",
			ExpectBrandingUsed: true,
			ExpectBrandingCat:  "cat1",
		},
		"should return primary middleware when host matches main domain": {
			BrandingHosts:      map[string]string{"cat1": "branding.example.com"},
			RequestHost:        "sp.example.com",
			ExpectBrandingUsed: false,
		},
		"should return primary middleware when no branding is configured": {
			BrandingHosts:      map[string]string{},
			RequestHost:        "sp.example.com",
			ExpectBrandingUsed: false,
		},
		"should fallback to primary middleware for unknown host": {
			BrandingHosts:      map[string]string{"cat1": "branding.example.com"},
			RequestHost:        "unknown.example.com",
			ExpectBrandingUsed: false,
		},
		"should return correct branding middleware for multi-category": {
			BrandingHosts:      map[string]string{"cat1": "cat1.example.com", "cat2": "cat2.example.com"},
			RequestHost:        "cat2.example.com",
			ExpectBrandingUsed: true,
			ExpectBrandingCat:  "cat2",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			dir := t.TempDir()

			certPath := filepath.Join(dir, "cert.pem")
			keyPath := filepath.Join(dir, "key.pem")
			certCfg := pkgTls.CertConfig{CommonName: "sp.example.com", Duration: time.Hour}
			require.NoError(t, pkgTls.GenerateSelfSignedKeyPair(certPath, keyPath, certCfg))

			metadata := `<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="https://idp.example.com/metadata">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="https://idp.example.com/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>`
			metadataPath := filepath.Join(dir, "metadata.xml")
			require.NoError(t, os.WriteFile(metadataPath, []byte(metadata), 0644))

			s := &SAML{
				cfg:           &cfgManager[SAMLConfig]{cfg: &SAMLConfig{}},
				host:          "sp.example.com",
				log:           log.New("test", "debug"),
				brandingHosts: tc.BrandingHosts,
			}

			input := model.SAMLConfig{
				MetadataFile:  metadataPath,
				KeyFile:       keyPath,
				CertFile:      certPath,
				RegexUID:      ".*",
				RegexUsername: ".*",
				RegexName:     ".*",
				RegexEmail:    ".*",
				RegexPhoto:    ".*",
			}

			err := s.LoadConfig(t.Context(), input)
			assert.NoError(err)

			mw := s.Middleware(tc.RequestHost)
			assert.NotNil(mw)

			cfg := s.cfg.Cfg()
			if tc.ExpectBrandingUsed {
				assert.Equal(cfg.BrandingMiddlewares[tc.ExpectBrandingCat], mw)
			} else {
				assert.Equal(cfg.Middleware, mw)
			}
		})
	}
}

func TestSAMLHealthcheck(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		PrepareSAML func(*testing.T) *SAML
		Reload      bool
		ExpectedErr error
	}{
		"should work as expected": {
			PrepareSAML: func(t *testing.T) *SAML {
				handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {})
				idp := httptest.NewTLSServer(handler)
				t.Cleanup(idp.Close)

				dir := t.TempDir()

				certPath := filepath.Join(dir, "cert.pem")
				keyPath := filepath.Join(dir, "key.pem")
				certCfg := pkgTls.CertConfig{CommonName: "sp.example.com", Duration: time.Hour}
				require.NoError(t, pkgTls.GenerateSelfSignedKeyPair(certPath, keyPath, certCfg))

				metadata := `<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="https://idp.example.com/metadata">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="` + idp.URL + `/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>`
				metadataPath := filepath.Join(dir, "metadata.xml")
				require.NoError(t, os.WriteFile(metadataPath, []byte(metadata), 0644))

				s := InitSAML("", "sp.example.com", nil, log.New("test", "debug"), nil)

				cfg := model.SAMLConfig{
					MetadataFile:     metadataPath,
					KeyFile:          keyPath,
					CertFile:         certPath,
					AllowInsecureTLS: true,

					RegexUID:      ".*",
					RegexUsername: ".*",
					RegexName:     ".*",
					RegexEmail:    ".*",
					RegexPhoto:    ".*",
				}
				require.NoError(t, s.LoadConfig(t.Context(), cfg))

				return s
			},
		},
		"should work as expected if the configuration reloads at the same time": {
			PrepareSAML: func(t *testing.T) *SAML {
				handler := http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {})
				idp := httptest.NewTLSServer(handler)
				t.Cleanup(idp.Close)

				dir := t.TempDir()

				certPath := filepath.Join(dir, "cert.pem")
				keyPath := filepath.Join(dir, "key.pem")
				certCfg := pkgTls.CertConfig{CommonName: "sp.example.com", Duration: time.Hour}
				require.NoError(t, pkgTls.GenerateSelfSignedKeyPair(certPath, keyPath, certCfg))

				metadata := `<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="https://idp.example.com/metadata">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="` + idp.URL + `/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>`
				metadataPath := filepath.Join(dir, "metadata.xml")
				require.NoError(t, os.WriteFile(metadataPath, []byte(metadata), 0644))

				s := InitSAML("", "sp.example.com", nil, log.New("test", "debug"), nil)

				cfg := model.SAMLConfig{
					MetadataFile:     metadataPath,
					KeyFile:          keyPath,
					CertFile:         certPath,
					AllowInsecureTLS: true,

					RegexUID:      ".*",
					RegexUsername: ".*",
					RegexName:     ".*",
					RegexEmail:    ".*",
					RegexPhoto:    ".*",
				}
				require.NoError(t, s.LoadConfig(t.Context(), cfg))

				return s
			},
			Reload: true,
		},
		"should return an error if the configuration has never been loaded": {
			ExpectedErr: ErrNotConfigured,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			s := InitSAML("", "", nil, log.New("test", "debug"), nil)
			if tc.PrepareSAML != nil {
				s = tc.PrepareSAML(t)
			}

			var wg sync.WaitGroup
			if tc.Reload {
				cfg := *s.lastModelCfg
				wg.Go(func() {
					assert.NoError(s.LoadConfig(t.Context(), cfg))
				})
			}

			err := s.Healthcheck()
			wg.Wait()

			assert.ErrorIs(err, tc.ExpectedErr)
		})
	}
}

func strPtr(s string) *string {
	return &s
}

func TestSAMLRequestTracker(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		MaxIssueDelay        time.Duration
		RequestTrackerMaxAge time.Duration
		ExpectedMaxAge       time.Duration
	}{
		"should use the configured tracker age, not the assertion-age limit": {
			MaxIssueDelay:        90 * time.Second,
			RequestTrackerMaxAge: 30 * time.Minute,
			ExpectedMaxAge:       30 * time.Minute,
		},
		"should fall back to the default if the tracker age is unset": {
			MaxIssueDelay:        90 * time.Second,
			RequestTrackerMaxAge: 0,
			ExpectedMaxAge:       defaultSAMLRequestTrackerMaxAge,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			dir := t.TempDir()

			certPath := filepath.Join(dir, "cert.pem")
			keyPath := filepath.Join(dir, "key.pem")
			certCfg := pkgTls.CertConfig{CommonName: "sp.example.com", Duration: time.Hour}
			require.NoError(t, pkgTls.GenerateSelfSignedKeyPair(certPath, keyPath, certCfg))

			metadata := `<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="https://idp.example.com/metadata">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="https://idp.example.com/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>`
			metadataPath := filepath.Join(dir, "metadata.xml")
			require.NoError(t, os.WriteFile(metadataPath, []byte(metadata), 0644))

			s := &SAML{
				cfg:           &cfgManager[SAMLConfig]{cfg: &SAMLConfig{}},
				host:          "sp.example.com",
				log:           log.New("test", "debug"),
				validateURL:   validateMetadataURL,
				brandingHosts: map[string]string{},
			}

			require.NoError(t, s.LoadConfig(t.Context(), model.SAMLConfig{
				MetadataFile:         metadataPath,
				KeyFile:              keyPath,
				CertFile:             certPath,
				MaxIssueDelay:        db.Duration(tc.MaxIssueDelay),
				RequestTrackerMaxAge: db.Duration(tc.RequestTrackerMaxAge),
				RegexUID:             ".*",
				RegexUsername:        ".*",
				RegexName:            ".*",
				RegexEmail:           ".*",
				RegexPhoto:           ".*",
			}))

			cfg := s.cfg.Cfg()
			require.NotNil(t, cfg.Middleware)
			tracker, ok := cfg.Middleware.RequestTracker.(samlsp.CookieRequestTracker)
			require.True(t, ok, "expected a CookieRequestTracker")
			codec, ok := tracker.Codec.(samlsp.JWTTrackedRequestCodec)
			require.True(t, ok, "expected a JWTTrackedRequestCodec")

			assert.Equal(tc.ExpectedMaxAge, tracker.MaxAge)
			assert.Equal(tc.ExpectedMaxAge, codec.MaxAge)
			assert.Equal(tc.MaxIssueDelay, cfg.Middleware.ServiceProvider.MaxIssueDelay)

			// TLS ends at the proxy, so the request the service sees is plain HTTP
			rec := httptest.NewRecorder()
			req := httptest.NewRequest(http.MethodGet, "http://sp.example.com/authentication/login", nil)
			_, err := tracker.TrackRequest(rec, req, "request-id")
			require.NoError(t, err)

			cookies := rec.Result().Cookies()
			require.Len(t, cookies, 1)
			assert.Equal(http.SameSiteNoneMode, cookies[0].SameSite)
			assert.True(cookies[0].Secure)
			assert.Equal(int(tc.ExpectedMaxAge.Seconds()), cookies[0].MaxAge)
		})
	}
}
