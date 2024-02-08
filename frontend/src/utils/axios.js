import axios from 'axios'
import router from '@/router'
import { sessionCookieName } from '../shared/constants'
import { getCookie } from 'tiny-cookie'

export default function axiosSetUp () {
  // point to your API endpoint
  axios.defaults.baseURL = `${window.location.protocol}//${window.location.host}`
  // Add a request interceptor
  axios.interceptors.request.use(
    // Spinning show
    function (config) {
      document.body.classList.add('loading-cursor')
      if (document.querySelector('#content[type="submit"]')) {
        document.querySelector('#content[type="submit"]').setAttribute('disabled', 'disabled')
      }
      config.headers.Authorization = `Bearer ${getCookie(sessionCookieName)}`
      return config
    },
    function (error) {
      // Do something with request error
      return Promise.reject(error)
    }
  )

  // Add a response interceptor
  axios.interceptors.response.use(
    // Spinning hide
    function (response) {
      document.body.classList.remove('loading-cursor')
      if (document.querySelector('[type="submit"]')) {
        document.querySelector('[type="submit"]').removeAttribute('disabled')
      }
      // Any status code that lie within the range of 2xx cause this function to trigger
      // Do something with response data
      return response
    },
    async function (error) {
      document.body.classList.remove('loading-cursor')
      if (document.querySelector('[type="submit"]')) {
        document.querySelector('[type="submit"]').removeAttribute('disabled')
      }
      // Any status codes that falls outside the range of 2xx cause this function to trigger
      // Do something with response error

      // const originalRequest = error.config
      // if (
      //   error.response.status === 401 &&
      //   originalRequest.url.includes("auth/jwt/refresh/")
      // ) {
      //   store.commit("clearUserData");
      //   router.push("/login");
      //   return Promise.reject(error);
      // } else if (error.response.status === 401 && !originalRequest._retry) {
      //   originalRequest._retry = true;
      //   await store.dispatch("refreshToken");
      //   return axios(originalRequest);
      // }
      if (!error.config.url.includes('scheduler') && error.response.status === 503) {
        router.replace({ name: 'Maintenance' })
      } else if (error.response.status === 500) {
        router.replace({
          name: 'Error',
          params: { code: error.response && error.response.status.toString() }
        })
      } else if (error.response.status === 401) {
        router.replace({ name: 'Login' })
      }
      return Promise.reject(error)
    }
  )
}
