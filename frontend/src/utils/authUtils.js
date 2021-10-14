import store from '@/store/index.js'

export function authHeader () {
  // return authorization header with jwt token
  const token = store.getters.getToken()

  if (token) {
    return { Authorization: 'Bearer ' + token }
  } else {
    return {}
  }
}
