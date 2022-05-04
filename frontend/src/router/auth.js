import store from '@/store/index.js'
import { StringUtils } from '../utils/stringUtils'
import * as cookies from 'tiny-cookie'

export function auth (to, from, next) {
  if (StringUtils.isNullOrUndefinedOrEmpty(sessionStorage.token)) {
    if (cookies.getCookie('authorization')) {
      const jwt = JSON.parse(atob(cookies.getCookie('authorization').split('.')[1]))
      if (jwt.type === 'register') {
        store.dispatch('saveNavigation', { url: to })
        next({ name: 'Register' })
      } else {
        sessionStorage.token = cookies.getCookie('authorization')
        store.dispatch('loginSuccess', sessionStorage.token)

        store.dispatch('saveNavigation', { url: to })
        next({ name: 'desktops' })
      }
    } else {
      store.dispatch('logout')
    }
  } else {
    if (new Date() > new Date(JSON.parse(atob(sessionStorage.token.split('.')[1])).exp * 1000)) {
      store.dispatch('logout')
    } else {
      store.dispatch('saveNavigation', { url: to })
      next()
    }
  }
}
