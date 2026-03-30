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

		if len(d) == 0 {
			delete(m.categoriesDisabledProviders, categoryID)
		}

		return
	}

	if _, ok := m.categoriesDisabledProviders[categoryID]; !ok {
		m.categoriesDisabledProviders[categoryID] = map[string]bool{}
	}

	m.categoriesDisabledProviders[categoryID][prv] = true
}

// isCategoryDisabledProvider returns true if the provider is explicitly disabled in the category.
func (m *ProviderManager) isCategoryDisabledProvider(categoryID string, prv string) bool {
	d, ok := m.categoriesDisabledProviders[categoryID]
	if !ok {
		return false
	}

	return d[prv]
}

func (m *ProviderManager) Manage(ctx context.Context, wg *sync.WaitGroup) {
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
				if !m.handleCategoryBrandingDomainChange(ctx, change) {
					// The target provider doesn't exist yet (e.g. providerChange hasn't
					// been processed). Re-enqueue so it gets retried after the provider
					// is created.
					change.retries++
					if change.retries > 10 {
						m.log.Warn().Str("category", change.CategoryID).Msg("branding domain change exceeded max retries, discarding")
					} else {
						m.cfgWatcher.categoriesBrandingDomainChanges <- change
					}
				}
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

// handleCategoryBrandingDomainChange applies branding to providers matching the
// category's config_source. It returns true if at least one provider was updated.
func (m *ProviderManager) handleCategoryBrandingDomainChange(ctx context.Context, change categoryBrandingDomainChange) bool {
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

	m.mux.RLock()
	if catScope, ok := m.categories[change.CategoryID]; ok {
		collectTargets(catScope, model.CategoryAuthenticationConfigSourceCustom)
	}
	collectTargets(&m.global, model.CategoryAuthenticationConfigSourceGlobal)
	m.mux.RUnlock()

	for _, t := range targets {
		if err := t.provider.SetBrandingHost(ctx, change.CategoryID, change.Host); err != nil {
			log.Error().Err(err).Str("provider", t.name).Msg("update branding host on provider")
		}
	}

	return len(targets) > 0
}

func (m *ProviderManager) handleProviderChange(ctx context.Context, wg *sync.WaitGroup, change providerChange) {
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
		return getProvider(m.global.providers, types.ProviderUnknown)
	}

	prv := getProvider(m.readScope(categoryID).providers, p)
	if prv != nil && prv.String() != types.ProviderUnknown {
		return prv
	}

	// Fallback to global providers.
	return getProvider(m.global.providers, p)
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
