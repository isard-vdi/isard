package provider

import (
	"context"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"

	"github.com/google/go-cmp/cmp"
	"github.com/rs/zerolog"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

// CfgWatcher is responsible for watching for changes in the authentication configuration
type CfgWatcher struct {
	log *zerolog.Logger

	ldapChanges   chan model.LDAPConfig
	samlChanges   chan model.SAMLConfig
	googleChanges chan model.GoogleConfig
}

func InitCfgWatcher(log *zerolog.Logger) *CfgWatcher {
	return &CfgWatcher{
		log: log,

		ldapChanges:   make(chan model.LDAPConfig, 1024),
		samlChanges:   make(chan model.SAMLConfig, 1024),
		googleChanges: make(chan model.GoogleConfig, 1024),
	}
}

func (c *CfgWatcher) Watch(ctx context.Context, wg *sync.WaitGroup, sess r.QueryExecutor) {
	cfg := &model.Config{}
	if err := cfg.Load(ctx, sess); err != nil {
		c.log.Error().Err(err).Msg("load authentication config")
		return
	}

	// Initial configuration load
	c.ldapChanges <- cfg.LDAP.LDAPConfig
	c.samlChanges <- cfg.SAML.SAMLConfig
	c.googleChanges <- cfg.Google.GoogleConfig

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
				notifyIfNeeded(c.ldapChanges, cfg.LDAP.LDAPConfig, newCfg.LDAP.LDAPConfig)
				notifyIfNeeded(c.samlChanges, cfg.SAML.SAMLConfig, newCfg.SAML.SAMLConfig)
				notifyIfNeeded(c.googleChanges, cfg.Google.GoogleConfig, newCfg.Google.GoogleConfig)

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

func notifyIfNeeded[T any](channel chan T, cfg T, newCfg T) {
	if !cmp.Equal(cfg, newCfg) {
		channel <- newCfg
	}
}

func (c *CfgWatcher) AddLDAPWatcher(ctx context.Context, wg *sync.WaitGroup, p ConfigurableProvider[model.LDAPConfig]) {
	wg.Add(1)
	go func() {
		for {
			select {
			case <-ctx.Done():
				wg.Done()
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

func (c *CfgWatcher) AddSAMLWatcher(ctx context.Context, wg *sync.WaitGroup, p ConfigurableProvider[model.SAMLConfig]) {
	wg.Add(1)
	go func() {
		for {
			select {
			case <-ctx.Done():
				wg.Done()
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

func (c *CfgWatcher) AddGoogleWatcher(ctx context.Context, wg *sync.WaitGroup, p ConfigurableProvider[model.GoogleConfig]) {
	wg.Add(1)
	go func() {
		for {
			select {
			case <-ctx.Done():
				wg.Done()
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

// cfgManager is responsible for accessing / loading a provider
// runtime configuration
type cfgManager[T any] struct {
	mux sync.RWMutex

	cfg *T
}

func (c *cfgManager[T]) Cfg() T {
	c.mux.RLock()
	defer c.mux.RUnlock()

	return *c.cfg
}

func (c *cfgManager[T]) LoadCfg(cfg T) {
	c.mux.Lock()
	defer c.mux.Unlock()

	c.cfg = &cfg
}
