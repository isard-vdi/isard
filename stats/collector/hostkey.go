package collector

import (
	"errors"
	"net"
	"os"
	"sync"

	"github.com/rs/zerolog"
	"golang.org/x/crypto/ssh"
	"golang.org/x/crypto/ssh/knownhosts"
)

// NewSelfHealingHostKeyCallback returns an ssh.HostKeyCallback that verifies the
// hypervisor host key against known_hosts and RE-PINS it when it has rotated.
//
// The hypervisor regenerates ephemeral SSH host keys on every start
// (`ssh-keygen -A`) -- an intentional design. stats-go has always coped by
// re-scanning the key with `ssh-keyscan` at container startup (see
// stats/build/package/run.sh), i.e. trust-on-first-use on every (re)start. The
// in-process SSH reconnect pool (conn.go) re-dials with the start-time-pinned
// key, so it broke when the hypervisor rotated keys *during* a stats run
// ("knownhosts: key mismatch", leaving SSH collection dead until restart).
//
// This callback applies the SAME trust model to the reconnect path: a presented
// key that is unknown or rotated is recorded in known_hosts and accepted --
// exactly what the startup `ssh-keyscan` already does, so it adds no trust
// assumption beyond the established design. It fails CLOSED only if the new key
// cannot be persisted. (A stricter posture would mean persisting the hypervisor
// host keys, which contradicts the deliberate ephemeral-key design and provides
// no benefit on the internal, service-name-addressed SSH path.)
func NewSelfHealingHostKeyCallback(path string, log *zerolog.Logger) (ssh.HostKeyCallback, error) {
	base, err := knownhosts.New(path)
	if err != nil {
		return nil, err
	}
	var mu sync.Mutex
	return func(hostname string, remote net.Addr, key ssh.PublicKey) error {
		mu.Lock()
		defer mu.Unlock()

		verifyErr := base(hostname, remote, key)
		if verifyErr == nil {
			return nil
		}
		var keyErr *knownhosts.KeyError
		if !errors.As(verifyErr, &keyErr) {
			// Not a host-key verification failure (e.g. malformed file) -- surface it.
			return verifyErr
		}
		// keyErr.Want empty => unknown host (first contact); non-empty => the
		// host's key rotated. Re-pin in both cases, mirroring the startup
		// ssh-keyscan. Fail closed if the new key cannot be recorded so a
		// read-only HOME does not silently downgrade to "accept anything".
		if werr := appendKnownHost(path, hostname, key); werr != nil {
			log.Error().Err(werr).Str("host", hostname).Msg(
				"ssh host key rotated but known_hosts update failed; refusing connection")
			return verifyErr
		}
		log.Warn().Str("host", hostname).Int("prior_keys", len(keyErr.Want)).Msg(
			"ssh host key (re)pinned in known_hosts (rotation/first-contact)")
		if nb, nerr := knownhosts.New(path); nerr == nil {
			base = nb
		}
		return nil
	}, nil
}

// appendKnownHost appends a known_hosts line for hostname/key. SSH accepts a
// host that matches ANY known line, so appending the rotated key is enough to
// re-pin; a now-stale prior line is harmless and left in place.
func appendKnownHost(path, hostname string, key ssh.PublicKey) error {
	f, err := os.OpenFile(path, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o600)
	if err != nil {
		return err
	}
	defer f.Close()
	line := knownhosts.Line([]string{knownhosts.Normalize(hostname)}, key)
	_, err = f.WriteString(line + "\n")
	return err
}
