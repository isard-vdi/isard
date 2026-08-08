import DOMPurify from 'dompurify'

// Admin-authored notification bodies and footers are rendered with v-html, so
// they are sanitized here before they reach the DOM. The server refuses the
// dangerous constructs on write, but rows stored before that gate existed are
// still out there, and this is what keeps them inert.
export const sanitizeHtml = (html) => (html ? DOMPurify.sanitize(String(html)) : '')

export default {
  install (Vue) {
    Vue.prototype.$sanitize = sanitizeHtml
  }
}
