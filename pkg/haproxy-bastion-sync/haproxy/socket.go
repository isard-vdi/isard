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

// Socket manages communication with HAProxy stats socket
type Socket struct {
	path string
	conn net.Conn
	mu   sync.Mutex
	log  *zerolog.Logger
}

// NewSocket creates a new HAProxy socket connection
func NewSocket(path string, log *zerolog.Logger) *Socket {
	return &Socket{
		path: path,
		log:  log,
	}
}

// Connect establishes connection to HAProxy socket
func (s *Socket) Connect() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.conn != nil {
		s.conn.Close()
	}

	conn, err := net.DialTimeout("unix", s.path, 5*time.Second)
	if err != nil {
		return fmt.Errorf("dial HAProxy socket: %w", err)
	}

	s.conn = conn
	s.log.Info().Str("socket", s.path).Msg("connected to HAProxy socket")
	return nil
}

// Close closes the socket connection
func (s *Socket) Close() error {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.conn != nil {
		return s.conn.Close()
	}
	return nil
}

// Execute sends a command to HAProxy and returns the response
func (s *Socket) Execute(command string) (string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if s.conn == nil {
		return "", fmt.Errorf("not connected to HAProxy socket")
	}

	// Set write deadline
	if err := s.conn.SetWriteDeadline(time.Now().Add(5 * time.Second)); err != nil {
		return "", fmt.Errorf("set write deadline: %w", err)
	}

	// Send command
	_, err := fmt.Fprintf(s.conn, "%s\n", command)
	if err != nil {
		// Try to reconnect on write error
		s.conn.Close()
		s.conn = nil
		return "", fmt.Errorf("write command: %w", err)
	}

	// Set read deadline
	if err := s.conn.SetReadDeadline(time.Now().Add(5 * time.Second)); err != nil {
		return "", fmt.Errorf("set read deadline: %w", err)
	}

	// Read response
	var response strings.Builder
	scanner := bufio.NewScanner(s.conn)
	for scanner.Scan() {
		line := scanner.Text()
		// HAProxy terminates responses with an empty line
		if line == "" {
			break
		}
		response.WriteString(line)
		response.WriteString("\n")
	}

	if err := scanner.Err(); err != nil {
		// Try to reconnect on read error
		s.conn.Close()
		s.conn = nil
		return "", fmt.Errorf("read response: %w", err)
	}

	return strings.TrimSpace(response.String()), nil
}

// ShowMap returns all entries in a map file
func (s *Socket) ShowMap(mapFile string) ([]string, error) {
	cmd := fmt.Sprintf("show map %s", mapFile)
	response, err := s.Execute(cmd)
	if err != nil {
		return nil, fmt.Errorf("show map %s: %w", mapFile, err)
	}

	if response == "" {
		return []string{}, nil
	}

	// Parse response - format is "0xADDRESS KEY"
	// We only care about the KEY part
	var entries []string
	for _, line := range strings.Split(response, "\n") {
		if line == "" {
			continue
		}
		// Split by whitespace and take the second part (the key)
		parts := strings.Fields(line)
		if len(parts) >= 2 {
			entries = append(entries, parts[1])
		}
	}

	return entries, nil
}

// AddMap adds an entry to a map file
// For subdomains.map and individual.map, we only need the key (domain name)
// HAProxy map syntax: add map <file> <key> [<value>]
// Since our maps don't have values, we use empty string
func (s *Socket) AddMap(mapFile, key string) error {
	// HAProxy requires at least an empty value
	cmd := fmt.Sprintf("add map %s %s", mapFile, key)
	_, err := s.Execute(cmd)
	if err != nil {
		return fmt.Errorf("add map %s %s: %w", mapFile, key, err)
	}

	s.log.Debug().
		Str("map", mapFile).
		Str("key", key).
		Msg("added map entry")

	return nil
}

// DelMap removes an entry from a map file
func (s *Socket) DelMap(mapFile, key string) error {
	cmd := fmt.Sprintf("del map %s %s", mapFile, key)
	_, err := s.Execute(cmd)
	if err != nil {
		return fmt.Errorf("del map %s %s: %w", mapFile, key, err)
	}

	s.log.Debug().
		Str("map", mapFile).
		Str("key", key).
		Msg("deleted map entry")

	return nil
}

// ClearMap removes all entries from a map file
func (s *Socket) ClearMap(mapFile string) error {
	cmd := fmt.Sprintf("clear map %s", mapFile)
	_, err := s.Execute(cmd)
	if err != nil {
		return fmt.Errorf("clear map %s: %w", mapFile, err)
	}

	s.log.Debug().
		Str("map", mapFile).
		Msg("cleared map")

	return nil
}

// IsConnected returns true if socket is connected
func (s *Socket) IsConnected() bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.conn != nil
}

// Reconnect attempts to reconnect to HAProxy socket
func (s *Socket) Reconnect() error {
	s.log.Warn().Msg("attempting to reconnect to HAProxy socket")
	return s.Connect()
}
