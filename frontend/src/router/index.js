import MainLayout from '@/layouts/MainLayout.vue'
import Booking from '@/pages/Booking'
import BookingsSummary from '@/pages/BookingsSummary'
import Deployment from '@/pages/Deployment.vue'
import DeploymentNew from '@/pages/DeploymentNew.vue'
import DeploymentEdit from '@/pages/DeploymentEdit.vue'
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
import RecycleBins from '@/pages/RecycleBins.vue'
import RecycleBin from '@/pages/RecycleBin.vue'
import ResetPassword from '@/pages/ResetPassword.vue'
import ForgotPassword from '@/pages/ForgotPassword.vue'
import VerifyEmail from '@/pages/VerifyEmail.vue'
import Vue from 'vue'
import VueRouter from 'vue-router'
import { appTitle } from '../shared/constants'
import { auth } from './auth'
import i18n from '@/i18n'
import moment from 'moment'

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
        }
      ],
      meta: {
        requiresAuth: true
      }
    },
    {
      path: '/domain',
      component: MainLayout,
      children: [
        {
          path: 'edit',
          name: 'domainedit',
          component: DomainEdit,
          meta: {
            title: i18n.t('router.titles.edit-domain'),
            allowedRoles: ['admin', 'manager', 'advanced', 'user']
          }
        }
      ]
    },
    {
      path: '/booking',
      component: MainLayout,
      children: [
        {
          path: ':type/:id',
          name: 'booking',
          component: Booking,
          meta: {
            title: i18n.t('router.titles.booking'),
            allowedRoles: ['admin', 'manager', 'advanced', 'user']
          }
        },
        {
          path: 'summary',
          name: 'bookingsummary',
          component: BookingsSummary,
          meta: {
            title: i18n.t('router.titles.booking'),
            allowedRoles: ['admin', 'manager', 'advanced', 'user']
          }
        }
      ]
    },
    {
      path: '/planning',
      component: MainLayout,
      children: [
        {
          path: '',
          name: 'Planning',
          component: Planning,
          meta: {
            title: i18n.t('router.titles.planning'),
            allowedRoles: ['admin']
          }
        }
      ]
    },
    {
      path: '/templates',
      component: MainLayout,
      children: [
        {
          path: '',
          name: 'templates',
          component: Templates,
          meta: {
            title: i18n.t('router.titles.templates'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: 'new',
          name: 'templatenew',
          component: TemplateNew,
          meta: {
            title: i18n.t('router.titles.new_template'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: 'duplicate',
          name: 'templateduplicate',
          component: TemplateNew,
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
      component: Rdp
    },
    {
      path: '/deployments',
      component: MainLayout,
      children: [
        {
          path: '',
          name: 'deployments',
          component: Deployments,
          meta: {
            title: i18n.t('router.titles.deployment'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: 'new',
          name: 'deploymentsnew',
          component: DeploymentNew,
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
      component: MainLayout,
      children: [
        {
          path: '',
          name: 'deployment_desktops',
          component: Deployment,
          meta: {
            title: i18n.t('router.titles.deployment'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: 'videowall',
          name: 'deployment_videowall',
          component: DeploymentVideowall,
          meta: {
            title: i18n.t('router.titles.deployment_videowall'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: 'edit',
          name: 'deploymentEdit',
          component: DeploymentEdit,
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
      component: MainLayout,
      children: [
        {
          path: ':action?',
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
      path: '/media',
      component: MainLayout,
      children: [
        {
          path: '',
          name: 'media',
          component: Media,
          meta: {
            title: i18n.t('router.titles.media'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: 'new',
          name: 'medianew',
          component: MediaNew,
          meta: {
            title: i18n.t('router.titles.new_media'),
            allowedRoles: ['admin', 'manager', 'advanced']
          }
        },
        {
          path: 'desktop/new',
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
      path: '/userstorage',
      component: MainLayout,
      children: [
        {
          path: '',
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
      path: '/',
      name: 'RecycleBins',
      redirect: '/recycleBins',
      component: MainLayout,
      children: [
        {
          path: 'recycleBins',
          name: 'recycleBins',
          component: RecycleBins,
          meta: {
            title: i18n.t('router.titles.recycleBin'),
            allowedRoles: ['admin', 'manager', 'advanced', 'user']
          }
        },
        {
          path: '/recyclebin/:id',
          name: 'recycleBin',
          component: RecycleBin,
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
      component: ResetPassword,
      name: 'ResetPassword',
      meta: {
        title: i18n.t('router.titles.password')
      }
    },
    {
      path: '/forgot-password',
      component: ForgotPassword,
      name: 'ForgotPassword',
      meta: {
        title: i18n.t('router.titles.forgot-password')
      }
    },
    {
      path: '/verify-email',
      component: VerifyEmail,
      name: 'VerifyEmail',
      meta: {
        title: i18n.t('router.titles.verify-email')
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
  moment.locale(localStorage.language)
  document.title = to.meta.title ? `${appTitle} - ${to.meta.title}` : appTitle

  if (to.matched.some(record => record.meta.requiresAuth)) {
    auth(to, from, next, to.meta.allowedRoles)
  } else {
    store.dispatch('saveNavigation', { url: to })
    next()
  }
})

export default router
