import * as cookies from 'tiny-cookie'
import axios from 'axios'

import store from '@/store/index.js'

export const apiAxios = axios.create({
  baseURL: `${window.location.protocol}//${window.location.host}/api/v2`,
  timeout: 10000,
  headers: {
    Accept: 'application/json'
  }
})

const cookieName = 'session'

export function auth (to, from, next) {
  const sessionCookie = cookies.getCookie(cookieName)
  // Si no la té que vagi a login
  if (isNullOrUndefined(sessionCookie)) {
    next({ name: 'Login' })
  }
  // Si la té comprovem que sigui vàlida
  axios.get('/check').then(response => {
    // Si es vàlida demanem les dades de l'usuari
    store.dispatch('setUser')
    next()
  }).catch(e => {
    if (e.response.status === 503) {
      next({ name: 'Maintenance' })
    }
    next({ name: 'Login' })
  })
}

function isNullOrUndefined (arg) {
  return arg === null || arg === undefined || arg === 'undefined'
}
