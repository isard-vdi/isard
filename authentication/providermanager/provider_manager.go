package providermanager

import (
	"context"
	"slices"
	"sync"

	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"

	"github.com/crewjam/saml/samlsp"
	"github.com/rs/zerolog"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type Interface interface {
	Manage(ctx context.Context, wg *sync.WaitGroup)
	Providers(ctx context.Context, categoryID string) ([]string, error)
	Provider(p string) provider.Provider
	Healthcheck() error
	SAML() *samlsp.Middleware
}

var _ Interface = &ProviderManager{}

func InitProviderManager(cfg cfg.Authentication, log *zerolog.Logger, db r.QueryExecutor) *ProviderManager {
	cfgWatcher := InitCfgWatcher(log)

	m := &ProviderManager{
		log: log,
		cfg: cfg,
		db:  db,

		cfgWatcher:        cfgWatcher,
		cfgWatcherCancels: map[string]context.CancelFunc{},
		providers: map[string]provider.Provider{
			types.ProviderUnknown:  &provider.Unknown{},
			types.ProviderForm:     provider.InitForm(cfg, log, nil, nil),
			types.ProviderExternal: provider.InitExternal(db),
		},
	}

	return m
}

type ProviderManager struct {
	mux sync.RWMutex

	log *zerolog.Logger
	cfg cfg.Authentication
	db  r.QueryExecutor

	cfgWatcher        *CfgWatcher
	cfgWatcherCancels map[string]context.CancelFunc
	providers         map[string]provider.Provider
}

func (m *ProviderManager) Manage(ctx context.Context, wg *sync.WaitGroup) {
	// Start watching for configuration changes
	m.cfgWatcher.Watch(ctx, wg, m.db)

	wg.Add(1)
	go func() {
		defer wg.Done()

		for {
			select {
			case <-ctx.Done():
				return

			case change := <-m.cfgWatcher.providerChanges:
				m.handleProviderChange(ctx, wg, change)
			}
		}
	}()
}

func (m *ProviderManager) handleProviderChange(ctx context.Context, wg *sync.WaitGroup, change providerChange) {
	if change.Enabled {
		m.enableProvider(ctx, wg, change.Provider)

	} else {
		m.disableProvider(change.Provider)
	}
}

func (m *ProviderManager) disableProvider(prv string) {
	m.mux.Lock()
	defer m.mux.Unlock()

	if cancel, ok := m.cfgWatcherCancels[prv]; ok {
		cancel()
		delete(m.cfgWatcherCancels, prv)
	}

	switch prv {
	case types.ProviderLocal, types.ProviderLDAP:
		if f, ok := m.providers[types.ProviderForm].(*provider.Form); ok {
			f.DisableProvider(prv)
		}

		return
	}

	if _, ok := m.providers[prv]; !ok {
		m.log.Warn().Str("provider", prv).Msg("attempted to disable provider, but was nonexistent")
		return
	}

	delete(m.providers, prv)
	m.log.Info().Str("provider", prv).Msg("provider disabled")
}

func (m *ProviderManager) enableProvider(ctx context.Context, wg *sync.WaitGroup, prv string) {
	m.mux.Lock()
	defer m.mux.Unlock()

	if _, ok := m.providers[prv]; ok {
		m.log.Warn().Str("provider", prv).Msg("attempted to enable provider, but was already enabled")
		return
	}

	switch prv {
	case types.ProviderLocal:
		if f, ok := m.providers[types.ProviderForm].(*provider.Form); ok {
			if f.Provider(types.ProviderLocal) != nil {
				m.log.Warn().Str("provider", prv).Msg("attempted to enable provider, but was already enabled")
				return
			}

			f.EnableProvider(provider.InitLocal(m.db))
		}

	case types.ProviderLDAP:
		if f, ok := m.providers[types.ProviderForm].(*provider.Form); ok {
			if f.Provider(types.ProviderLDAP) != nil {
				m.log.Warn().Str("provider", prv).Msg("attempted to enable provider, but was already enabled")
				return
			}

			ldap := provider.InitLDAP(m.cfg.Secret, m.log, m.db)

			watcherCtx, cancel := context.WithCancel(ctx)
			m.cfgWatcherCancels[prv] = cancel
			m.cfgWatcher.AddLDAPWatcher(watcherCtx, wg, ldap)

			f.EnableProvider(ldap)
		}

	case types.ProviderSAML:
		saml := provider.InitSAML(m.cfg.Secret, m.cfg.Host, m.log, m.db)

		watcherCtx, cancel := context.WithCancel(ctx)
		m.cfgWatcherCancels[prv] = cancel
		m.cfgWatcher.AddSAMLWatcher(watcherCtx, wg, saml)

		m.providers[saml.String()] = saml

	case types.ProviderGoogle:
		google := provider.InitGoogle(m.cfg)

		watcherCtx, cancel := context.WithCancel(ctx)
		m.cfgWatcherCancels[prv] = cancel
		m.cfgWatcher.AddGoogleWatcher(watcherCtx, wg, google)

		m.providers[google.String()] = google

	default:
		m.log.Error().Str("provider", prv).Msg("attempted to enable provider, but we don't know it")
		return
	}

	m.log.Info().Str("provider", prv).Msg("provider enabled")
}

func (m *ProviderManager) Providers(ctx context.Context, categoryID string) ([]string, error) {
	m.mux.RLock()
	defer m.mux.RUnlock()

	providers := []string{}
	for k, v := range m.providers {
		if k == types.ProviderUnknown || k == types.ProviderExternal {
			continue
		}

		if k == types.ProviderForm {
			formPrvs := v.(*provider.Form).Providers()
			if len(formPrvs) == 0 {
				continue
			}

			providers = append(providers, formPrvs...)
		}

		providers = append(providers, k)
	}

	slices.Sort(providers)

	return providers, nil
}

func (m *ProviderManager) Provider(p string) provider.Provider {
	m.mux.RLock()
	defer m.mux.RUnlock()

	if prv := m.providers[p]; prv != nil {
		return prv
	}

	if f, ok := m.providers[types.ProviderForm].(*provider.Form); ok {
		if prv := f.Provider(p); prv != nil {
			return prv
		}
	}

	return m.providers[types.ProviderUnknown]
}

func (m *ProviderManager) Healthcheck() error {
	m.mux.RLock()
	defer m.mux.RUnlock()

	for _, p := range m.providers {
		if err := p.Healthcheck(); err != nil {
			m.log.Warn().Err(err).Str("provider", p.String()).Msg("service unhealthy")

			return err
		}
	}

	return nil
}

func (m *ProviderManager) SAML() *samlsp.Middleware {
	s, ok := m.Provider(types.ProviderSAML).(*provider.SAML)
	if !ok {
		return nil
	}

	return s.Middleware()
}
