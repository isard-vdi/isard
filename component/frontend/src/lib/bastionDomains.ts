// Mirrors the limit apiv4 enforces on a target's domains.
export const MAX_BASTION_DOMAINS = 10

export const cleanDomains = (domains: readonly string[]): string[] => [
  ...new Set(domains.map((domain) => domain.trim()).filter(Boolean))
]

/** Order counts: the access URLs are built from the first domain. */
export const domainsChanged = (domains: readonly string[], saved: readonly string[]): boolean => {
  const next = cleanDomains(domains)
  const stored = cleanDomains(saved)
  return next.length !== stored.length || next.some((domain, index) => domain !== stored[index])
}

/** How many domains must go before the list can be saved. An unchanged list is never sent. */
export const domainsOverLimit = (domains: readonly string[], saved: readonly string[]): number =>
  domainsChanged(domains, saved)
    ? Math.max(0, cleanDomains(domains).length - MAX_BASTION_DOMAINS)
    : 0
