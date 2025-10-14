package haproxy

import (
	"bufio"
	"fmt"
	"os"
	"strings"
	"sync"

	"github.com/rs/zerolog"
)

// MapStore manages in-memory storage of HAProxy map files
type MapStore struct {
	subdomains     map[string]bool
	individual     map[string]bool
	mu             sync.RWMutex
	log            *zerolog.Logger
	subdomPath     string
	individualPath string
}

// NewMapStore creates a new map store
func NewMapStore(subdomainsPath, individualPath string, log *zerolog.Logger) *MapStore {
	return &MapStore{
		subdomains:     make(map[string]bool),
		individual:     make(map[string]bool),
		log:            log,
		subdomPath:     subdomainsPath,
		individualPath: individualPath,
	}
}

// LoadFromFiles loads map files into memory
func (m *MapStore) LoadFromFiles() error {
	m.mu.Lock()
	defer m.mu.Unlock()

	// Load subdomains
	subdomains, err := readMapFile(m.subdomPath)
	if err != nil {
		return fmt.Errorf("load subdomains map: %w", err)
	}
	m.subdomains = make(map[string]bool)
	for _, domain := range subdomains {
		m.subdomains[domain] = true
	}
	m.log.Info().
		Int("count", len(subdomains)).
		Str("file", m.subdomPath).
		Msg("loaded subdomains from file")

	// Load individual domains
	individual, err := readMapFile(m.individualPath)
	if err != nil {
		return fmt.Errorf("load individual map: %w", err)
	}
	m.individual = make(map[string]bool)
	for _, domain := range individual {
		m.individual[domain] = true
	}
	m.log.Info().
		Int("count", len(individual)).
		Str("file", m.individualPath).
		Msg("loaded individual domains from file")

	return nil
}

// readMapFile reads a map file and returns domain list
func readMapFile(path string) ([]string, error) {
	file, err := os.Open(path)
	if err != nil {
		// If file doesn't exist, create it
		if os.IsNotExist(err) {
			if err := os.MkdirAll(strings.TrimSuffix(path, "/"+strings.Split(path, "/")[len(strings.Split(path, "/"))-1]), 0755); err != nil {
				return nil, fmt.Errorf("create directory: %w", err)
			}
			f, err := os.Create(path)
			if err != nil {
				return nil, fmt.Errorf("create file: %w", err)
			}
			f.Close()
			return []string{}, nil
		}
		return nil, fmt.Errorf("open file: %w", err)
	}
	defer file.Close()

	var domains []string
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		// Skip empty lines and comments
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		domains = append(domains, line)
	}

	if err := scanner.Err(); err != nil {
		return nil, fmt.Errorf("scan file: %w", err)
	}

	return domains, nil
}

// GetSubdomains returns a copy of subdomain list
func (m *MapStore) GetSubdomains() []string {
	m.mu.RLock()
	defer m.mu.RUnlock()

	domains := make([]string, 0, len(m.subdomains))
	for domain := range m.subdomains {
		domains = append(domains, domain)
	}
	return domains
}

// GetIndividual returns a copy of individual domain list
func (m *MapStore) GetIndividual() []string {
	m.mu.RLock()
	defer m.mu.RUnlock()

	domains := make([]string, 0, len(m.individual))
	for domain := range m.individual {
		domains = append(domains, domain)
	}
	return domains
}

// AddSubdomain adds a subdomain to memory
func (m *MapStore) AddSubdomain(domain string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.subdomains[domain] = true
}

// DelSubdomain removes a subdomain from memory
func (m *MapStore) DelSubdomain(domain string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.subdomains, domain)
}

// AddIndividual adds an individual domain to memory
func (m *MapStore) AddIndividual(domain string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.individual[domain] = true
}

// DelIndividual removes an individual domain from memory
func (m *MapStore) DelIndividual(domain string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	delete(m.individual, domain)
}

// SetSubdomains replaces all subdomains
func (m *MapStore) SetSubdomains(domains []string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.subdomains = make(map[string]bool)
	for _, domain := range domains {
		if domain != "" {
			m.subdomains[domain] = true
		}
	}
}

// SetIndividual replaces all individual domains
func (m *MapStore) SetIndividual(domains []string) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.individual = make(map[string]bool)
	for _, domain := range domains {
		if domain != "" {
			m.individual[domain] = true
		}
	}
}

// HasSubdomain checks if subdomain exists
func (m *MapStore) HasSubdomain(domain string) bool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.subdomains[domain]
}

// HasIndividual checks if individual domain exists
func (m *MapStore) HasIndividual(domain string) bool {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.individual[domain]
}

// SubdomainsCount returns number of subdomains
func (m *MapStore) SubdomainsCount() int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return len(m.subdomains)
}

// IndividualCount returns number of individual domains
func (m *MapStore) IndividualCount() int {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return len(m.individual)
}
