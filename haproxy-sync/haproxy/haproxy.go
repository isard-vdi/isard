package haproxy

import (
	"bufio"
	"fmt"
	"net"
	"strings"
	"sync"
	"time"

	"github.com/rs/zerolog"
)

const timeout = 5 * time.Second

type Interface interface {
	ShowVersion() (string, error)
	ShowMap(name string) ([]string, error)
	AddMap(name, key string) error
	DelMap(name, key string) error
	ClearMap(name string) error
}

var _ Interface = &HAProxy{}

type HAProxy struct {
	log *zerolog.Logger

	mux  sync.Mutex
	addr string
}

func NewHAProxy(log *zerolog.Logger, addr string) (*HAProxy, error) {
	h := &HAProxy{
		log:  log,
		addr: addr,
	}

	version, err := h.ShowVersion()
	if err != nil {
		return nil, fmt.Errorf("check the HAProxy version: %w", err)
	}

	*h.log = log.With().Str("haproxy_version", version).Logger()
	h.log.Info().Str("addr", addr).Msg("connected to the HAProxy admin socket")

	return h, nil
}

func (h *HAProxy) exec(command string) (string, error) {
	h.mux.Lock()
	defer h.mux.Unlock()

	sock, err := net.DialTimeout("unix", h.addr, timeout)
	if err != nil {
		return "", fmt.Errorf("connect to the HAProxy admin socket: %w", err)
	}
	defer sock.Close()

	if err = sock.SetWriteDeadline(time.Now().Add(timeout)); err != nil {
		return "", fmt.Errorf("set write timeout to HAProxy socket: %w", err)
	}

	if _, err := sock.Write([]byte(command + "\n")); err != nil {
		return "", fmt.Errorf("write command to HAProxy socket: %w", err)
	}

	if err := sock.SetReadDeadline(time.Now().Add(timeout)); err != nil {
		return "", fmt.Errorf("set read timeout to HAProxy socket: %w", err)
	}

	buf := bufio.NewReader(sock)
	b, err := buf.ReadBytes('\n')
	if err != nil {
		return "", fmt.Errorf("read the command respone from HAProxy socket: %w", err)
	}

	return strings.TrimSpace(string(b)), nil
}

// ShowVersion returns the HAProxy version
func (h *HAProxy) ShowVersion() (string, error) {
	// HAProxy reference: https://docs.haproxy.org/3.3/management.html#9.3-show%20version
	// show version
	//
	// Show the version of the current HAProxy process. This is available from
	// master and workers CLI.
	version, err := h.exec("show version")
	if err != nil {
		return "", fmt.Errorf("show version: %w", err)
	}

	h.log.Debug().
		Str("version", version).
		Msg("showed version")

	return version, nil
}

// ShowMap returns all entries in a map file
func (h *HAProxy) ShowMap(name string) ([]string, error) {
	// HAProxy reference: https://docs.haproxy.org/3.3/management.html#9.3-show%20map
	// show map [[@<ver>] <map>]
	//
	// Dump info about map converters. Without argument, the list of all available
	// maps is returned. If a <map> is specified, its contents are dumped. <map> is
	// the #<id> or <name>. By  default the current version of the map is shown (the
	// version currently being matched against and reported as 'curr_ver' in the map
	// list). It is possible to instead dump other versions by prepending '@<ver>'
	// before the map's identifier. The version works as a filter and non-existing
	// versions will simply report no result. The 'entry_cnt' value represents the
	// count of all the map entries, not just the active ones, which means that it
	// also includes entries currently being added.
	//
	// In the output, the first column is a unique entry identifier, which is usable
	// as a reference for operations "del map" and "set map". The second column is
	// the pattern and the third column is the sample if available. The data returned
	// are not directly a list of available maps, but are the list of all patterns
	// composing any map. Many of these patterns can be shared with ACL.
	raw, err := h.exec(fmt.Sprintf("show map %s", name))
	if err != nil {
		return nil, fmt.Errorf("show map '%s': %w", name, err)
	}

	// Parse response - format is "0xADDRESS KEY"
	// We only care about the KEY part
	entries := []string{}
	for _, line := range strings.Split(raw, "\n") {
		if line == "" {
			continue
		}

		parts := strings.Fields(line)
		if len(parts) >= 2 {
			entries = append(entries, parts[1])
		}
	}

	h.log.Debug().
		Str("map", name).
		Msg("showed map")

	return entries, nil
}

// AddMap adds an entry to a map file
func (h *HAProxy) AddMap(name, key string) error {
	// Since our maps don't have values, we use an underscore as value
	// HAProxy reference: https://docs.haproxy.org/3.3/management.html#9.3-add%20map
	// add map [@<ver>] <map> <key> <value>
	// add map [@<ver>] <map> <payload>
	//
	// Add an entry into the map <map> to associate the value <value> to the key
	// <key>. This command does not verify if the entry already exists. It is
	// mainly used to fill a map after a "clear" or "prepare" operation. Entries
	// are added to the current version of the ACL, unless a specific version is
	// specified with "@<ver>". This version number must have preliminary been
	// allocated by "prepare acl", and it will be comprised between the versions
	// reported in "curr_ver" and "next_ver" on the output of "show acl". Entries
	// added with a specific version number will not match until a "commit map"
	// operation is performed on them. They may however be consulted using the
	// "show map @<ver>" command, and cleared using a "clear acl @<ver>" command.
	// If the designated map is also used as an ACL, the ACL will only match the
	// <key> part and will ignore the <value> part. Using the payload syntax it is
	// possible to add multiple key/value pairs by entering them on separate lines.
	// On each new line, the first word is the key and the rest of the line is
	// considered to be the value which can even contains spaces.

	if _, err := h.exec(fmt.Sprintf("add map %s %s _", name, key)); err != nil {
		return fmt.Errorf("add '%s' key to '%s' map: %w", key, name, err)
	}

	h.log.Debug().
		Str("map", name).
		Str("key", key).
		Msg("addded map entry")

	return nil
}

func (h *HAProxy) DelMap(name, key string) error {
	// HAProxy reference: https://docs.haproxy.org/3.3/management.html#9.3-del%20map
	// del map <map> [<key>|#<ref>]
	//
	// Delete all the map entries from the map <map> corresponding to the key <key>.
	// <map> is the #<id> or the <name> returned by "show map". If the <ref> is used,
	// this command delete only the listed reference. The reference can be found with
	// listing the content of the map. Note that if the reference <map> is a name and
	// is shared with a acl, the entry will be also deleted in the map.
	if _, err := h.exec(fmt.Sprintf("del map %s %s", name, key)); err != nil {
		return fmt.Errorf("delete '%s' key from '%s' map: %w", key, name, err)
	}

	h.log.Debug().
		Str("map", name).
		Str("key", key).
		Msg("deleted map entry")

	return nil
}

func (h *HAProxy) ClearMap(name string) error {
	// HAProxy reference: https://docs.haproxy.org/3.3/management.html#9.3-clear%20map
	// clear map [@<ver>] <map>
	//
	// Remove all entries from the map <map>. <map> is the #<id> or the <name>
	// returned by "show map". Note that if the reference <map> is a name and is
	// shared with a acl, this acl will be also cleared. By default only the current
	// version of the map is cleared (the one being matched against). However it is
	// possible to specify another version using '@' followed by this version.
	if _, err := h.exec(fmt.Sprintf("clear map %s", name)); err != nil {
		return fmt.Errorf("clear map '%s': %w", name, err)
	}

	h.log.Debug().
		Str("map", name).
		Msg("cleared map")

	return nil
}
