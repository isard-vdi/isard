package providermanager

import (
	"context"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"

	"github.com/google/go-cmp/cmp"
	"github.com/rs/zerolog"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

// CfgWatcher is responsible for watching for changes in the authentication configuration
type CfgWatcher struct {
	log *zerolog.Logger

	providerChanges chan providerChange

	ldapChanges   chan model.LDAPConfig
	samlChanges   chan model.SAMLConfig
	googleChanges chan model.GoogleConfig
}

type providerChange struct {
	Provider string
	Enabled  bool
}

func InitCfgWatcher(log *zerolog.Logger) *CfgWatcher {
	return &CfgWatcher{
		log: log,

		providerChanges: make(chan providerChange, 1024),

		ldapChanges:   make(chan model.LDAPConfig, 1024),
		samlChanges:   make(chan model.SAMLConfig, 1024),
		googleChanges: make(chan model.GoogleConfig, 1024),
	}
}

func (c *CfgWatcher) Watch(ctx context.Context, wg *sync.WaitGroup, sess r.QueryExecutor) {
	cfg := &model.Config{}
	if err := cfg.Load(ctx, sess); err != nil {
		c.log.Fatal().Err(err).Msg("load initial authentication configuration")
	}

	// Initial providers setup
	if cfg.Local.Enabled {
		c.providerChanges <- providerChange{Provider: types.ProviderLocal, Enabled: true}
	}

	if cfg.LDAP.Enabled {
		c.providerChanges <- providerChange{Provider: types.ProviderLDAP, Enabled: true}
		c.ldapChanges <- cfg.LDAP.LDAPConfig
	}

	if cfg.SAML.Enabled {
		c.providerChanges <- providerChange{Provider: types.ProviderSAML, Enabled: true}
		c.samlChanges <- cfg.SAML.SAMLConfig
	}

	if cfg.Google.Enabled {
		c.providerChanges <- providerChange{Provider: types.ProviderGoogle, Enabled: true}
		c.googleChanges <- cfg.Google.GoogleConfig
	}

	wg.Add(1)
	go func() {
		defer wg.Done()

		ticker := time.NewTicker(1 * time.Minute)
		defer ticker.Stop()

		for {
			newCfg := &model.Config{}
			if err := newCfg.Load(ctx, sess); err != nil {
				c.log.Error().Err(err).Msg("reload authentication config")

			} else {
				notifyProviderChangeIfNeeded(c.providerChanges, types.ProviderLocal, cfg.Local.Enabled, newCfg.Local.Enabled)
				notifyProviderChangeIfNeeded(c.providerChanges, types.ProviderLDAP, cfg.LDAP.Enabled, newCfg.LDAP.Enabled)
				notifyProviderChangeIfNeeded(c.providerChanges, types.ProviderSAML, cfg.SAML.Enabled, newCfg.SAML.Enabled)
				notifyProviderChangeIfNeeded(c.providerChanges, types.ProviderGoogle, cfg.Google.Enabled, newCfg.Google.Enabled)

				if newCfg.LDAP.Enabled {
					notifyIfNeeded(c.ldapChanges, cfg.LDAP.LDAPConfig, newCfg.LDAP.LDAPConfig)
				}
				if newCfg.SAML.Enabled {
					notifyIfNeeded(c.samlChanges, cfg.SAML.SAMLConfig, newCfg.SAML.SAMLConfig)
				}
				if newCfg.Google.Enabled {
					notifyIfNeeded(c.googleChanges, cfg.Google.GoogleConfig, newCfg.Google.GoogleConfig)
				}

				cfg = newCfg
			}

			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
			}
		}
	}()
}

func notifyProviderChangeIfNeeded(channel chan providerChange, prv string, enabled, newEnabled bool) {
	if enabled != newEnabled {
		channel <- providerChange{
			Provider: prv,
			Enabled:  newEnabled,
		}
	}
}

func notifyIfNeeded[T any](channel chan T, cfg T, newCfg T) {
	if !cmp.Equal(cfg, newCfg) {
		channel <- newCfg
	}
}

func (c *CfgWatcher) AddLDAPWatcher(ctx context.Context, wg *sync.WaitGroup, p provider.ConfigurableProvider[model.LDAPConfig]) {
	wg.Add(1)
	go func() {
		defer wg.Done()

		for {
			select {
			case <-ctx.Done():
				return

			case cfg := <-c.ldapChanges:
				c.log.Debug().Msg("reloading LDAP configuration")
				if err := p.LoadConfig(ctx, cfg); err != nil {
					c.log.Error().Err(err).Msg("load new LDAP configuration")
				} else {
					c.log.Info().Msg("successfully reloaded LDAP configuration")
				}
			}
		}
	}()
}

func (c *CfgWatcher) AddSAMLWatcher(ctx context.Context, wg *sync.WaitGroup, p provider.ConfigurableProvider[model.SAMLConfig]) {
	wg.Add(1)
	go func() {
		defer wg.Done()

		for {
			select {
			case <-ctx.Done():
				return

			case cfg := <-c.samlChanges:
				c.log.Debug().Msg("reloading SAML configuration")
				if err := p.LoadConfig(ctx, cfg); err != nil {
					c.log.Error().Err(err).Msg("load new SAML configuration")
				} else {
					c.log.Info().Msg("successfully reloaded SAML configuration")
				}
			}
		}
	}()
}

func (c *CfgWatcher) AddGoogleWatcher(ctx context.Context, wg *sync.WaitGroup, p provider.ConfigurableProvider[model.GoogleConfig]) {
	wg.Add(1)
	go func() {
		defer wg.Done()

		for {
			select {
			case <-ctx.Done():
				return

			case cfg := <-c.googleChanges:
				c.log.Debug().Msg("reloading Google configuration")
				if err := p.LoadConfig(ctx, cfg); err != nil {
					c.log.Error().Err(err).Msg("load new Google configuration")
				} else {
					c.log.Info().Msg("successfully reloaded Google configuration")
				}
			}
		}
	}()
}
