package haproxysync_test

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"os"
	"path/filepath"
	"testing"
	"time"

	"gitlab.com/isard/isardvdi/haproxy-sync/acme"
	"gitlab.com/isard/isardvdi/haproxy-sync/cfg"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy"
	"gitlab.com/isard/isardvdi/haproxy-sync/haproxy-sync"
	"gitlab.com/isard/isardvdi/pkg/log"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/mock"
	"github.com/stretchr/testify/require"
)

// certPEM returns a self-signed certificate for dnsName valid until notAfter, followed by a key:
// the key of that certificate, or an unrelated one when mismatchedKey is set.
func certPEM(t *testing.T, dnsName string, notAfter time.Time, mismatchedKey bool) []byte {
	t.Helper()

	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	require.NoError(t, err)

	tmpl := &x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject:      pkix.Name{CommonName: dnsName},
		DNSNames:     []string{dnsName},
		NotBefore:    time.Now().Add(-time.Hour),
		NotAfter:     notAfter,
	}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, &key.PublicKey, key)
	require.NoError(t, err)

	if mismatchedKey {
		key, err = ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
		require.NoError(t, err)
	}
	keyDER, err := x509.MarshalECPrivateKey(key)
	require.NoError(t, err)

	return append(pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}),
		pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: keyDER})...)
}

const brand = "brand.example.com"

// syncBrand runs a DomainSync for brand with the given files on disk and returns what was served.
func syncBrand(t *testing.T, onDisk []byte, acmeManaged bool, provided []byte, expectACME bool) []byte {
	t.Helper()
	require := require.New(t)

	dir, acmeDir := t.TempDir(), t.TempDir()
	certPath := filepath.Join(dir, brand+".pem")
	if onDisk != nil {
		require.NoError(os.WriteFile(certPath, onDisk, 0o600))
	}
	if acmeManaged {
		require.NoError(os.MkdirAll(filepath.Join(acmeDir, brand+"_ecc"), 0o700))
		require.NoError(os.WriteFile(filepath.Join(acmeDir, brand+"_ecc", brand+".cer"), []byte("x"), 0o600))
	}

	var served []byte
	m := haproxy.NewMockHaproxy(t)
	m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
	m.On("NewSslCert", certPath).Return(nil).Once()
	m.On("SetSslCert", certPath, mock.Anything).Run(func(args mock.Arguments) { served = args.Get(1).([]byte) }).Return(nil).Once()
	m.On("CommitSslCert", certPath).Return(nil).Once()
	m.On("AddSslCrtList", "/certs/crt-list.cfg", certPath).Return(nil).Once()
	m.On("AddMap", "virt@domains", brand).Return(nil).Once()

	fresh := certPEM(t, brand, time.Now().Add(90*24*time.Hour), false)
	acmeMock := acme.NewMockAcme(t)
	if expectACME {
		acmeMock.On("IssueCert", mock.Anything, brand, brand+".pem").Run(func(mock.Arguments) {
			require.NoError(os.WriteFile(certPath, fresh, 0o600))
		}).Return(nil).Once()
	}

	svc := haproxysync.Init(log.New("test", "debug"), cfg.HAProxy{
		Domains: cfg.HAProxyDomains{DomainsMap: "virt@domains", CrtListPath: "/certs/crt-list.cfg", CertsPath: dir, ACMEPath: acmeDir},
	}, m, acmeMock)

	result, err := svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{{Name: brand, Certificate: provided}})
	require.NoError(err)
	require.Equal(1, result.DomainsAdded)
	require.Empty(result.FailedDomains)

	return served
}

func TestAResyncReusesAValidACMECertificateOnDisk(t *testing.T) {
	valid := certPEM(t, brand, time.Now().Add(60*24*time.Hour), false)
	assert.Equal(t, valid, syncBrand(t, valid, true, nil, false))
}

func TestACertificateOnDiskIsNotReusedWhenItCannotBeTrusted(t *testing.T) {
	cases := map[string]struct {
		OnDisk      func(*testing.T) []byte
		ACMEManaged bool
	}{
		"expired":               {OnDisk: func(t *testing.T) []byte { return certPEM(t, brand, time.Now().Add(-24*time.Hour), false) }, ACMEManaged: true},
		"expires in three days": {OnDisk: func(t *testing.T) []byte { return certPEM(t, brand, time.Now().Add(72*time.Hour), false) }, ACMEManaged: true},
		"issued for another name": {OnDisk: func(t *testing.T) []byte {
			return certPEM(t, "other.example.org", time.Now().Add(60*24*time.Hour), false)
		}, ACMEManaged: true},
		"key does not match": {OnDisk: func(t *testing.T) []byte { return certPEM(t, brand, time.Now().Add(60*24*time.Hour), true) }, ACMEManaged: true},
		"left by a custom certificate, not managed by acme.sh": {OnDisk: func(t *testing.T) []byte { return certPEM(t, brand, time.Now().Add(60*24*time.Hour), false) }},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			old := tc.OnDisk(t)
			served := syncBrand(t, old, tc.ACMEManaged, nil, true)
			assert.NotEqual(t, old, served, "the untrusted certificate on disk was served")
		})
	}
}

func TestAProvidedCertificateAlwaysWinsOverTheOneOnDisk(t *testing.T) {
	onDisk := certPEM(t, brand, time.Now().Add(60*24*time.Hour), false)
	custom := certPEM(t, brand, time.Now().Add(300*24*time.Hour), false)

	assert.Equal(t, custom, syncBrand(t, onDisk, true, custom, false))
}

func TestRemovingADomainDeletesItsCertificateFile(t *testing.T) {
	require := require.New(t)

	dir := t.TempDir()
	certPath := filepath.Join(dir, "gone.example.com.pem")
	require.NoError(os.WriteFile(certPath, certPEM(t, "gone.example.com", time.Now().Add(60*24*time.Hour), false), 0o600))

	m := haproxy.NewMockHaproxy(t)
	m.On("ShowMap", "virt@domains").Return([]string{"gone.example.com"}, nil).Once()
	m.On("DelMap", "virt@domains", "gone.example.com").Return(nil).Once()
	m.On("DelSslCrtList", "/certs/crt-list.cfg", certPath).Return(nil).Once()
	m.On("DelSslCert", certPath).Return(nil).Once()

	// a custom certificate is not in acme.sh, so the removal script fails before deleting the file
	acmeMock := acme.NewMockAcme(t)
	acmeMock.On("RemoveCert", mock.Anything, "gone.example.com", "gone.example.com.pem").Return(nil).Once()

	svc := haproxysync.Init(log.New("test", "debug"), cfg.HAProxy{
		Domains: cfg.HAProxyDomains{DomainsMap: "virt@domains", CrtListPath: "/certs/crt-list.cfg", CertsPath: dir},
	}, m, acmeMock)

	_, err := svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{})
	require.NoError(err)
	require.NoFileExists(certPath)
}
