import MainLayout from '@/layouts/MainLayout.vue'
import Booking from '@/pages/Booking'
import BookingsSummary from '@/pages/BookingsSummary'
import Deployment from '@/pages/Deployment.vue'
import DeploymentNew from '@/pages/DeploymentNew.vue'
import Deployments from '@/pages/Deployments.vue'
import DeploymentVideowall from '@/pages/DeploymentVideowall.vue'
import DomainEdit from '@/pages/DomainEdit.vue'
import DesktopNew from '@/pages/DesktopNew.vue'
import Desktops from '@/pages/Desktops.vue'
import Media from '@/pages/Media.vue'
import MediaNew from '@/pages/MediaNew.vue'
import NewFromMedia from '@/pages/NewFromMedia.vue'
import Planning from '@/pages/Planning'
import Profile from '@/pages/Profile.vue'
import TemplateNew from '@/pages/TemplateNew.vue'
import Templates from '@/pages/Templates.vue'
import store from '@/store/index.js'
import DirectViewer from '@/views/DirectViewer.vue'
import Error from '@/views/Error.vue'
import Login from '@/views/Login.vue'
import Maintenance from '@/views/Maintenance.vue'
import NotFound from '@/views/NotFound.vue'
import Rdp from '@/views/Rdp.vue'
import Register from '@/views/Register.vue'
import Storage from '@/pages/Storage.vue'
import Vue from 'vue'
import VueRouter from 'vue-router'
import { appTitle } from '../shared/constants'
import { auth, checkRdpToken } from './auth'
import i18n from '@/i18n'

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
            title: i18n.t('router.titles.desktops'),
            allowedRoles: ['admin', 'manager', 'advanced', 'user']
          }
        },
        {
          path: 'desktops/new',
          name: 'desktopsnew',
          component: DesktopNew,
          meta: {
            title: i18n.t('router.titles.new_desktop'),
            allowedRoles: ['admin', 'manager', 'advanced', 'user']
          }
        },
        {
          path: 'domain/edit',
          name: 'domainedit',
          component: DomainEdit,
          meta: {
            title: i18n.t('router.titles.edit-domain'),
            allowedRoles: ['admin', 'manager', 'advanced', 'user']
          }
        },
        {
          path: 'booking',
          name: 'booking',
          component: Booking,
          meta: {
            title: i18n.t('router.titles.booking'),
            allowedRoles: ['admin', 'manager', 'advanced', 'user']
          }
        },
        {
          path: 'booking/summary',
          name: 'bookingsummary',
          component: BookingsSummary,
          meta: {
            title: i18n.t('router.titles.booking'),
            allowedRoles: ['admin', 'manager', 'advanced', 'user']
          }
        },
        {
          path: 'planning',
          name: 'Planning',
          component: Planning,
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
      path: '/',
      name: 'Templates',
      redirect: '/templates',
      component: MainLayout,
      children: [
        {
          path: 'templates',
          name: 'templates',
          component: Templates,
          meta: {
            title: i18n.t('router.titles.templates'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: 'template/new',
          name: 'templatenew',
          component: TemplateNew,
          meta: {
            title: i18n.t('router.titles.new_template'),
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
      component: Rdp,
      meta: {
        requiresRdpToken: true
      }
    },
    {
      path: '/',
      name: 'Deployments',
      component: MainLayout,
      children: [
        {
          path: 'deployments',
          name: 'deployments',
          component: Deployments,
          meta: {
            title: i18n.t('router.titles.deployment'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: 'deployments/new',
          name: 'deploymentsnew',
          component: DeploymentNew,
          meta: {
            title: i18n.t('router.titles.new_deployment'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: '/deployment/videowall/:id',
          name: 'deployment_videowall',
          component: DeploymentVideowall,
          meta: {
            title: i18n.t('router.titles.deployment_videowall'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: '/deployment/:id',
          name: 'deployment_desktops',
          component: Deployment,
          meta: {
            title: i18n.t('router.titles.deployment'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        }
      ],
      meta: {
        requiresAuth: true
      }
    },
    {
      path: '/',
      name: 'Profile',
      redirect: '/profile',
      component: MainLayout,
      children: [
        {
          path: 'profile',
          name: 'profile',
          component: Profile,
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
      path: '/',
      name: 'Media',
      redirect: '/media',
      component: MainLayout,
      children: [
        {
          path: 'media',
          name: 'media',
          component: Media,
          meta: {
            title: i18n.t('router.titles.media'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: 'media/new',
          name: 'medianew',
          component: MediaNew,
          meta: {
            title: i18n.t('router.titles.new_media'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: 'media/desktop/new',
          name: 'newfrommedia',
          component: NewFromMedia,
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
      path: '/',
      name: 'Storage',
      redirect: '/userstorage',
      component: MainLayout,
      children: [
        {
          path: 'userstorage',
          name: 'userstorage',
          component: Storage,
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
      path: '/login/:customUrlName?',
      name: 'Login',
      component: Login,
      meta: {
        title: i18n.t('router.titles.login')
      }
    },
    {
      path: '/register',
      name: 'Register',
      component: Register,
      meta: {
        title: i18n.t('router.titles.register')
      }
    },
    {
      path: '/error/:code',
      name: 'Error',
      component: Error,
      meta: {
        title: i18n.t('router.titles.error')
      }
    },
    {
      path: '*',
      name: 'NotFound',
      component: NotFound,
      meta: {
        title: i18n.t('router.titles.not_found')
      }
    },
    {
      path: '/maintenance',
      name: 'Maintenance',
      component: Maintenance,
      meta: {
        title: i18n.t('router.titles.maintenance')
      }
    },
    {
      path: '/vw/*',
      name: 'DirectViewer',
      component: DirectViewer,
      meta: {
        title: i18n.t('router.titles.direct_viewer')
      }
    }
  ],
  mode: 'history'
})

router.beforeEach((to, from, next) => {
  document.title = to.meta.title ? `${appTitle} - ${to.meta.title}` : appTitle

  if (to.matched.some(record => record.meta.requiresAuth)) {
    auth(to, from, next, to.meta.allowedRoles)
  } else if (to.matched.some(record => record.meta.requiresRdpToken)) {
    checkRdpToken(to, from, next)
  } else {
    store.dispatch('saveNavigation', { url: to })
    next()
  }
})

export default router
