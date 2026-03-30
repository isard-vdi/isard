package providermanager

import (
	"context"
	"maps"
	"slices"
	"sync"
	"time"

	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"

	"github.com/google/go-cmp/cmp"
	"github.com/rs/zerolog"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

// cfgWatcher is responsible for watching for changes in the authentication configuration.
type cfgWatcher struct {
	log *zerolog.Logger

	reloadInterval time.Duration

	providerChanges                    chan providerChange
	categoriesDisabledProvidersChanges chan categoryDisabledProviderChange
	categoriesBrandingDomainChanges    chan categoryBrandingDomainChange

	globalChanges     *providerChangesChannels
	categoriesMux     sync.RWMutex
	categoriesChanges map[string]*providerChangesChannels
}

type providerChange struct {
	CategoryID *string
	Provider   string
	Enabled    bool
}

type categoryDisabledProviderChange struct {
	CategoryID string
	Provider   string
	Disabled   bool
}

type categoryBrandingDomainChange struct {
	CategoryID     string
	Host           *string
	Authentication *model.CategoryAuthentication
	retries        int
}

type providerChangesChannels struct {
	ldapChanges   chan model.LDAPConfig
	samlChanges   chan model.SAMLConfig
	googleChanges chan model.GoogleConfig
}

func initCfgWatcher(log *zerolog.Logger) *cfgWatcher {
	return &cfgWatcher{
		log: log,

		reloadInterval: 1 * time.Minute,

		providerChanges:                    make(chan providerChange, 1024),
		categoriesDisabledProvidersChanges: make(chan categoryDisabledProviderChange, 1024),
		categoriesBrandingDomainChanges:    make(chan categoryBrandingDomainChange, 1024),

		globalChanges: &providerChangesChannels{
			ldapChanges:   make(chan model.LDAPConfig, 1024),
			samlChanges:   make(chan model.SAMLConfig, 1024),
			googleChanges: make(chan model.GoogleConfig, 1024),
		},

		categoriesChanges: map[string]*providerChangesChannels{},
	}
}

func extractBrandingHost(entry model.CategoryConfigEntry) *string {
	if !entry.Branding.Domain.Enabled {
		return nil
	}

	return &entry.Branding.Domain.Name
}

func (c *cfgWatcher) Watch(ctx context.Context, wg *sync.WaitGroup, sess r.QueryExecutor) {
	c.log.Debug().Dur("reload_interval", c.reloadInterval).Msg("starting configuration watcher")

	c.watchGlobal(ctx, wg, sess)
	c.watchCategories(ctx, wg, sess)
}

func (c *cfgWatcher) watchGlobal(ctx context.Context, wg *sync.WaitGroup, sess r.QueryExecutor) {
	cfg := &model.Config{}
	if err := cfg.Load(ctx, sess); err != nil {
		c.log.Fatal().Err(err).Msg("load initial global authentication configuration")
	}

	c.log.Debug().Msg("loaded initial global authentication configuration")

	// Initial global providers setup.
	if cfg.Local.Enabled {
		c.log.Debug().Str("provider", types.ProviderLocal).Msg("scheduling initial global provider enable")
		c.providerChanges <- providerChange{Provider: types.ProviderLocal, Enabled: true}
	}

	if cfg.LDAP.Enabled {
		c.log.Debug().Str("provider", types.ProviderLDAP).Msg("scheduling initial global provider enable")
		c.providerChanges <- providerChange{Provider: types.ProviderLDAP, Enabled: true}
		c.globalChanges.ldapChanges <- cfg.LDAP.LDAPConfig
	}

	if cfg.SAML.Enabled {
		c.log.Debug().Str("provider", types.ProviderSAML).Msg("scheduling initial global provider enable")
		c.providerChanges <- providerChange{Provider: types.ProviderSAML, Enabled: true}
		c.globalChanges.samlChanges <- cfg.SAML.SAMLConfig
	}

	if cfg.Google.Enabled {
		c.log.Debug().Str("provider", types.ProviderGoogle).Msg("scheduling initial global provider enable")
		c.providerChanges <- providerChange{Provider: types.ProviderGoogle, Enabled: true}
		c.globalChanges.googleChanges <- cfg.Google.GoogleConfig
	}

	wg.Go(func() {
		ticker := time.NewTicker(c.reloadInterval)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
			}

			newCfg := &model.Config{}
			if err := newCfg.Load(ctx, sess); err != nil {
				c.log.Error().Err(err).Msg("reload authentication config")
				continue
			}

			c.log.Debug().Msg("reloading global authentication configuration")

			notifyProviderChangeIfNeeded(c.log, c.providerChanges, nil, types.ProviderLocal, cfg.Local.Enabled, newCfg.Local.Enabled)
			notifyProviderChangeIfNeeded(c.log, c.providerChanges, nil, types.ProviderLDAP, cfg.LDAP.Enabled, newCfg.LDAP.Enabled)
			notifyProviderChangeIfNeeded(c.log, c.providerChanges, nil, types.ProviderSAML, cfg.SAML.Enabled, newCfg.SAML.Enabled)
			notifyProviderChangeIfNeeded(c.log, c.providerChanges, nil, types.ProviderGoogle, cfg.Google.Enabled, newCfg.Google.Enabled)

			if newCfg.LDAP.Enabled {
				notifyIfNeeded(c.globalChanges.ldapChanges, cfg.LDAP.LDAPConfig, newCfg.LDAP.LDAPConfig)
			}
			if newCfg.SAML.Enabled {
				notifyIfNeeded(c.globalChanges.samlChanges, cfg.SAML.SAMLConfig, newCfg.SAML.SAMLConfig)
			}
			if newCfg.Google.Enabled {
				notifyIfNeeded(c.globalChanges.googleChanges, cfg.Google.GoogleConfig, newCfg.Google.GoogleConfig)
			}

			cfg = newCfg
		}
	})
}

func (c *cfgWatcher) watchCategories(ctx context.Context, wg *sync.WaitGroup, sess r.QueryExecutor) {
	cfgCategories, err := model.CategoryConfigurationsLoad(ctx, sess)
	if err != nil {
		c.log.Fatal().Err(err).Msg("load initial categories authentication configuration")
	}

	c.log.Debug().Strs("categories", slices.Sorted(maps.Keys(cfgCategories))).Msg("loaded initial categories authentication configuration")

	for categoryID, entry := range cfgCategories {
		cfg := entry.Authentication
		changesChans := c.getOrCreateCategoryChangesChannels(categoryID)

		hasProviders := false

		// Initial category providers setup.
		if cfg.Local != nil {
			if cfg.Local.Disabled {
				c.categoriesDisabledProvidersChanges <- categoryDisabledProviderChange{
					CategoryID: categoryID,
					Provider:   types.ProviderLocal,
					Disabled:   true,
				}
			} else {
				hasProviders = true

				c.providerChanges <- providerChange{
					CategoryID: &categoryID,
					Provider:   types.ProviderLocal,
					Enabled:    true,
				}
			}
		}

		if cfg.LDAP != nil {
			if cfg.LDAP.Disabled {
				c.categoriesDisabledProvidersChanges <- categoryDisabledProviderChange{
					CategoryID: categoryID,
					Provider:   types.ProviderLDAP,
					Disabled:   true,
				}
			} else if cfg.LDAP.ConfigSource == model.CategoryAuthenticationConfigSourceCustom && cfg.LDAP.LDAPConfig != nil {
				hasProviders = true

				c.providerChanges <- providerChange{
					CategoryID: &categoryID,
					Provider:   types.ProviderLDAP,
					Enabled:    true,
				}
				changesChans.ldapChanges <- *cfg.LDAP.LDAPConfig
			}
		}

		if cfg.SAML != nil {
			if cfg.SAML.Disabled {
				c.categoriesDisabledProvidersChanges <- categoryDisabledProviderChange{
					CategoryID: categoryID,
					Provider:   types.ProviderSAML,
					Disabled:   true,
				}
			} else if cfg.SAML.ConfigSource == model.CategoryAuthenticationConfigSourceCustom && cfg.SAML.SAMLConfig != nil {
				hasProviders = true

				c.providerChanges <- providerChange{
					CategoryID: &categoryID,
					Provider:   types.ProviderSAML,
					Enabled:    true,
				}
				changesChans.samlChanges <- *cfg.SAML.SAMLConfig
			}
		}

		if cfg.Google != nil {
			if cfg.Google.Disabled {
				c.categoriesDisabledProvidersChanges <- categoryDisabledProviderChange{
					CategoryID: categoryID,
					Provider:   types.ProviderGoogle,
					Disabled:   true,
				}
			} else if cfg.Google.ConfigSource == model.CategoryAuthenticationConfigSourceCustom && cfg.Google.GoogleConfig != nil {
				hasProviders = true

				c.providerChanges <- providerChange{
					CategoryID: &categoryID,
					Provider:   types.ProviderGoogle,
					Enabled:    true,
				}
				changesChans.googleChanges <- *cfg.Google.GoogleConfig
			}
		}

		// If the category has providers, add it to the map.
		if hasProviders {
			c.categoriesMux.Lock()
			c.categoriesChanges[categoryID] = changesChans
			c.categoriesMux.Unlock()
		}

		// Send initial branding host state after provider changes,
		// so the provider exists when SetBrandingHost is called.
		if brandingHost := extractBrandingHost(entry); brandingHost != nil {
			c.categoriesBrandingDomainChanges <- categoryBrandingDomainChange{
				CategoryID:     categoryID,
				Host:           brandingHost,
				Authentication: &cfg,
			}
		}
	}

	wg.Go(func() {
		ticker := time.NewTicker(c.reloadInterval)
		defer ticker.Stop()

		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
			}

			newCfgCategories, err := model.CategoryConfigurationsLoad(ctx, sess)
			if err != nil {
				c.log.Error().Err(err).Msg("reload categories authentication config")
				continue
			}

			c.log.Debug().Strs("categories", slices.Sorted(maps.Keys(newCfgCategories))).Msg("reloading categories authentication configuration")

			for categoryID, newEntry := range newCfgCategories {
				entry := cfgCategories[categoryID]

				cfg := entry.Authentication
				newCfg := newEntry.Authentication

				notifyBrandingDomainChangeIfNeeded(c.categoriesBrandingDomainChanges, categoryID, extractBrandingHost(entry), extractBrandingHost(newEntry), &newCfg)

				changesChans := c.getOrCreateCategoryChangesChannels(categoryID)

				hasProviders := false

				cfgLocalExists := cfg.Local != nil
				newCfgLocalExists := newCfg.Local != nil

				cfgLocalEnabled := cfgLocalExists && !cfg.Local.Disabled
				newCfgLocalEnabled := newCfgLocalExists && !newCfg.Local.Disabled
				notifyProviderChangeIfNeeded(c.log, c.providerChanges, &categoryID, types.ProviderLocal, cfgLocalEnabled, newCfgLocalEnabled)

				cfgLocalDisabled := cfgLocalExists && cfg.Local.Disabled
				newCfgLocalDisabled := newCfgLocalExists && newCfg.Local.Disabled
				notifyDisabledProviderChangeIfNeeded(c.log, c.categoriesDisabledProvidersChanges, categoryID, types.ProviderLocal, cfgLocalDisabled, newCfgLocalDisabled)

				cfgLDAPExists := cfg.LDAP != nil
				newCfgLDAPExists := newCfg.LDAP != nil

				cfgLDAPEnabled := cfgLDAPExists && !cfg.LDAP.Disabled && cfg.LDAP.ConfigSource == model.CategoryAuthenticationConfigSourceCustom && cfg.LDAP.LDAPConfig != nil
				newCfgLDAPEnabled := newCfgLDAPExists && !newCfg.LDAP.Disabled && newCfg.LDAP.ConfigSource == model.CategoryAuthenticationConfigSourceCustom && newCfg.LDAP.LDAPConfig != nil
				notifyProviderChangeIfNeeded(c.log, c.providerChanges, &categoryID, types.ProviderLDAP, cfgLDAPEnabled, newCfgLDAPEnabled)

				cfgLDAPDisabled := cfgLDAPExists && cfg.LDAP.Disabled
				newCfgLDAPDisabled := newCfgLDAPExists && newCfg.LDAP.Disabled
				notifyDisabledProviderChangeIfNeeded(c.log, c.categoriesDisabledProvidersChanges, categoryID, types.ProviderLDAP, cfgLDAPDisabled, newCfgLDAPDisabled)

				cfgSAMLExists := cfg.SAML != nil
				newCfgSAMLExists := newCfg.SAML != nil

				cfgSAMLEnabled := cfgSAMLExists && !cfg.SAML.Disabled && cfg.SAML.ConfigSource == model.CategoryAuthenticationConfigSourceCustom && cfg.SAML.SAMLConfig != nil
				newCfgSAMLEnabled := newCfgSAMLExists && !newCfg.SAML.Disabled && newCfg.SAML.ConfigSource == model.CategoryAuthenticationConfigSourceCustom && newCfg.SAML.SAMLConfig != nil
				notifyProviderChangeIfNeeded(c.log, c.providerChanges, &categoryID, types.ProviderSAML, cfgSAMLEnabled, newCfgSAMLEnabled)

				cfgSAMLDisabled := cfgSAMLExists && cfg.SAML.Disabled
				newCfgSAMLDisabled := newCfgSAMLExists && newCfg.SAML.Disabled
				notifyDisabledProviderChangeIfNeeded(c.log, c.categoriesDisabledProvidersChanges, categoryID, types.ProviderSAML, cfgSAMLDisabled, newCfgSAMLDisabled)

				cfgGoogleExists := cfg.Google != nil
				newCfgGoogleExists := newCfg.Google != nil

				cfgGoogleEnabled := cfgGoogleExists && !cfg.Google.Disabled && cfg.Google.ConfigSource == model.CategoryAuthenticationConfigSourceCustom && cfg.Google.GoogleConfig != nil
				newCfgGoogleEnabled := newCfgGoogleExists && !newCfg.Google.Disabled && newCfg.Google.ConfigSource == model.CategoryAuthenticationConfigSourceCustom && newCfg.Google.GoogleConfig != nil
				notifyProviderChangeIfNeeded(c.log, c.providerChanges, &categoryID, types.ProviderGoogle, cfgGoogleEnabled, newCfgGoogleEnabled)

				cfgGoogleDisabled := cfgGoogleExists && cfg.Google.Disabled
				newCfgGoogleDisabled := newCfgGoogleExists && newCfg.Google.Disabled
				notifyDisabledProviderChangeIfNeeded(c.log, c.categoriesDisabledProvidersChanges, categoryID, types.ProviderGoogle, cfgGoogleDisabled, newCfgGoogleDisabled)

				if newCfgLocalEnabled {
					hasProviders = true
				}

				if newCfgLDAPEnabled && newCfg.LDAP.LDAPConfig != nil {
					hasProviders = true

					var cfgLDAPConfig model.LDAPConfig
					if cfgLDAPEnabled && cfg.LDAP.LDAPConfig != nil {
						cfgLDAPConfig = *cfg.LDAP.LDAPConfig
					}

					notifyIfNeeded(changesChans.ldapChanges, cfgLDAPConfig, *newCfg.LDAP.LDAPConfig)
				}

				if newCfgSAMLEnabled && newCfg.SAML.SAMLConfig != nil {
					hasProviders = true

					var cfgSAMLConfig model.SAMLConfig
					if cfgSAMLEnabled && cfg.SAML.SAMLConfig != nil {
						cfgSAMLConfig = *cfg.SAML.SAMLConfig
					}

					notifyIfNeeded(changesChans.samlChanges, cfgSAMLConfig, *newCfg.SAML.SAMLConfig)
				}

				if newCfgGoogleEnabled && newCfg.Google.GoogleConfig != nil {
					hasProviders = true

					var cfgGoogleConfig model.GoogleConfig
					if cfgGoogleEnabled && cfg.Google.GoogleConfig != nil {
						cfgGoogleConfig = *cfg.Google.GoogleConfig
					}

					notifyIfNeeded(changesChans.googleChanges, cfgGoogleConfig, *newCfg.Google.GoogleConfig)
				}

				// If the category has providers, add it to the map.
				c.categoriesMux.Lock()
				if hasProviders {
					c.categoriesChanges[categoryID] = changesChans
				} else {
					delete(c.categoriesChanges, categoryID)
				}
				c.categoriesMux.Unlock()
			}

			// Handle categories that were deleted from the DB.
			for categoryID, entry := range cfgCategories {
				if _, ok := newCfgCategories[categoryID]; ok {
					continue
				}

				c.log.Info().Str("category", categoryID).Msg("category removed from DB, disabling all its providers")

				cfg := entry.Authentication

				// Send disable events for all active providers in the deleted category.
				if cfg.Local != nil {
					if cfg.Local.Disabled {
						c.categoriesDisabledProvidersChanges <- categoryDisabledProviderChange{
							CategoryID: categoryID,
							Provider:   types.ProviderLocal,
							Disabled:   false,
						}
					} else {
						c.providerChanges <- providerChange{
							CategoryID: &categoryID,
							Provider:   types.ProviderLocal,
							Enabled:    false,
						}
					}
				}

				if cfg.LDAP != nil {
					if cfg.LDAP.Disabled {
						c.categoriesDisabledProvidersChanges <- categoryDisabledProviderChange{
							CategoryID: categoryID,
							Provider:   types.ProviderLDAP,
							Disabled:   false,
						}
					} else if cfg.LDAP.ConfigSource == model.CategoryAuthenticationConfigSourceCustom && cfg.LDAP.LDAPConfig != nil {
						c.providerChanges <- providerChange{
							CategoryID: &categoryID,
							Provider:   types.ProviderLDAP,
							Enabled:    false,
						}
					}
				}

				if cfg.SAML != nil {
					if cfg.SAML.Disabled {
						c.categoriesDisabledProvidersChanges <- categoryDisabledProviderChange{
							CategoryID: categoryID,
							Provider:   types.ProviderSAML,
							Disabled:   false,
						}
					} else if cfg.SAML.ConfigSource == model.CategoryAuthenticationConfigSourceCustom && cfg.SAML.SAMLConfig != nil {
						c.providerChanges <- providerChange{
							CategoryID: &categoryID,
							Provider:   types.ProviderSAML,
							Enabled:    false,
						}
					}
				}

				if cfg.Google != nil {
					if cfg.Google.Disabled {
						c.categoriesDisabledProvidersChanges <- categoryDisabledProviderChange{
							CategoryID: categoryID,
							Provider:   types.ProviderGoogle,
							Disabled:   false,
						}
					} else if cfg.Google.ConfigSource == model.CategoryAuthenticationConfigSourceCustom && cfg.Google.GoogleConfig != nil {
						c.providerChanges <- providerChange{
							CategoryID: &categoryID,
							Provider:   types.ProviderGoogle,
							Enabled:    false,
						}
					}
				}

				c.categoriesMux.Lock()
				delete(c.categoriesChanges, categoryID)
				c.categoriesMux.Unlock()
			}

			cfgCategories = newCfgCategories
		}
	})
}

func (c *cfgWatcher) getOrCreateCategoryChangesChannels(categoryID string) *providerChangesChannels {
	c.categoriesMux.RLock()
	defer c.categoriesMux.RUnlock()

	if changesChans, ok := c.categoriesChanges[categoryID]; ok {
		return changesChans
	}

	changesChans := &providerChangesChannels{
		ldapChanges:   make(chan model.LDAPConfig, 1024),
		samlChanges:   make(chan model.SAMLConfig, 1024),
		googleChanges: make(chan model.GoogleConfig, 1024),
	}

	return changesChans
}

func notifyProviderChangeIfNeeded(log *zerolog.Logger, channel chan providerChange, categoryID *string, prv string, enabled, newEnabled bool) {
	if enabled == newEnabled {
		return
	}

	action := "enable"
	if !newEnabled {
		action = "disable"
	}

	evt := log.Debug().Str("provider", prv).Str("action", action)
	if categoryID != nil {
		evt = evt.Str("category", *categoryID)
	}
	evt.Msg("provider state change detected")

	channel <- providerChange{
		CategoryID: categoryID,
		Provider:   prv,
		Enabled:    newEnabled,
	}
}

func notifyDisabledProviderChangeIfNeeded(log *zerolog.Logger, channel chan categoryDisabledProviderChange, categoryID string, prv string, disabled, newDisabled bool) {
	if disabled == newDisabled {
		return
	}

	action := "disabled"
	if !newDisabled {
		action = "re-enabled"
	}

	log.Debug().Str("provider", prv).Str("category", categoryID).Str("action", action).Msg("category disabled provider change detected")

	channel <- categoryDisabledProviderChange{
		CategoryID: categoryID,
		Provider:   prv,
		Disabled:   newDisabled,
	}
}

func notifyIfNeeded[T any](channel chan T, cfg T, newCfg T) {
	if !cmp.Equal(cfg, newCfg) {
		channel <- newCfg
	}
}

func notifyBrandingDomainChangeIfNeeded(channel chan categoryBrandingDomainChange, categoryID string, host, newHost *string, auth *model.CategoryAuthentication) {
	if cmp.Equal(host, newHost) {
		return
	}

	channel <- categoryBrandingDomainChange{
		CategoryID:     categoryID,
		Host:           newHost,
		Authentication: auth,
	}
}

func addLDAPWatcher(ctx context.Context, wg *sync.WaitGroup, log *zerolog.Logger, changesChan chan model.LDAPConfig, p provider.ConfigurableProvider[model.LDAPConfig]) {
	wg.Go(func() {
		for {
			select {
			case <-ctx.Done():
				return

			case cfg := <-changesChan:
				log.Debug().Msg("reloading LDAP configuration")
				if err := p.LoadConfig(ctx, cfg); err != nil {
					log.Error().Err(err).Msg("load new LDAP configuration")
				} else {
					log.Info().Msg("successfully reloaded LDAP configuration")
				}
			}
		}
	})
}

func addSAMLWatcher(ctx context.Context, wg *sync.WaitGroup, log *zerolog.Logger, changesChan chan model.SAMLConfig, p provider.ConfigurableProvider[model.SAMLConfig]) {
	wg.Go(func() {
		for {
			select {
			case <-ctx.Done():
				return

			case cfg := <-changesChan:
				log.Debug().Msg("reloading SAML configuration")
				if err := p.LoadConfig(ctx, cfg); err != nil {
					log.Error().Err(err).Msg("load new SAML configuration")
				} else {
					log.Info().Msg("successfully reloaded SAML configuration")
				}
			}
		}
	})
}

func addGoogleWatcher(ctx context.Context, wg *sync.WaitGroup, log *zerolog.Logger, changesChan chan model.GoogleConfig, p provider.ConfigurableProvider[model.GoogleConfig]) {
	wg.Go(func() {
		for {
			select {
			case <-ctx.Done():
				return

			case cfg := <-changesChan:
				log.Debug().Msg("reloading Google configuration")
				if err := p.LoadConfig(ctx, cfg); err != nil {
					log.Error().Err(err).Msg("load new Google configuration")
				} else {
					log.Info().Msg("successfully reloaded Google configuration")
				}
			}
		}
	})
}
