import { getCookie } from 'tiny-cookie'

export function listenCookieChange (callback, cookieName, interval = 1000) {
  let lastCookie = getCookie(cookieName)
  setInterval(() => {
    const cookie = getCookie(cookieName)
    if (cookie !== lastCookie) {
      try {
        // eslint-disable-next-line node/no-callback-literal
        callback({ oldValue: lastCookie, newValue: cookie }, cookieName)
      } finally {
        lastCookie = cookie
      }
    }
  }, interval)
}
