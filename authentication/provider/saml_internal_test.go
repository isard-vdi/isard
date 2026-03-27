package provider

import (
	"context"
	"crypto/rand"
	"crypto/rsa"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"regexp"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	"gitlab.com/isard/isardvdi/pkg/db"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func generateTestCert(t *testing.T, dir string) (certPath, keyPath string) {
	t.Helper()

	key, err := rsa.GenerateKey(rand.Reader, 2048)
	require.NoError(t, err)

	template := &x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject:      pkix.Name{CommonName: "test"},
		NotBefore:    time.Now(),
		NotAfter:     time.Now().Add(time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature,
	}

	certDER, err := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	require.NoError(t, err)

	certPath = filepath.Join(dir, "cert.pem")
	certFile, err := os.Create(certPath)
	require.NoError(t, err)
	require.NoError(t, pem.Encode(certFile, &pem.Block{Type: "CERTIFICATE", Bytes: certDER}))
	require.NoError(t, certFile.Close())

	keyPath = filepath.Join(dir, "key.pem")
	keyFile, err := os.Create(keyPath)
	require.NoError(t, err)
	require.NoError(t, pem.Encode(keyFile, &pem.Block{
		Type:  "RSA PRIVATE KEY",
		Bytes: x509.MarshalPKCS1PrivateKey(key),
	}))
	require.NoError(t, keyFile.Close())

	return certPath, keyPath
}

const testSAMLMetadata = `<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" entityID="https://idp.example.com/metadata">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:SingleSignOnService Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect" Location="https://idp.example.com/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>`

func prepareSAMLFiles(t *testing.T) (certPath, keyPath, metadataPath string) {
	t.Helper()

	dir := t.TempDir()
	certPath, keyPath = generateTestCert(t, dir)

	metadataPath = filepath.Join(dir, "metadata.xml")
	require.NoError(t, os.WriteFile(metadataPath, []byte(testSAMLMetadata), 0644))

	return certPath, keyPath, metadataPath
}

func TestSAMLLoadConfig(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	nopLog := zerolog.Nop()

	type expected struct {
		Err string
		Cfg *SAMLConfig
	}

	tlsFallbackServer := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/xml")
		w.Write([]byte(testSAMLMetadata))
	}))
	t.Cleanup(tlsFallbackServer.Close)

	cases := map[string]struct {
		Input         func(certPath, keyPath, metadataPath string) model.SAMLConfig
		NeedTLS       bool
		HTTPClient    *http.Client
		CategoryID    *string
		BrandingHosts map[string]string
		Expected      expected
	}{
		"should load config with all fields from local metadata file": {
			NeedTLS: true,
			Input: func(certPath, keyPath, metadataPath string) model.SAMLConfig {
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
			},
		},
		"should return error when neither metadata file nor URL is configured": {
			NeedTLS: false,
			Input: func(_, _, _ string) model.SAMLConfig {
				return model.SAMLConfig{}
			},
			Expected: expected{
				Err: "neither metadata file nor metadata URL is configured",
			},
		},
		"should return error for invalid UID regex": {
			NeedTLS: true,
			Input: func(certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath, KeyFile: keyPath, CertFile: certPath,
					RegexUID: "[invalid",
				}
			},
			Expected: expected{Err: "invalid UID regex"},
		},
		"should return error for invalid username regex": {
			NeedTLS: true,
			Input: func(certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath, KeyFile: keyPath, CertFile: certPath,
					RegexUID: ".*", RegexUsername: "[invalid",
				}
			},
			Expected: expected{Err: "invalid username regex"},
		},
		"should return error for invalid name regex": {
			NeedTLS: true,
			Input: func(certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath, KeyFile: keyPath, CertFile: certPath,
					RegexUID: ".*", RegexUsername: ".*", RegexName: "[invalid",
				}
			},
			Expected: expected{Err: "invalid name regex"},
		},
		"should return error for invalid email regex": {
			NeedTLS: true,
			Input: func(certPath, keyPath, metadataPath string) model.SAMLConfig {
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
			Input: func(certPath, keyPath, metadataPath string) model.SAMLConfig {
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
			Input: func(certPath, keyPath, metadataPath string) model.SAMLConfig {
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
			Input: func(certPath, keyPath, metadataPath string) model.SAMLConfig {
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
			Input: func(certPath, keyPath, metadataPath string) model.SAMLConfig {
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
			Input: func(certPath, keyPath, metadataPath string) model.SAMLConfig {
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
			Input: func(certPath, keyPath, metadataPath string) model.SAMLConfig {
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
			Input: func(certPath, keyPath, metadataPath string) model.SAMLConfig {
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
			Input: func(certPath, keyPath, metadataPath string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile: metadataPath, KeyFile: keyPath, CertFile: certPath,
					RegexUID: ".*", RegexUsername: ".*", RegexName: ".*",
					RegexEmail: ".*", RegexPhoto: ".*",
					AutoRegister: true, RegexGroup: "(.*)", RegexRole: "(.*)",
				}
			},
			Expected: expected{Cfg: &SAMLConfig{AutoRegister: true}},
		},
		"should return error for invalid key pair": {
			NeedTLS: false,
			Input: func(_, _, _ string) model.SAMLConfig {
				dir := t.TempDir()
				metadataPath := filepath.Join(dir, "metadata.xml")
				require.NoError(t, os.WriteFile(metadataPath, []byte(testSAMLMetadata), 0644))

				return model.SAMLConfig{
					MetadataFile: metadataPath,
					KeyFile:      "/nonexistent/key.pem",
					CertFile:     "/nonexistent/cert.pem",
				}
			},
			Expected: expected{Err: "load key pair"},
		},
		"should fallback to URL when metadata file has invalid XML": {
			NeedTLS: false,
			Input: func(_, _, _ string) model.SAMLConfig {
				dir := t.TempDir()
				invalidMetadata := filepath.Join(dir, "bad.xml")
				require.NoError(t, os.WriteFile(invalidMetadata, []byte("not xml"), 0644))

				ts := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					http.Error(w, "not found", http.StatusInternalServerError)
				}))
				t.Cleanup(ts.Close)

				return model.SAMLConfig{
					MetadataFile: invalidMetadata,
					MetadataURL:  ts.URL,
				}
			},
			Expected: expected{Err: "fetch metadata from URL failed"},
		},
		"should fallback to URL when metadata file does not exist": {
			NeedTLS: false,
			Input: func(_, _, _ string) model.SAMLConfig {
				ts := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					http.Error(w, "not found", http.StatusInternalServerError)
				}))
				t.Cleanup(ts.Close)

				return model.SAMLConfig{
					MetadataFile: "/nonexistent/metadata.xml",
					MetadataURL:  ts.URL,
				}
			},
			Expected: expected{Err: "fetch metadata from URL failed"},
		},
		"should return error for invalid metadata URL": {
			NeedTLS: false,
			Input: func(_, _, _ string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataURL: "://invalid-url",
				}
			},
			Expected: expected{Err: "invalid metadata URL"},
		},
		"should fallback to URL and load config when metadata file does not exist": {
			NeedTLS:    true,
			HTTPClient: tlsFallbackServer.Client(),
			Input: func(certPath, keyPath, _ string) model.SAMLConfig {
				return model.SAMLConfig{
					MetadataFile:    "/nonexistent/metadata.xml",
					MetadataURL:     tlsFallbackServer.URL,
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
			},
		},
		"should use category-specific SAML endpoint paths when categoryID is set": {
			NeedTLS:    true,
			CategoryID: strPtr("my-category"),
			Input: func(certPath, keyPath, metadataPath string) model.SAMLConfig {
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
			Input: func(certPath, keyPath, metadataPath string) model.SAMLConfig {
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
			Input: func(certPath, keyPath, metadataPath string) model.SAMLConfig {
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
			Input: func(certPath, keyPath, metadataPath string) model.SAMLConfig {
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
			// NOTE: not parallel because LoadConfig writes to the
			// package-level saml.MaxIssueDelay global variable.

			var certPath, keyPath, metadataPath string
			if tc.NeedTLS {
				certPath, keyPath, metadataPath = prepareSAMLFiles(t)
			}

			brandingHosts := tc.BrandingHosts
			if brandingHosts == nil {
				brandingHosts = map[string]string{}
			}

			s := &SAML{
				cfg:           &cfgManager[SAMLConfig]{cfg: &SAMLConfig{}},
				host:          "sp.example.com",
				categoryID:    tc.CategoryID,
				log:           &nopLog,
				httpClient:    tc.HTTPClient,
				brandingHosts: brandingHosts,
			}

			input := tc.Input(certPath, keyPath, metadataPath)
			err := s.LoadConfig(context.Background(), input)

			if tc.Expected.Err != "" {
				assert.ErrorContains(err, tc.Expected.Err)
				return
			}

			assert.NoError(err)

			cfg := s.cfg.Cfg()
			exp := tc.Expected.Cfg

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
					assert.Contains(cfg.BrandingMiddlewares, catID)
					assert.NotNil(cfg.BrandingMiddlewares[catID])
					assert.Equal(bHost, cfg.BrandingHosts[catID])

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
		})
	}
}

func TestValidateMetadataURL(t *testing.T) {
	t.Parallel()

	cases := map[string]struct {
		URL         string
		ExpectedErr string
	}{
		"should accept a valid HTTPS URL": {
			URL: "https://idp.example.com/metadata",
		},
		"should reject an HTTP URL": {
			URL:         "http://idp.example.com/metadata",
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

	nopLog := zerolog.Nop()

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
				log: &nopLog,
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
		Cfg         SAMLConfig
		ExpectedURL string
	}{
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

			url, err := s.Logout(context.Background(), "")

			assert.NoError(err)
			assert.Equal(tc.ExpectedURL, url)
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
	// NOTE: not parallel because LoadConfig writes to the
	// package-level saml.MaxIssueDelay global variable.

	assert := assert.New(t)

	nopLog := zerolog.Nop()
	certPath, keyPath, metadataPath := prepareSAMLFiles(t)

	cachedCfg := &model.SAMLConfig{
		MetadataFile:  metadataPath,
		KeyFile:       keyPath,
		CertFile:      certPath,
		RegexUID:      ".*",
		RegexUsername: ".*",
		RegexName:     ".*",
		RegexEmail:    ".*",
		RegexPhoto:    ".*",
	}

	cases := map[string]struct {
		PrepareProvider    func() *SAML
		CategoryID         string
		Host               *string
		ExpectedHosts      map[string]string
		ExpectBrandingKeys []string
		ExpectReload       bool
	}{
		"should store host and reload when config is cached": {
			PrepareProvider: func() *SAML {
				return &SAML{
					cfg:           &cfgManager[SAMLConfig]{cfg: &SAMLConfig{}},
					host:          "sp.example.com",
					log:           &nopLog,
					brandingHosts: map[string]string{},
					lastModelCfg:  cachedCfg,
				}
			},
			CategoryID:         "cat1",
			Host:               strPtr("branding.example.com"),
			ExpectedHosts:      map[string]string{"cat1": "branding.example.com"},
			ExpectBrandingKeys: []string{"cat1"},
			ExpectReload:       true,
		},
		"should store host without reload when no config is cached": {
			PrepareProvider: func() *SAML {
				return &SAML{
					cfg:           &cfgManager[SAMLConfig]{cfg: &SAMLConfig{}},
					host:          "sp.example.com",
					log:           &nopLog,
					brandingHosts: map[string]string{},
				}
			},
			CategoryID:    "cat1",
			Host:          strPtr("branding.example.com"),
			ExpectedHosts: map[string]string{"cat1": "branding.example.com"},
			ExpectReload:  false,
		},
		"should clear branding when host is nil and config is cached": {
			PrepareProvider: func() *SAML {
				return &SAML{
					cfg:           &cfgManager[SAMLConfig]{cfg: &SAMLConfig{}},
					host:          "sp.example.com",
					log:           &nopLog,
					brandingHosts: map[string]string{"cat1": "old.example.com"},
					lastModelCfg:  cachedCfg,
				}
			},
			CategoryID:    "cat1",
			Host:          nil,
			ExpectedHosts: map[string]string{},
			ExpectReload:  true,
		},
		"should not affect other categories when setting host": {
			PrepareProvider: func() *SAML {
				return &SAML{
					cfg:           &cfgManager[SAMLConfig]{cfg: &SAMLConfig{}},
					host:          "sp.example.com",
					log:           &nopLog,
					brandingHosts: map[string]string{"other": "other.example.com"},
					lastModelCfg:  cachedCfg,
				}
			},
			CategoryID:         "cat1",
			Host:               strPtr("branding.example.com"),
			ExpectedHosts:      map[string]string{"other": "other.example.com", "cat1": "branding.example.com"},
			ExpectBrandingKeys: []string{"other", "cat1"},
			ExpectReload:       true,
		},
		"should not affect other categories when clearing host": {
			PrepareProvider: func() *SAML {
				return &SAML{
					cfg:           &cfgManager[SAMLConfig]{cfg: &SAMLConfig{}},
					host:          "sp.example.com",
					log:           &nopLog,
					brandingHosts: map[string]string{"other": "other.example.com", "cat1": "old.example.com"},
					lastModelCfg:  cachedCfg,
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
			// NOTE: not parallel because LoadConfig writes to the
			// package-level saml.MaxIssueDelay global variable.

			s := tc.PrepareProvider()

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
	// NOTE: not parallel because LoadConfig writes to the
	// package-level saml.MaxIssueDelay global variable.

	assert := assert.New(t)

	nopLog := zerolog.Nop()
	certPath, keyPath, metadataPath := prepareSAMLFiles(t)

	baseCfg := model.SAMLConfig{
		MetadataFile:  metadataPath,
		KeyFile:       keyPath,
		CertFile:      certPath,
		RegexUID:      ".*",
		RegexUsername: ".*",
		RegexName:     ".*",
		RegexEmail:    ".*",
		RegexPhoto:    ".*",
	}

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
			// NOTE: not parallel because LoadConfig writes to the
			// package-level saml.MaxIssueDelay global variable.

			s := &SAML{
				cfg:           &cfgManager[SAMLConfig]{cfg: &SAMLConfig{}},
				host:          "sp.example.com",
				log:           &nopLog,
				brandingHosts: tc.BrandingHosts,
			}

			err := s.LoadConfig(t.Context(), baseCfg)
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

func strPtr(s string) *string {
	return &s
}
