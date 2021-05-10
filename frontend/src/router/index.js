import ErrorPage from '@/views/ErrorPage.vue'
import ExpiredSession from '@/views/ExpiredSession.vue'
import Login from '@/views/Login.vue'
import Maintenance from '@/views/Maintenance.vue'
import NotFound from '@/views/NotFound.vue'
import Register from '@/views/Register.vue'
import Home from '@/views/Home.vue'
import Rdp from '@/views/Rdp.vue'
import Vue from 'vue'
import VueRouter from 'vue-router'
import { auth } from './auth'

Vue.use(VueRouter)

const router = new VueRouter({
  routes: [
    {
      path: '/',
      name: 'Home',
      component: Home,
      meta: {
        requiresAuth: true
      }
    },
    {
      path: '/rdp',
      name: 'Rdp',
      component: Rdp,
      meta: {
        requiresAuth: true
      }
    },
    {
      path: '/login/:category?',
      name: 'Login',
      component: Login
    },
    {
      path: '/register',
      name: 'Register',
      component: Register
    },
    {
      path: '/error/:code',
      name: 'Error',
      component: ErrorPage
    },
    {
      path: '*',
      name: 'NotFound',
      component: NotFound
    },
    {
      path: '/maintenance',
      name: 'Maintenance',
      component: Maintenance
    },
    {
      path: '/expired_session',
      name: 'ExpiredSession',
      component: ExpiredSession
    }
  ],
  mode: 'history'
})

router.beforeEach((to, from, next) => {
  if (to.matched.some(record => record.meta.requiresAuth)) {
    auth(to, from, next)
  } else {
    next()
  }
})

export default router
