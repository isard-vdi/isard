import { getCookie } from 'tiny-cookie'

export function listenCookieChange (callback, cookieName, interval = 1000) {
  let lastCookie = getCookie(cookieName)
  setInterval(() => {
    const cookie = getCookie(cookieName)
    if (cookie !== lastCookie) {
      try {
        callback(null, { oldValue: lastCookie, newValue: cookie }, cookieName)
      } finally {
        lastCookie = cookie
      }
    }
  }, interval)
}
