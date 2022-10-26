import axios from 'axios'
import store from '../store'
import router from '@/router'

export default function axiosSetUp () {
  // point to your API endpoint
  axios.defaults.baseURL = `${window.location.protocol}//${window.location.host}`
  // Add a request interceptor
  axios.interceptors.request.use(
    // Spinning show
    function (config) {
      document.body.classList.add('loading-cursor')
      config.headers.Authorization = `Bearer ${store.getters.getToken}`
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
      // Any status code that lie within the range of 2xx cause this function to trigger
      // Do something with response data
      return response
    },
    async function (error) {
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
      if (error.response.status === 503) {
        router.replace({ name: 'Maintenance' })
      } else if (error.response.status === 500 || error.response.status === 401) {
        router.replace({
          name: 'Error',
          params: { code: error.response && error.response.status.toString() }
        })
      }
      return Promise.reject(error)
    }
  )
}
