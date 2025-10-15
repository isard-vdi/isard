package haproxy

import (
	"fmt"

	"github.com/rs/zerolog"
)

// Syncer handles synchronization between map files and HAProxy runtime
type Syncer struct {
	socket         *Socket
	store          *MapStore
	log            *zerolog.Logger
	subdomPath     string
	individualPath string
}

// NewSyncer creates a new syncer
func NewSyncer(socket *Socket, store *MapStore, subdomPath, individualPath string, log *zerolog.Logger) *Syncer {
	return &Syncer{
		socket:         socket,
		store:          store,
		log:            log,
		subdomPath:     subdomPath,
		individualPath: individualPath,
	}
}

// SyncResult contains synchronization statistics
type SyncResult struct {
	SubdomainsAdded   int32
	SubdomainsRemoved int32
	IndividualAdded   int32
	IndividualRemoved int32
}

// SyncSubdomains synchronizes subdomain map with desired state
func (s *Syncer) SyncSubdomains(desiredDomains []string) (*SyncResult, error) {
	result := &SyncResult{}

	// Get current state from HAProxy
	currentDomains, err := s.socket.ShowMap(s.subdomPath)
	if err != nil {
		return nil, fmt.Errorf("show map: %w", err)
	}

	// Convert to maps for efficient lookup
	current := make(map[string]bool)
	for _, domain := range currentDomains {
		current[domain] = true
	}

	desired := make(map[string]bool)
	for _, domain := range desiredDomains {
		if domain != "" {
			desired[domain] = true
		}
	}

	// Find domains to add (in desired but not in current)
	for domain := range desired {
		if !current[domain] {
			if err := s.socket.AddMap(s.subdomPath, domain); err != nil {
				s.log.Error().
					Err(err).
					Str("domain", domain).
					Msg("failed to add subdomain")
				continue
			}
			s.store.AddSubdomain(domain)
			result.SubdomainsAdded++
		}
	}

	// Find domains to remove (in current but not in desired)
	for domain := range current {
		if !desired[domain] {
			if err := s.socket.DelMap(s.subdomPath, domain); err != nil {
				s.log.Error().
					Err(err).
					Str("domain", domain).
					Msg("failed to delete subdomain")
				continue
			}
			s.store.DelSubdomain(domain)
			result.SubdomainsRemoved++
		}
	}

	s.log.Info().
		Int32("added", result.SubdomainsAdded).
		Int32("removed", result.SubdomainsRemoved).
		Msg("synced subdomains")

	return result, nil
}

// SyncIndividual synchronizes individual domain map with desired state
func (s *Syncer) SyncIndividual(desiredDomains []string) (*SyncResult, error) {
	result := &SyncResult{}

	// Get current state from HAProxy
	currentDomains, err := s.socket.ShowMap(s.individualPath)
	if err != nil {
		return nil, fmt.Errorf("show map: %w", err)
	}

	// Convert to maps for efficient lookup
	current := make(map[string]bool)
	for _, domain := range currentDomains {
		current[domain] = true
	}

	desired := make(map[string]bool)
	for _, domain := range desiredDomains {
		if domain != "" {
			desired[domain] = true
		}
	}

	// Find domains to add (in desired but not in current)
	for domain := range desired {
		if !current[domain] {
			if err := s.socket.AddMap(s.individualPath, domain); err != nil {
				s.log.Error().
					Err(err).
					Str("domain", domain).
					Msg("failed to add individual domain")
				continue
			}
			s.store.AddIndividual(domain)
			result.IndividualAdded++
		}
	}

	// Find domains to remove (in current but not in desired)
	for domain := range current {
		if !desired[domain] {
			if err := s.socket.DelMap(s.individualPath, domain); err != nil {
				s.log.Error().
					Err(err).
					Str("domain", domain).
					Msg("failed to delete individual domain")
				continue
			}
			s.store.DelIndividual(domain)
			result.IndividualRemoved++
		}
	}

	s.log.Info().
		Int32("added", result.IndividualAdded).
		Int32("removed", result.IndividualRemoved).
		Msg("synced individual domains")

	return result, nil
}

// SyncAll synchronizes both maps with desired state
func (s *Syncer) SyncAll(desiredSubdomains, desiredIndividual []string) (*SyncResult, error) {
	result := &SyncResult{}

	// Sync subdomains
	subResult, err := s.SyncSubdomains(desiredSubdomains)
	if err != nil {
		return nil, fmt.Errorf("sync subdomains: %w", err)
	}
	result.SubdomainsAdded = subResult.SubdomainsAdded
	result.SubdomainsRemoved = subResult.SubdomainsRemoved

	// Sync individual domains
	indResult, err := s.SyncIndividual(desiredIndividual)
	if err != nil {
		return nil, fmt.Errorf("sync individual: %w", err)
	}
	result.IndividualAdded = indResult.IndividualAdded
	result.IndividualRemoved = indResult.IndividualRemoved

	// Update memory store
	s.store.SetSubdomains(desiredSubdomains)
	s.store.SetIndividual(desiredIndividual)

	s.log.Info().
		Int32("subdomains_added", result.SubdomainsAdded).
		Int32("subdomains_removed", result.SubdomainsRemoved).
		Int32("individual_added", result.IndividualAdded).
		Int32("individual_removed", result.IndividualRemoved).
		Msg("full sync completed")

	return result, nil
}

// AddSubdomain adds a single subdomain
func (s *Syncer) AddSubdomain(domain string) error {
	if domain == "" {
		return fmt.Errorf("domain cannot be empty")
	}

	// Check if already exists
	if s.store.HasSubdomain(domain) {
		s.log.Debug().Str("domain", domain).Msg("subdomain already exists")
		return nil
	}

	// Add to HAProxy
	if err := s.socket.AddMap(s.subdomPath, domain); err != nil {
		return fmt.Errorf("add to HAProxy: %w", err)
	}

	// Update memory
	s.store.AddSubdomain(domain)

	s.log.Info().Str("domain", domain).Msg("added subdomain")
	return nil
}

// DeleteSubdomain removes a single subdomain
func (s *Syncer) DeleteSubdomain(domain string) error {
	if domain == "" {
		return fmt.Errorf("domain cannot be empty")
	}

	// Check if exists
	if !s.store.HasSubdomain(domain) {
		s.log.Debug().Str("domain", domain).Msg("subdomain doesn't exist")
		return nil
	}

	// Remove from HAProxy
	if err := s.socket.DelMap(s.subdomPath, domain); err != nil {
		return fmt.Errorf("delete from HAProxy: %w", err)
	}

	// Update memory
	s.store.DelSubdomain(domain)

	s.log.Info().Str("domain", domain).Msg("deleted subdomain")
	return nil
}

// AddIndividualDomain adds a single individual domain
func (s *Syncer) AddIndividualDomain(domain string) error {
	if domain == "" {
		return fmt.Errorf("domain cannot be empty")
	}

	// Check if already exists
	if s.store.HasIndividual(domain) {
		s.log.Debug().Str("domain", domain).Msg("individual domain already exists")
		return nil
	}

	// Add to HAProxy
	if err := s.socket.AddMap(s.individualPath, domain); err != nil {
		return fmt.Errorf("add to HAProxy: %w", err)
	}

	// Update memory
	s.store.AddIndividual(domain)

	s.log.Info().Str("domain", domain).Msg("added individual domain")
	return nil
}

// DeleteIndividualDomain removes a single individual domain
func (s *Syncer) DeleteIndividualDomain(domain string) error {
	if domain == "" {
		return fmt.Errorf("domain cannot be empty")
	}

	// Check if exists
	if !s.store.HasIndividual(domain) {
		s.log.Debug().Str("domain", domain).Msg("individual domain doesn't exist")
		return nil
	}

	// Remove from HAProxy
	if err := s.socket.DelMap(s.individualPath, domain); err != nil {
		return fmt.Errorf("delete from HAProxy: %w", err)
	}

	// Update memory
	s.store.DelIndividual(domain)

	s.log.Info().Str("domain", domain).Msg("deleted individual domain")
	return nil
}
