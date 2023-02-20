import store from '@/store/index.js'
import { StringUtils } from '../utils/stringUtils'
import * as cookies from 'tiny-cookie'

export function auth (to, from, next, allowedRoles) {
  if (StringUtils.isNullOrUndefinedOrEmpty(localStorage.token)) {
    if (cookies.getCookie('authorization')) {
      const jwt = JSON.parse(atob(cookies.getCookie('authorization').split('.')[1]))
      if (jwt.type === 'register') {
        store.dispatch('saveNavigation', { url: to })
        next({ name: 'Register' })
      } else {
        localStorage.token = cookies.getCookie('authorization')
        store.dispatch('loginSuccess', localStorage.token)

        store.dispatch('saveNavigation', { url: to })
        next({ name: 'desktops' })
      }
    } else {
      store.dispatch('logout')
    }
  } else {
    if (new Date() > new Date(JSON.parse(atob(localStorage.token.split('.')[1])).exp * 1000)) {
      store.dispatch('logout')
    } else {
      checkRoutePermission(next, allowedRoles)
      store.dispatch('saveNavigation', { url: to })
      next()
    }
  }
}

export function checkRoutePermission (next, allowedRoles) {
  if (!allowedRoles.includes(JSON.parse(atob(localStorage.token.split('.')[1])).data.role_id)) {
    next({ name: 'desktops' })
  }
}
