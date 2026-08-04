import { Locale } from '@/lib/i18n'

const OFFICIAL_DOCS_ROOT = 'https://isard.gitlab.io/isardvdi-docs/'

export const DEFAULT_DOCS_URL = OFFICIAL_DOCS_ROOT
export const DEFAULT_VIEWERS_DOCS_URL = `${OFFICIAL_DOCS_ROOT}user/viewers/viewers/`

const OFFICIAL_DOCS_LANGUAGE_PATH: Partial<Record<Locale, string>> = {
  'es-ES': 'es/',
  'ca-ES': 'ca/'
}

// Only URLs that are the official docs (not custom URI in .cfg file)
// may be rewritten; anything else is opened verbatim.
const officialDocsPath = (url: string): string | null => {
  const normalized = `${url.replace(/\/+$/, '')}/`

  if (normalized === DEFAULT_DOCS_URL) return ''
  if (normalized === DEFAULT_VIEWERS_DOCS_URL)
    return DEFAULT_VIEWERS_DOCS_URL.slice(OFFICIAL_DOCS_ROOT.length)

  return null
}

export const docsUrl = (
  configuredUrl: string | undefined,
  defaultUrl: string,
  locale: string
): string => {
  const url = configuredUrl || defaultUrl
  const path = officialDocsPath(url)

  if (path === null) return url

  return OFFICIAL_DOCS_ROOT + (OFFICIAL_DOCS_LANGUAGE_PATH[locale as Locale] ?? '') + path
}

// NOTE: renaming a heading in the docs silently breaks the link here. Give the
// headings explicit ids (`## VNC al navegador {#vnc-browser}`) so the anchors
// stop depending on the prose, and this map collapses back to one per viewer.
const VIEWER_GUIDE_ANCHOR: Record<string, Partial<Record<Locale, string>>> = {
  'browser-vnc': {
    'en-US': '#vnc-browser',
    'es-ES': '#vnc-en-navegador',
    'ca-ES': '#vnc-al-navegador'
  },
  'browser-rdp': {
    'en-US': '#rdp-browser-viewer',
    'es-ES': '#rdp-en-el-navegador',
    'ca-ES': '#rdp-al-navegador'
  },
  'file-spice': {
    'en-US': '#spice'
  },
  'file-rdpgw': {
    'en-US': '#native-rdp',
    'es-ES': '#rdp-nativo',
    'ca-ES': '#rdp-natiu'
  },
  'file-rdpvpn': {
    'en-US': '#native-rdp',
    'es-ES': '#rdp-nativo',
    'ca-ES': '#rdp-natiu'
  }
}

export const viewerGuideUrl = (locale: string, viewerId: string): string => {
  const anchors = VIEWER_GUIDE_ANCHOR[viewerId]
  const anchor = anchors?.[locale as Locale] ?? anchors?.['en-US'] ?? ''

  return docsUrl(undefined, DEFAULT_VIEWERS_DOCS_URL, locale) + anchor
}
