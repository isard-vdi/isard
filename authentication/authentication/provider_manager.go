package authentication

import (
	"context"
	"sync"

	"github.com/crewjam/saml/samlsp"
	"github.com/rs/zerolog"
	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

func InitProviderManager(ctx context.Context, wg *sync.WaitGroup, cfg cfg.Authentication, log *zerolog.Logger, db r.QueryExecutor) *ProviderManager {
	cfgWatcher := provider.InitCfgWatcher(log)

	var local *provider.Local
	if cfg.Local.Enabled {
		local = provider.InitLocal(db)
	}

	var ldap *provider.LDAP
	if cfg.LDAP.Enabled {
		ldap = provider.InitLDAP(cfg.Secret, log, db)
		cfgWatcher.AddLDAPWatcher(ctx, wg, ldap)
	}

	m := &ProviderManager{
		log:        log,
		cfgWatcher: cfgWatcher,
		providers: map[string]provider.Provider{
			types.ProviderUnknown:  &provider.Unknown{},
			types.ProviderForm:     provider.InitForm(cfg, local, ldap),
			types.ProviderExternal: &provider.External{},
		},
	}

	if cfg.SAML.Enabled {
		saml := provider.InitSAML(cfg.Secret, cfg.Host, log, db)
		m.cfgWatcher.AddSAMLWatcher(ctx, wg, saml)

		m.providers[saml.String()] = saml
	}

	if cfg.Google.Enabled {
		google := provider.InitGoogle(cfg)
		m.cfgWatcher.AddGoogleWatcher(ctx, wg, google)

		m.providers[google.String()] = google
	}

	cfgWatcher.Watch(ctx, wg, db)

	return m
}

type ProviderManager struct {
	log *zerolog.Logger

	cfgWatcher *provider.CfgWatcher
	providers  map[string]provider.Provider
}

func (m *ProviderManager) Providers() []string {
	providers := []string{}
	for k, v := range m.providers {
		if k == types.ProviderUnknown || k == types.ProviderExternal {
			continue
		}

		if k == types.ProviderForm {
			providers = append(providers, v.(*provider.Form).Providers()...)
		}

		providers = append(providers, k)
	}

	return providers
}

func (m *ProviderManager) Provider(p string) provider.Provider {
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
