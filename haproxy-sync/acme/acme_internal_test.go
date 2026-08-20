package acme

import (
	"context"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"

	"github.com/rs/zerolog"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

// The password is the reason this file exists. It reaches the issuance script
// on stdin rather than as an argument, because an argument lives in
// /proc/<pid>/cmdline for the length of the issuance -- readable by anything
// else in the container, and printed by any ps an operator runs while
// debugging the failure that made them look.
//
// The tests below assert both halves of that: it IS on stdin, and it is NOT
// anywhere else. Asserting only the first would pass just as well if the
// password were sent twice.

const testPassword = "htB9mR9DYgcu9bX_afHF62erXaH2TS7bg9KW3F7Z"

func testCreds() ACMEDNSCredentials {
	return ACMEDNSCredentials{
		BaseURL:   "https://auth.example.com",
		Username:  "eabcdb41-d89f-4580-826f-3e62e9755ef2",
		Password:  testPassword,
		Subdomain: "d420c923-bbd7-4056-ab64-c3ca54c9b3cf",
	}
}

// newTestACME builds an ACME whose issuance script is a stub recording what it
// was given, and returns readers for each channel the stub can observe.
func newTestACME(t *testing.T, exitCode int, writePem bool) (*ACME, func() []string, func() string, func() string) {
	t.Helper()

	dir := t.TempDir()
	certsDir := filepath.Join(dir, "certs")
	require.NoError(t, os.MkdirAll(certsDir, 0755))

	argvPath := filepath.Join(dir, "argv")
	stdinPath := filepath.Join(dir, "stdin")
	envPath := filepath.Join(dir, "env")
	scriptPath := filepath.Join(dir, "issue-dns.sh")

	// One argument per line, so the assertions can talk about argv boundaries
	// rather than about a flattened command line.
	script := `#!/bin/sh
for a in "$@"; do echo "$a" >> "` + argvPath + `"; done
cat > "` + stdinPath + `"
{
  echo "ACMEDNS_BASE_URL=$ACMEDNS_BASE_URL"
  echo "ACMEDNS_USERNAME=$ACMEDNS_USERNAME"
  echo "ACMEDNS_SUBDOMAIN=$ACMEDNS_SUBDOMAIN"
  echo "ACMEDNS_PASSWORD=${ACMEDNS_PASSWORD:-<unset>}"
} > "` + envPath + `"
# Whatever acme.sh would have printed. The real script keeps this in a file
# rather than letting it out, so nothing here should reach an error string.
echo "POST https://auth.example.com/update X-Api-Key: ` + testPassword + `"
if ` + strconv.FormatBool(writePem) + `; then
  echo PEM > "` + certsDir + `/$2"
fi
exit ` + strconv.Itoa(exitCode) + `
`
	require.NoError(t, os.WriteFile(scriptPath, []byte(script), 0755))

	log := zerolog.Nop()
	a := NewACME(&log, certsDir)
	a.issueDNSScript = scriptPath

	readLines := func(path string) []string {
		data, err := os.ReadFile(path)
		if err != nil {
			return nil
		}
		return strings.Split(strings.TrimRight(string(data), "\n"), "\n")
	}
	read := func(path string) string {
		data, err := os.ReadFile(path)
		if err != nil {
			return ""
		}
		return string(data)
	}

	return a, func() []string { return readLines(argvPath) }, func() string { return read(stdinPath) },
		func() string { return read(envPath) }
}

// ── Where the password is allowed to be ──────────────────────────────────

func TestIssueCertDNSSendsThePasswordOnStdin(t *testing.T) {
	a, _, stdin, _ := newTestACME(t, 0, true)

	require.NoError(t, a.IssueCertDNS(context.Background(), "vdi.example.com", "chain.pem", testCreds()))
	assert.Equal(t, testPassword+"\n", stdin())
}

func TestIssueCertDNSKeepsThePasswordOutOfArgv(t *testing.T) {
	a, argv, _, _ := newTestACME(t, 0, true)

	require.NoError(t, a.IssueCertDNS(context.Background(), "vdi.example.com", "chain.pem", testCreds()))
	for _, arg := range argv() {
		assert.NotContains(t, arg, testPassword,
			"argv is world-readable inside the container through /proc/<pid>/cmdline")
	}
}

func TestIssueCertDNSKeepsThePasswordOutOfTheEnvironmentItPasses(t *testing.T) {
	// The script puts it in acme.sh's environment itself, from stdin. Passing
	// it in the child's environment as well would put it back in
	// /proc/<pid>/environ for the whole run without buying anything.
	a, _, _, env := newTestACME(t, 0, true)

	require.NoError(t, a.IssueCertDNS(context.Background(), "vdi.example.com", "chain.pem", testCreds()))
	assert.Contains(t, env(), "ACMEDNS_PASSWORD=<unset>")
}

func TestIssueCertDNSPassesTheOtherThreeInTheEnvironment(t *testing.T) {
	a, _, _, env := newTestACME(t, 0, true)

	require.NoError(t, a.IssueCertDNS(context.Background(), "vdi.example.com", "chain.pem", testCreds()))
	assert.Contains(t, env(), "ACMEDNS_BASE_URL=https://auth.example.com")
	assert.Contains(t, env(), "ACMEDNS_USERNAME=eabcdb41-d89f-4580-826f-3e62e9755ef2")
	assert.Contains(t, env(), "ACMEDNS_SUBDOMAIN=d420c923-bbd7-4056-ab64-c3ca54c9b3cf")
}

func TestIssueCertDNSPassesTheDomainAndPemName(t *testing.T) {
	a, argv, _, _ := newTestACME(t, 0, true)

	require.NoError(t, a.IssueCertDNS(context.Background(), "vdi.example.com", "chain.pem", testCreds()))
	assert.Equal(t, []string{"vdi.example.com", "chain.pem"}, argv())
}

// ── Failures ─────────────────────────────────────────────────────────────

func TestIssueCertDNSErrorDoesNotCarryTheScriptOutput(t *testing.T) {
	// The script keeps acme.sh's output in a file precisely because the
	// dns_acmedns plugin logs the request it makes, password included.
	// Embedding the output here would undo that: this error travels up
	// through gRPC into an apiv4 log line.
	a, _, _, _ := newTestACME(t, 1, true)

	err := a.IssueCertDNS(context.Background(), "vdi.example.com", "chain.pem", testCreds())
	require.Error(t, err)
	assert.NotContains(t, err.Error(), testPassword)
}

func TestIssueCertDNSErrorNamesTheDomain(t *testing.T) {
	a, _, _, _ := newTestACME(t, 1, true)

	err := a.IssueCertDNS(context.Background(), "vdi.example.com", "chain.pem", testCreds())
	require.Error(t, err)
	assert.Contains(t, err.Error(), "vdi.example.com")
}

func TestIssueCertDNSVerifiesTheCertificateWasWritten(t *testing.T) {
	// A script that exits 0 without producing a PEM would otherwise be
	// reported as a successful issuance, and the domain would go on being
	// served with whatever certificate was there before -- an expiry that
	// nothing reports until a browser does.
	a, _, _, _ := newTestACME(t, 0, false)

	err := a.IssueCertDNS(context.Background(), "vdi.example.com", "chain.pem", testCreds())
	assert.Error(t, err)
}

// ── Incomplete credentials ───────────────────────────────────────────────

func TestIssueCertDNSRefusesIncompleteCredentials(t *testing.T) {
	// Three of four cannot issue anything. Refusing here rather than letting
	// the script do it keeps a half-filled form from becoming an acme.sh
	// failure about DNS resolution, which sends the operator to look at their
	// zone instead of at what they just saved.
	for _, tc := range []struct {
		name  string
		blank func(*ACMEDNSCredentials)
	}{
		{"base url", func(c *ACMEDNSCredentials) { c.BaseURL = "" }},
		{"username", func(c *ACMEDNSCredentials) { c.Username = "" }},
		{"password", func(c *ACMEDNSCredentials) { c.Password = "" }},
		{"subdomain", func(c *ACMEDNSCredentials) { c.Subdomain = "" }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			a, argv, _, _ := newTestACME(t, 0, true)
			creds := testCreds()
			tc.blank(&creds)

			err := a.IssueCertDNS(context.Background(), "vdi.example.com", "chain.pem", creds)
			require.Error(t, err)
			assert.Nil(t, argv(), "the script must not run at all")
		})
	}
}

func TestCompleteReportsWhetherAllFourAreSet(t *testing.T) {
	assert.True(t, testCreds().Complete())
	assert.False(t, ACMEDNSCredentials{}.Complete())

	partial := testCreds()
	partial.Subdomain = ""
	assert.False(t, partial.Complete())
}

// ── The main domain ──────────────────────────────────────────────────────

func TestIssueMainDomainDNSPassesTheServer(t *testing.T) {
	a, argv, _, _ := newTestACME(t, 0, true)

	require.NoError(t, a.IssueMainDomainDNS(
		context.Background(), []string{"vdi.example.com"}, "chain.pem",
		ACMEAccount{Server: "letsencrypt_test"}, testCreds()))
	assert.Equal(t, []string{"vdi.example.com", "chain.pem", "letsencrypt_test"}, argv())
}

func TestIssueMainDomainDNSSendsThePasswordOnStdin(t *testing.T) {
	a, _, stdin, _ := newTestACME(t, 0, true)

	require.NoError(t, a.IssueMainDomainDNS(
		context.Background(), []string{"vdi.example.com"}, "chain.pem",
		ACMEAccount{}, testCreds()))
	assert.Equal(t, testPassword+"\n", stdin())
}

func TestIssueMainDomainDNSRefusesMoreThanOneName(t *testing.T) {
	// One acme.sh invocation uses one acme-dns account for every name on the
	// certificate, and an account holds a bounded number of TXT records, so a
	// multi-name certificate over DNS-01 needs a design this does not have.
	// Refused here as well as in the script, so the caller gets a message
	// about names rather than a non-zero exit code.
	a, argv, _, _ := newTestACME(t, 0, true)

	err := a.IssueMainDomainDNS(
		context.Background(), []string{"vdi.example.com", "extra.example.com"},
		"chain.pem", ACMEAccount{}, testCreds())
	require.Error(t, err)
	assert.Contains(t, err.Error(), "extra.example.com")
	assert.Nil(t, argv(), "the script must not run at all")
}

func TestIssueMainDomainDNSRefusesNoNames(t *testing.T) {
	a, _, _, _ := newTestACME(t, 0, true)

	err := a.IssueMainDomainDNS(
		context.Background(), nil, "chain.pem", ACMEAccount{}, testCreds())
	assert.Error(t, err)
}

// ── Cancellation ─────────────────────────────────────────────────────────

func TestIssueCertDNSHonoursACancelledContext(t *testing.T) {
	a, argv, _, _ := newTestACME(t, 0, true)

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	err := a.IssueCertDNS(ctx, "vdi.example.com", "chain.pem", testCreds())
	require.Error(t, err)
	assert.Nil(t, argv())
}
