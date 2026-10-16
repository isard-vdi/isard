package haproxysync_test

import (
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

// pathsSvc returns a service whose certificates live in <base>/certs, with base left free for
// files that must never be touched.
func pathsSvc(t *testing.T, m *haproxy.MockHaproxy, a *acme.MockAcme) (*haproxysync.HAproxySync, string, string) {
	t.Helper()

	base := t.TempDir()
	certs := filepath.Join(base, "certs")
	require.NoError(t, os.MkdirAll(certs, 0o700))

	return haproxysync.Init(log.New("test", "debug"), cfg.HAProxy{
		Domains: cfg.HAProxyDomains{DomainsMap: "virt@domains", CrtListPath: "/certs/crt-list.cfg", CertsPath: certs},
	}, m, a), base, certs
}

func TestRemovingAnInvalidMapEntryTouchesNoFile(t *testing.T) {
	for _, entry := range []string{"../victim", "../../victim", "/victim", "Victim.example.com", ""} {
		t.Run(entry, func(t *testing.T) {
			m := haproxy.NewMockHaproxy(t)
			m.On("ShowMap", "virt@domains").Return([]string{entry}, nil).Once()
			m.On("DelMap", "virt@domains", entry).Return(nil).Once()
			// no DelSslCrtList, DelSslCert or RemoveCert expectations: any of them fails the test
			a := acme.NewMockAcme(t)

			svc, base, _ := pathsSvc(t, m, a)
			victim := filepath.Join(base, "victim.pem")
			require.NoError(t, os.WriteFile(victim, []byte("keep me"), 0o600))

			result, err := svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{})
			require.NoError(t, err)
			assert.Equal(t, 1, result.DomainsRemoved)
			assert.FileExists(t, victim)
		})
	}
}

func TestRemovingADomainDoesNotFollowASymlink(t *testing.T) {
	const d = "brand.example.com"

	m := haproxy.NewMockHaproxy(t)
	a := acme.NewMockAcme(t)
	svc, base, certs := pathsSvc(t, m, a)

	outside := filepath.Join(base, "outside.pem")
	require.NoError(t, os.WriteFile(outside, certPEM(t, d, time.Now().Add(60*24*time.Hour), false), 0o600))
	link := filepath.Join(certs, d+".pem")
	require.NoError(t, os.Symlink(outside, link))

	m.On("ShowMap", "virt@domains").Return([]string{d}, nil).Once()
	m.On("DelMap", "virt@domains", d).Return(nil).Once()
	m.On("DelSslCrtList", "/certs/crt-list.cfg", link).Return(nil).Once()
	m.On("DelSslCert", link).Return(nil).Once()
	a.On("RemoveCert", mock.Anything, d, d+".pem").Return(nil).Once()

	_, err := svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{})
	require.NoError(t, err)
	assert.FileExists(t, outside)
	_, err = os.Lstat(link)
	assert.NoError(t, err, "the symlink is not ours to delete")
}

func TestAProvidedCertificateIsNotWrittenThroughASymlink(t *testing.T) {
	const d = "brand.example.com"

	m := haproxy.NewMockHaproxy(t)
	m.On("ShowMap", "virt@domains").Return([]string{}, nil).Once()
	a := acme.NewMockAcme(t)
	svc, base, certs := pathsSvc(t, m, a)

	outside := filepath.Join(base, "outside")
	require.NoError(t, os.WriteFile(outside, []byte("keep me"), 0o600))
	require.NoError(t, os.Symlink(outside, filepath.Join(certs, d+".pem")))

	result, err := svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{
		{Name: d, Certificate: certPEM(t, d, time.Now().Add(60*24*time.Hour), false)},
	})
	require.NoError(t, err)
	require.Len(t, result.FailedDomains, 1)

	content, err := os.ReadFile(outside)
	require.NoError(t, err)
	assert.Equal(t, "keep me", string(content))
}

func TestDomainsThatDifferOnlyInCaseCannotShareACertificateFile(t *testing.T) {
	const owner = "brand.example.com"

	m := haproxy.NewMockHaproxy(t)
	m.On("ShowMap", "virt@domains").Return([]string{owner}, nil).Once()
	a := acme.NewMockAcme(t)
	svc, _, certs := pathsSvc(t, m, a)

	ownerFile := filepath.Join(certs, owner+".pem")
	ownerPEM := certPEM(t, owner, time.Now().Add(60*24*time.Hour), false)
	require.NoError(t, os.WriteFile(ownerFile, ownerPEM, 0o600))

	result, err := svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{
		{Name: owner},
		{Name: "Brand.Example.com", Certificate: certPEM(t, "Brand.Example.com", time.Now().Add(60*24*time.Hour), false)},
	})
	require.NoError(t, err)
	require.Len(t, result.FailedDomains, 1)
	assert.Equal(t, "Brand.Example.com", result.FailedDomains[0].Domain)

	content, err := os.ReadFile(ownerFile)
	require.NoError(t, err)
	assert.Equal(t, ownerPEM, content)
}

func TestRemovingADomainKeepsAFileThatHoldsAnotherDomainsCertificate(t *testing.T) {
	const gone = "gone.example.com"

	m := haproxy.NewMockHaproxy(t)
	a := acme.NewMockAcme(t)
	svc, _, certs := pathsSvc(t, m, a)

	file := filepath.Join(certs, gone+".pem")
	require.NoError(t, os.WriteFile(file, certPEM(t, "other.example.org", time.Now().Add(60*24*time.Hour), false), 0o600))

	m.On("ShowMap", "virt@domains").Return([]string{gone}, nil).Once()
	m.On("DelMap", "virt@domains", gone).Return(nil).Once()
	m.On("DelSslCrtList", "/certs/crt-list.cfg", file).Return(nil).Once()
	m.On("DelSslCert", file).Return(nil).Once()
	a.On("RemoveCert", mock.Anything, gone, gone+".pem").Return(nil).Once()

	_, err := svc.DomainSync(t.Context(), []haproxysync.DomainSyncDomain{})
	require.NoError(t, err)
	assert.FileExists(t, file)
}
