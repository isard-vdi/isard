package providermanager

import (
	"context"
	"net/http"
	"slices"
	"sync"

	"gitlab.com/isard/isardvdi/authentication/cfg"
	"gitlab.com/isard/isardvdi/authentication/model"
	"gitlab.com/isard/isardvdi/authentication/provider"
	"gitlab.com/isard/isardvdi/authentication/provider/types"

	"github.com/crewjam/saml/samlsp"
	"github.com/rs/zerolog"
	r "gopkg.in/rethinkdb/rethinkdb-go.v6"
)

type Interface interface {
	Manage(ctx context.Context, wg *sync.WaitGroup)
	Providers(categoryID string) []string
	Provider(p string, categoryID string) provider.Provider
	Healthcheck() error
	SAML(categoryID string, host string) *samlsp.Middleware
}

var _ Interface = &ProviderManager{}

type providerSet struct {
	providers      map[string]provider.Provider
	watcherCancels map[string]context.CancelFunc
}

func InitProviderManager(cfg cfg.Authentication, log *zerolog.Logger, db r.QueryExecutor) *ProviderManager {
	cfgWatcher := initCfgWatcher(log)

	m := &ProviderManager{
		log: log,
		cfg: cfg,
		db:  db,

		cfgWatcher: cfgWatcher,
		global: providerSet{
			providers:      initProvidersMap(cfg, log, db),
			watcherCancels: map[string]context.CancelFunc{},
		},
		categories:                  map[string]*providerSet{},
		categoriesDisabledProviders: map[string]map[string]bool{},
		brandingDomains:             map[string]categoryBrandingDomainChange{},
	}

	return m
}

func initProvidersMap(cfg cfg.Authentication, log *zerolog.Logger, db r.QueryExecutor) map[string]provider.Provider {
	return map[string]provider.Provider{
		types.ProviderUnknown:  &provider.Unknown{},
		types.ProviderForm:     provider.InitForm(cfg, log, nil, nil),
		types.ProviderExternal: provider.InitExternal(db),
	}
}

type ProviderManager struct {
	mux sync.RWMutex

	log *zerolog.Logger
	cfg cfg.Authentication
	db  r.QueryExecutor

	cfgWatcher *cfgWatcher

	httpClient *http.Client

	global                      providerSet
	categories                  map[string]*providerSet
	categoriesDisabledProviders map[string]map[string]bool
	brandingDomains             map[string]categoryBrandingDomainChange
}

func (m *ProviderManager) resolveScope(categoryID *string) (*zerolog.Logger, *providerSet) {
	if categoryID == nil {
		return m.log, &m.global
	}

	log := m.log.With().Str("provider_category", *categoryID).Logger()

	if s, ok := m.categories[*categoryID]; ok {
		return &log, s
	}

	return &log, nil
}

func (m *ProviderManager) readScope(categoryID string) *providerSet {
	if s, ok := m.categories[categoryID]; ok {
		return s
	}
	return &m.global
}

func (m *ProviderManager) Manage(ctx context.Context, wg *sync.WaitGroup) {
	m.log.Debug().Msg("starting provider manager")

	// Start watching for configuration changes.
	m.cfgWatcher.Watch(ctx, wg, m.db)

	wg.Go(func() {
		for {
			select {
			case <-ctx.Done():
				return

			case change := <-m.cfgWatcher.providerChanges:
				m.handleProviderChange(ctx, wg, change)

			case change := <-m.cfgWatcher.categoriesDisabledProvidersChanges:
				m.handleCategoryDisabledProviderChange(change.CategoryID, change.Provider, change.Disabled)

			case change := <-m.cfgWatcher.categoriesBrandingDomainChanges:
				m.handleCategoryBrandingDomainChange(ctx, change)
			}
		}
	})
}

func providerConfigSource(auth *model.CategoryAuthentication, name string) (model.CategoryAuthenticationConfigSource, bool) {
	if auth == nil {
		return model.CategoryAuthenticationConfigSourceGlobal, false
	}

	var source model.CategoryAuthenticationConfigSource
	var disabled bool

	switch name {
	case types.ProviderSAML:
		if auth.SAML == nil {
			return model.CategoryAuthenticationConfigSourceGlobal, false
		}
		source, disabled = auth.SAML.ConfigSource, auth.SAML.Disabled
	case types.ProviderGoogle:
		if auth.Google == nil {
			return model.CategoryAuthenticationConfigSourceGlobal, false
		}
		source, disabled = auth.Google.ConfigSource, auth.Google.Disabled
	case types.ProviderLDAP:
		if auth.LDAP == nil {
			return model.CategoryAuthenticationConfigSourceGlobal, false
		}
		source, disabled = auth.LDAP.ConfigSource, auth.LDAP.Disabled
	default:
		return model.CategoryAuthenticationConfigSourceGlobal, false
	}

	if source != model.CategoryAuthenticationConfigSourceCustom {
		source = model.CategoryAuthenticationConfigSourceGlobal
	}

	return source, disabled
}

// handleCategoryBrandingDomainChange stores the branding domain and applies it
// to providers matching the category's config_source.
func (m *ProviderManager) handleCategoryBrandingDomainChange(ctx context.Context, change categoryBrandingDomainChange) {
	log := m.log.With().Str("category", change.CategoryID).Logger()
	if change.Host != nil {
		log.Info().Str("host", *change.Host).Msg("loading branding domain")
	} else {
		log.Info().Msg("clearing branding domain")
	}

	type brandingTarget struct {
		name     string
		provider provider.BrandingAwareProvider
	}

	var targets []brandingTarget

	collectTargets := func(scope *providerSet, expectedSource model.CategoryAuthenticationConfigSource) {
		for name, prv := range scope.providers {
			bap, ok := prv.(provider.BrandingAwareProvider)
			if !ok {
				continue
			}

			source, disabled := providerConfigSource(change.Authentication, name)

			if disabled || source != expectedSource {
				continue
			}

			targets = append(targets, brandingTarget{name: name, provider: bap})
		}
	}

	m.mux.Lock()
	if change.Host != nil {
		m.brandingDomains[change.CategoryID] = change
	} else {
		delete(m.brandingDomains, change.CategoryID)
	}
	if catScope, ok := m.categories[change.CategoryID]; ok {
		collectTargets(catScope, model.CategoryAuthenticationConfigSourceCustom)
	}
	collectTargets(&m.global, model.CategoryAuthenticationConfigSourceGlobal)
	m.mux.Unlock()

	for _, t := range targets {
		if err := t.provider.SetBrandingHost(ctx, change.CategoryID, change.Host); err != nil {
			log.Error().Err(err).Str("provider", t.name).Msg("update branding host on provider")
		}
	}

	if change.Host != nil {
		log.Info().Str("host", *change.Host).Msg("branding domain loaded")
	} else {
		log.Info().Msg("branding domain cleared")
	}
}

// handleCategoryDisabledProviderChange tracks whether a provider is explicitly disabled in a category.
func (m *ProviderManager) handleCategoryDisabledProviderChange(categoryID string, prv string, disabled bool) {
	m.mux.Lock()
	defer m.mux.Unlock()

	if !disabled {
		d, ok := m.categoriesDisabledProviders[categoryID]
		if !ok {
			return
		}

		delete(d, prv)
		m.log.Info().Str("category", categoryID).Str("provider", prv).Msg("category provider re-enabled (removed from disabled list)")

		if len(d) == 0 {
			delete(m.categoriesDisabledProviders, categoryID)
		}

		return
	}

	if _, ok := m.categoriesDisabledProviders[categoryID]; !ok {
		m.categoriesDisabledProviders[categoryID] = map[string]bool{}
	}

	m.categoriesDisabledProviders[categoryID][prv] = true
	m.log.Info().Str("category", categoryID).Str("provider", prv).Msg("category provider explicitly disabled")
}

// isCategoryDisabledProvider returns true if the provider is explicitly disabled in the category.
func (m *ProviderManager) isCategoryDisabledProvider(categoryID string, prv string) bool {
	d, ok := m.categoriesDisabledProviders[categoryID]
	if !ok {
		return false
	}

	return d[prv]
}

func (m *ProviderManager) handleProviderChange(ctx context.Context, wg *sync.WaitGroup, change providerChange) {
	evt := m.log.Info()
	if change.CategoryID != nil {
		evt = evt.Str("category", *change.CategoryID)
	}
	evt.Str("provider", change.Provider).Bool("enabled", change.Enabled).Msg("processing provider change")

	if change.Enabled {
		m.enableProvider(ctx, wg, change.Provider, change.CategoryID)

	} else {
		m.disableProvider(change.Provider, change.CategoryID)
	}
}

func (m *ProviderManager) disableProvider(prv string, categoryID *string) {
	m.mux.Lock()
	defer m.mux.Unlock()

	log, scope := m.resolveScope(categoryID)
	if scope == nil {
		log.Warn().Msg("attempted to disable category provider, but category was not found")
		return
	}

	disableProvider(log, scope, prv)

	// Clean up category if it has no active providers.
	if categoryID != nil && isProvidersEmpty(scope.providers) {
		log.Debug().Msg("category has no active providers, removing scope")
		delete(m.categories, *categoryID)
		m.cfgWatcher.categoriesMux.Lock()
		delete(m.cfgWatcher.categoriesChanges, *categoryID)
		m.cfgWatcher.categoriesMux.Unlock()
	}
}

func disableProvider(log *zerolog.Logger, scope *providerSet, p string) {
	if cancel, ok := scope.watcherCancels[p]; ok {
		cancel()
		delete(scope.watcherCancels, p)
	}

	switch p {
	case types.ProviderLocal, types.ProviderLDAP:
		if f, ok := scope.providers[types.ProviderForm].(*provider.Form); ok {
			f.DisableProvider(p)
		}

		return
	}

	if _, ok := scope.providers[p]; !ok {
		log.Warn().Str("provider", p).Msg("attempted to disable provider, but was nonexistent")
		return
	}

	delete(scope.providers, p)
	log.Info().Str("provider", p).Msg("provider disabled")
}

func isProvidersEmpty(prvs map[string]provider.Provider) bool {
	for name, prv := range prvs {
		switch name {
		case types.ProviderUnknown, types.ProviderExternal:
			continue
		case types.ProviderForm:
			if f, ok := prv.(*provider.Form); ok && len(f.Providers()) > 0 {
				return false
			}
		default:
			return false
		}
	}

	return true
}

func (m *ProviderManager) enableProvider(ctx context.Context, wg *sync.WaitGroup, prv string, categoryID *string) {
	m.mux.Lock()
	defer m.mux.Unlock()

	log, scope := m.resolveScope(categoryID)
	if scope == nil {
		log.Debug().Msg("creating new provider scope for category")
		scope = &providerSet{
			providers:      initProvidersMap(m.cfg, log, m.db),
			watcherCancels: map[string]context.CancelFunc{},
		}
		m.categories[*categoryID] = scope
	}

	changesChans := m.cfgWatcher.globalChanges
	if categoryID != nil {
		m.cfgWatcher.categoriesMux.RLock()
		var ok bool
		changesChans, ok = m.cfgWatcher.categoriesChanges[*categoryID]
		m.cfgWatcher.categoriesMux.RUnlock()
		if !ok {
			log.Error().Msg("attempted to enable category provider, but category changes channels were not found")
			return
		}
	}

	enableProvider(ctx, wg, enableProviderParams{
		log:          log,
		cfg:          m.cfg,
		db:           m.db,
		changesChans: changesChans,
		categoryID:   categoryID,
		httpClient:   m.httpClient,
	}, scope, prv)

	m.applyStoredBranding(ctx, log, scope, prv, categoryID)
}

// applyStoredBranding applies stored branding domains to a newly enabled provider.
// Must be called with m.mux held.
func (m *ProviderManager) applyStoredBranding(ctx context.Context, log *zerolog.Logger, scope *providerSet, prv string, categoryID *string) {
	if categoryID == nil {
		return
	}

	bap, ok := scope.providers[prv].(provider.BrandingAwareProvider)
	if !ok {
		return
	}

	bd, ok := m.brandingDomains[*categoryID]
	if !ok {
		return
	}

	if err := bap.SetBrandingHost(ctx, bd.CategoryID, bd.Host); err != nil {
		log.Error().Err(err).Str("category", bd.CategoryID).Msg("apply stored branding host to new provider")
	}
}

type enableProviderParams struct {
	log          *zerolog.Logger
	cfg          cfg.Authentication
	db           r.QueryExecutor
	changesChans *providerChangesChannels
	categoryID   *string
	httpClient   *http.Client
}

func enableProvider(ctx context.Context, wg *sync.WaitGroup, params enableProviderParams, scope *providerSet, p string) {
	if _, ok := scope.providers[p]; ok {
		params.log.Warn().Str("provider", p).Msg("attempted to enable provider, but was already enabled")
		return
	}

	switch p {
	case types.ProviderLocal:
		if f, ok := scope.providers[types.ProviderForm].(*provider.Form); ok {
			if f.Provider(types.ProviderLocal) != nil {
				params.log.Warn().Str("provider", p).Msg("attempted to enable provider, but was already enabled")
				return
			}

			f.EnableProvider(provider.InitLocal(params.db))
		}

	case types.ProviderLDAP:
		if f, ok := scope.providers[types.ProviderForm].(*provider.Form); ok {
			if f.Provider(types.ProviderLDAP) != nil {
				params.log.Warn().Str("provider", p).Msg("attempted to enable provider, but was already enabled")
				return
			}

			ldap := provider.InitLDAP(params.cfg.Secret, params.log, params.db)

			watcherCtx, cancel := context.WithCancel(ctx)
			scope.watcherCancels[p] = cancel
			addLDAPWatcher(watcherCtx, wg, params.log, params.changesChans.ldapChanges, ldap)

			f.EnableProvider(ldap)
		}

	case types.ProviderSAML:
		saml := provider.InitSAML(params.cfg.Secret, params.cfg.Host, params.categoryID, params.log, params.db, params.httpClient)

		watcherCtx, cancel := context.WithCancel(ctx)
		scope.watcherCancels[p] = cancel
		addSAMLWatcher(watcherCtx, wg, params.log, params.changesChans.samlChanges, saml)

		scope.providers[p] = saml

	case types.ProviderGoogle:
		google := provider.InitGoogle(params.cfg)

		watcherCtx, cancel := context.WithCancel(ctx)
		scope.watcherCancels[p] = cancel
		addGoogleWatcher(watcherCtx, wg, params.log, params.changesChans.googleChanges, google)

		scope.providers[p] = google

	default:
		params.log.Error().Str("provider", p).Msg("attempted to enable provider, but we don't know it")
		return
	}

	params.log.Info().Str("provider", p).Msg("provider enabled")
}

func (m *ProviderManager) Providers(categoryID string) []string {
	m.mux.RLock()
	defer m.mux.RUnlock()

	providers := listProviders(m.readScope(categoryID).providers)

	// Fallback to global providers.
	for _, p := range listProviders(m.global.providers) {
		if !slices.Contains(providers, p) {
			providers = append(providers, p)
		}
	}

	// Filter out providers explicitly disabled in the category.
	providers = slices.DeleteFunc(providers, func(p string) bool {
		return m.isCategoryDisabledProvider(categoryID, p)
	})

	slices.Sort(providers)

	m.log.Debug().Str("category", categoryID).Strs("providers", providers).Msg("resolved providers for category")

	return providers
}

func listProviders(prvs map[string]provider.Provider) []string {
	providers := []string{}
	for k, v := range prvs {
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

	return providers
}

func (m *ProviderManager) Provider(p string, categoryID string) provider.Provider {
	m.mux.RLock()
	defer m.mux.RUnlock()

	// Don't fall back if the provider is explicitly disabled in the category.
	if m.isCategoryDisabledProvider(categoryID, p) {
		m.log.Debug().Str("provider", p).Str("category", categoryID).Msg("provider explicitly disabled in category, returning unknown")
		return getProvider(m.global.providers, types.ProviderUnknown)
	}

	prv := getProvider(m.readScope(categoryID).providers, p)
	if prv != nil && prv.String() != types.ProviderUnknown {
		m.log.Debug().Str("provider", p).Str("category", categoryID).Str("resolved", prv.String()).Msg("resolved provider for category")
		return prv
	}

	// Fallback to global providers.
	globalPrv := getProvider(m.global.providers, p)
	if globalPrv == nil {
		m.log.Debug().Str("provider", p).Str("category", categoryID).Msg("provider not found")
		return nil
	}

	m.log.Debug().Str("provider", p).Str("category", categoryID).Str("resolved", globalPrv.String()).Msg("falling back to global provider")
	return globalPrv
}

func getProvider(prvs map[string]provider.Provider, p string) provider.Provider {
	if prv := prvs[p]; prv != nil {
		return prv
	}

	if f, ok := prvs[types.ProviderForm].(*provider.Form); ok {
		if prv := f.Provider(p); prv != nil {
			return prv
		}
	}

	return prvs[types.ProviderUnknown]
}

func (m *ProviderManager) Healthcheck() error {
	m.mux.RLock()
	defer m.mux.RUnlock()

	for _, p := range m.global.providers {
		if err := p.Healthcheck(); err != nil {
			m.log.Warn().Err(err).Str("provider", p.String()).Msg("service unhealthy")

			return err
		}
	}

	for categoryID, scope := range m.categories {
		for _, p := range scope.providers {
			if err := p.Healthcheck(); err != nil {
				m.log.Warn().Err(err).Str("provider", p.String()).Str("provider_category", categoryID).Msg("service unhealthy")

				return err
			}
		}
	}

	return nil
}

func (m *ProviderManager) SAML(categoryID string, host string) *samlsp.Middleware {
	s, ok := m.Provider(types.ProviderSAML, categoryID).(*provider.SAML)
	if !ok {
		return nil
	}

	return s.Middleware(host)
}
