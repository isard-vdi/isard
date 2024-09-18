import Vue from 'vue'
import VueRouter from 'vue-router'
import moment from 'moment'
import { jwtDecode } from 'jwt-decode'
import { getCookie } from 'tiny-cookie'
import { isEmpty } from 'lodash'
import { appTitle } from '../shared/constants'
import i18n from '@/i18n'
import store from '@/store'

Vue.use(VueRouter)

const router = new VueRouter({
  routes: [
    {
      path: '/',
      name: 'Home',
      redirect: '/desktops',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        {
          path: 'desktops',
          name: 'desktops',
          component: () => import('@/pages/Desktops.vue'),
          meta: {
            title: i18n.t('router.titles.desktops'),
            allowedRoles: ['admin', 'manager', 'advanced', 'user']
          }
        },
        {
          path: 'desktops/new',
          name: 'desktopsnew',
          component: () => import('@/pages/DesktopNew.vue'),
          meta: {
            title: i18n.t('router.titles.new_desktop'),
            allowedRoles: ['admin', 'manager', 'advanced', 'user']
          }
        }
      ],
      meta: {
        requiresAuth: true
      }
    },
    {
      path: '/domain',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        {
          path: 'edit',
          name: 'domainedit',
          component: () => import('@/pages/DomainEdit.vue'),
          meta: {
            title: i18n.t('router.titles.edit-domain'),
            allowedRoles: ['admin', 'manager', 'advanced', 'user']
          }
        }
      ],
      meta: {
        requiresAuth: true
      }
    },
    {
      path: '/booking',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        {
          path: ':type/:id',
          name: 'booking',
          component: () => import('@/pages/Booking.vue'),
          meta: {
            title: i18n.t('router.titles.booking'),
            allowedRoles: ['admin', 'manager', 'advanced', 'user']
          }
        },
        {
          path: 'summary',
          name: 'bookingsummary',
          component: () => import('@/pages/BookingsSummary.vue'),
          meta: {
            title: i18n.t('router.titles.booking'),
            allowedRoles: ['admin', 'manager', 'advanced', 'user']
          }
        }
      ],
      meta: {
        requiresAuth: true
      }
    },
    {
      path: '/planning',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        {
          path: '',
          name: 'Planning',
          component: () => import('@/pages/Planning.vue'),
          meta: {
            title: i18n.t('router.titles.planning'),
            allowedRoles: ['admin']
          }
        }
      ],
      meta: {
        requiresAuth: true
      }
    },
    {
      path: '/templates',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        {
          path: '',
          name: 'templates',
          component: () => import('@/pages/Templates.vue'),
          meta: {
            title: i18n.t('router.titles.templates'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: 'new',
          name: 'templatenew',
          component: () => import('@/pages/TemplateNew.vue'),
          meta: {
            title: i18n.t('router.titles.new_template'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: 'duplicate',
          name: 'templateduplicate',
          component: () => import('@/pages/TemplateNew.vue'),
          meta: {
            title: i18n.t('router.titles.duplicate_template'),
            allowedRoles: ['admin', 'manager', 'advanced']
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
      component: () => import('@/views/Rdp.vue')
    },
    {
      path: '/deployments',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        {
          path: '',
          name: 'deployments',
          component: () => import('@/pages/Deployments.vue'),
          meta: {
            title: i18n.t('router.titles.deployment'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: 'new',
          name: 'deploymentsnew',
          component: () => import('@/pages/DeploymentNew.vue'),
          meta: {
            title: i18n.t('router.titles.new_deployment'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        }
      ],
      meta: {
        requiresAuth: true
      }
    },
    {
      path: '/deployment/:id',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        {
          path: '',
          name: 'deployment_desktops',
          component: () => import('@/pages/Deployment.vue'),
          meta: {
            title: i18n.t('router.titles.deployment'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: 'videowall',
          name: 'deployment_videowall',
          component: () => import('@/pages/DeploymentVideowall.vue'),
          meta: {
            title: i18n.t('router.titles.deployment_videowall'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: 'edit',
          name: 'deploymentEdit',
          component: () => import('@/pages/DeploymentEdit.vue'),
          meta: {
            title: i18n.t('router.titles.edit-deployment'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        }
      ],
      meta: {
        requiresAuth: true
      }
    },
    {
      path: '/profile',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        {
          path: ':action?',
          name: 'profile',
          component: () => import('@/pages/Profile.vue'),
          meta: {
            title: i18n.t('router.titles.profile'),
            allowedRoles: ['admin', 'manager', 'advanced', 'user']
          }
        }
      ],
      meta: {
        requiresAuth: true
      }
    },
    {
      path: '/media',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        {
          path: '',
          name: 'media',
          component: () => import('@/pages/Media.vue'),
          meta: {
            title: i18n.t('router.titles.media'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: 'new',
          name: 'medianew',
          component: () => import('@/pages/MediaNew.vue'),
          meta: {
            title: i18n.t('router.titles.new_media'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: 'desktop/new',
          name: 'newfrommedia',
          component: () => import('@/pages/NewFromMedia.vue'),
          meta: {
            title: i18n.t('router.titles.new_desktop'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        }
      ],
      meta: {
        requiresAuth: true
      }
    },
    {
      path: '/userstorage',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        {
          path: '',
          name: 'userstorage',
          component: () => import('@/pages/Storage.vue'),
          meta: {
            title: i18n.t('router.titles.storage'),
            allowedRoles: ['admin', 'manager', 'advanced', 'user']
          }
        }
      ],
      meta: {
        title: i18n.t('router.titles.storage'),
        requiresAuth: true
      }
    },
    {
      path: '/',
      name: 'RecycleBins',
      redirect: '/recycleBins',
      component: () => import('@/layouts/MainLayout.vue'),
      children: [
        {
          path: 'recycleBins',
          name: 'recycleBins',
          component: () => import('@/pages/RecycleBins.vue'),
          meta: {
            title: i18n.t('router.titles.recycleBin'),
            allowedRoles: ['admin', 'manager', 'advanced', 'user']
          }
        },
        {
          path: '/recyclebin/:id',
          name: 'recycleBin',
          component: () => import('@/pages/RecycleBin.vue'),
          meta: {
            title: i18n.t('router.titles.recycleBin'),
            allowedRoles: ['admin', 'manager', 'advanced', 'user']
          }
        }
      ],
      meta: {
        requiresAuth: true
      }
    },
    {
      path: '/reset-password',
      component: () => import('@/pages/ResetPassword.vue'),
      name: 'ResetPassword',
      meta: {
        title: i18n.t('router.titles.password'),
        requiresAuth: true
      }
    },
    {
      path: '/forgot-password',
      component: () => import('@/pages/ForgotPassword.vue'),
      name: 'ForgotPassword',
      meta: {
        title: i18n.t('router.titles.forgot-password')
      }
    },
    {
      path: '/verify-email',
      component: () => import('@/pages/VerifyEmail.vue'),
      name: 'VerifyEmail',
      meta: {
        title: i18n.t('router.titles.verify-email'),
        requiresAuth: true
      }
    },
    {
      path: '/disclaimer',
      component: () => import('@/pages/Disclaimer.vue'),
      name: 'Disclaimer',
      meta: {
        title: i18n.t('router.titles.disclaimer')
      }
    },
    {
      path: '/export-user',
      component: () => import('@/pages/ExportUser.vue'),
      name: 'ExportUser',
      meta: {
        title: i18n.t('router.titles.export-user')
      }
    },
    {
      path: '/error/:code',
      name: 'Error',
      component: () => import('@/views/Error.vue'),
      meta: {
        title: i18n.t('router.titles.error')
      }
    },
    {
      path: '*',
      name: 'NotFound',
      component: () => import('@/views/NotFound.vue'),
      meta: {
        title: i18n.t('router.titles.not_found')
      }
    },
    {
      path: '/maintenance',
      name: 'Maintenance',
      component: () => import('@/views/Maintenance.vue'),
      meta: {
        title: i18n.t('router.titles.maintenance')
      }
    },
    {
      path: '/vw/*',
      name: 'DirectViewer',
      component: () => import('@/views/DirectViewer.vue'),
      meta: {
        title: i18n.t('router.titles.direct_viewer')
      }
    }
  ],
  mode: 'history'
})

router.beforeEach(async (to, from, next) => {
  moment.locale(localStorage.language)
  document.title = to.meta.title ? `${appTitle} - ${to.meta.title}` : appTitle
  let session = store.getters.getSession
  if (to.matched.some((record) => record.meta.requiresAuth)) {
    // No session yet
    if (!session) {
      const authCookie = getCookie('authorization')
      if (!authCookie) {
        if (['VerifyEmail', 'ResetPassword'].includes(to.name)) {
          if (to.query.token) {
            next()
            return
          }
        }

        window.location.pathname = '/login'
        return
      }

      store.dispatch('loginSuccess', authCookie)
      return
    }

    const sessionData = jwtDecode(session)
    // Handle user registration
    if (sessionData.type === 'register') {
      window.location.pathname = '/register'
      return
    } else if (sessionData.type === 'category-select') {
      window.location.pathname = '/login'
      return
    }

    // TODO: The session might not be expired but it could be revoked
    if (Date.now() + store.getters.getTimeDrift > ((sessionData.exp - 30) * 1000)) {
      await store.dispatch('renew')
      session = store.getters.getSession
      if (session) {
        store.dispatch('saveNavigation', { url: to })
        next()
      } else {
        store.dispatch('logout')
      }
    } else {
      store.dispatch('saveNavigation', { url: to })
      store.dispatch('fetchUser')
      // Logged in without requirements
      if (!to.query.token && !sessionData.type) {
        if (
          to.meta.allowedRoles &&
          to.meta.allowedRoles.includes(store.getters.getUser.role_id)
        ) {
          store.dispatch('openSocket', {})
          if (isEmpty(store.getters.getConfig)) {
            store.dispatch('fetchConfig')
          }
          if (!store.getters.getMaxTime) {
            store.dispatch('fetchMaxTime')
          }
          next()
        } else {
          store.dispatch('saveNavigation', { url: from })
          next({ name: 'desktops' })
        }
        // Requires disclaimer acceptance, will be redirected
      } else if (
        to.name !== 'Disclaimer' &&
        ['disclaimer-acknowledgement-required'].includes(sessionData.type)
      ) {
        router.push({ name: 'Disclaimer' })
        // Requires email verification, will be redirected
      } else if (
        to.name !== 'VerifyEmail' &&
        ['email-verification-required', 'email-verification'].includes(
          sessionData.type
        )
      ) {
        router.push({ name: 'VerifyEmail' })
        // Requires password reset, will be redirected
      } else if (
        to.name !== 'ResetPassword' &&
        ['password-reset-required', 'password-reset'].includes(
          sessionData.type
        )
      ) {
        router.push({ name: 'ResetPassword' })
      } else {
        next()
      }
    }
  } else {
    if (
      to.name === 'Login' &&
      getCookie('authorization') &&
      jwtDecode(getCookie('authorization')).type === 'category-select'
    ) {
      window.location.pathname = '/'
    } else {
      store.dispatch('saveNavigation', { url: to })
      next()
    }
  }
})

export default router
