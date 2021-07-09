import store from '@/store/index.js'
import { StringUtils } from '../utils/stringUtils'
import * as cookies from 'tiny-cookie'

export function auth (to, from, next) {
  if (StringUtils.isNullOrUndefinedOrEmpty(localStorage.token)) {
    if (cookies.getCookie('authorization')) {
      const jwt = JSON.parse(atob(cookies.getCookie('authorization').split('.')[1]))
      if (jwt.type === 'register') {
        next({ name: 'Register' })
      } else {
        localStorage.token = cookies.getCookie('authorization')
        store.dispatch('loginSuccess', localStorage.token)
        next({ name: 'Home' })
      }
    } else {
      next({ name: 'Login' })
    }
  } else {
    if (new Date() > new Date(JSON.parse(atob(localStorage.token.split('.')[1])).exp * 1000)) {
      store.dispatch('logout')
    }
    next()
  }
}
