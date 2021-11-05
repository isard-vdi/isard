import ErrorPage from '@/views/ErrorPage.vue'
import ExpiredSession from '@/views/ExpiredSession.vue'
import Login from '@/views/Login.vue'
import Maintenance from '@/views/Maintenance.vue'
import NotFound from '@/views/NotFound.vue'
import Register from '@/views/Register.vue'
import Rdp from '@/views/Rdp.vue'
import Deployments from '@/views/Deployments.vue'
import Deployment from '@/views/Deployment.vue'
import Vue from 'vue'
import VueRouter from 'vue-router'
import { auth } from './auth'
import MainLayout from '@/layouts/MainLayout.vue'
import Desktops from '@/pages/Desktops.vue'
import DesktopNew from '@/pages/DesktopNew.vue'
import { appTitle } from '../shared/constants'

Vue.use(VueRouter)

const router = new VueRouter({
  routes: [
    {
      path: '/',
      name: 'Home',
      redirect: '/desktops',
      component: MainLayout,
      children: [
        {
          path: 'desktops',
          name: 'desktops',
          component: Desktops,
          meta: {
            title: 'Desktops'
          }
        },
        {
          path: 'desktops/new',
          name: 'NewDesktop',
          component: DesktopNew,
          meta: {
            title: 'New Desktop'
          }
        }
      ],
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
      path: '/deployments',
      name: 'Deployments',
      component: Deployments,
      meta: {
        requiresAuth: true
      }
    },
    {
      path: '/deployment/:id',
      name: 'Deployment',
      component: Deployment,
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
  document.title = to.meta.title ? `${appTitle} - ${to.meta.title}` : appTitle

  if (to.matched.some(record => record.meta.requiresAuth)) {
    auth(to, from, next)
  } else {
    next()
  }
})

export default router
