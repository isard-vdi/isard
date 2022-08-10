import store from '@/store/index.js'
import ErrorPage from '@/views/ErrorPage.vue'
import ExpiredSession from '@/views/ExpiredSession.vue'
import Login from '@/views/Login.vue'
import Maintenance from '@/views/Maintenance.vue'
import NotFound from '@/views/NotFound.vue'
import Register from '@/views/Register.vue'
import Rdp from '@/views/Rdp.vue'
import Deployments from '@/pages/Deployments.vue'
import DeploymentVideowall from '@/pages/DeploymentVideowall.vue'
import Deployment from '@/pages/Deployment.vue'
import DeploymentNew from '@/pages/DeploymentNew.vue'
import DirectViewer from '@/views/DirectViewer.vue'
import Vue from 'vue'
import VueRouter from 'vue-router'
import { auth, checkRdpToken } from './auth'
import MainLayout from '@/layouts/MainLayout.vue'
import Desktops from '@/pages/Desktops.vue'
import DesktopNew from '@/pages/DesktopNew.vue'
import { appTitle } from '../shared/constants'
import ImagesList from '@/views/ImagesList.vue'
import TemplateNew from '@/pages/TemplateNew.vue'
import Templates from '@/pages/Templates.vue'
import Booking from '@/pages/Booking'
import Planning from '@/pages/Planning'
import Profile from '@/pages/Profile.vue'
import Media from '@/pages/Media.vue'
import MediaNew from '@/pages/MediaNew.vue'
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
            title: i18n.t('router.titles.desktops')
          }
        },
        {
          path: 'desktops/new',
          name: 'desktopsnew',
          component: DesktopNew,
          meta: {
            title: i18n.t('router.titles.new_desktop')
          }
        },
        {
          path: 'images',
          name: 'images',
          component: ImagesList,
          meta: {
            title: i18n.t('router.titles.images')
          }
        },
        {
          path: 'booking',
          name: 'booking',
          component: Booking,
          meta: {
            title: i18n.t('router.titles.booking')
          }
        },
        {
          path: 'planning',
          name: 'Planning',
          component: Planning,
          meta: {
            title: i18n.t('router.titles.planning')
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
            title: i18n.t('router.titles.templates')
          }
        },
        {
          path: 'template/new',
          name: 'templatenew',
          component: TemplateNew,
          meta: {
            title: i18n.t('router.titles.new_template')
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
            title: i18n.t('router.titles.deployment')
          }
        },
        {
          path: 'deployments/new',
          name: 'deploymentsnew',
          component: DeploymentNew,
          meta: {
            title: i18n.t('router.titles.new_deployment')
          }
        },
        {
          path: '/deployment/videowall/:id',
          name: 'deployment_videowall',
          component: DeploymentVideowall,
          meta: {
            title: i18n.t('router.titles.deployment_videowall')
          }
        },
        {
          path: '/deployment/:id',
          name: 'deployment_desktops',
          component: Deployment,
          meta: {
            title: i18n.t('router.titles.deployment')
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
            title: i18n.t('router.titles.profile')
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
            title: i18n.t('router.titles.media')
          }
        },
        {
          path: 'media/new',
          name: 'medianew',
          component: MediaNew,
          meta: {
            title: i18n.t('router.titles.new_media')
          }
        }
      ],
      meta: {
        requiresAuth: true
      }
    },
    {
      path: '/login/:category?',
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
      component: ErrorPage,
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
      path: '/expired_session',
      name: 'ExpiredSession',
      component: ExpiredSession,
      meta: {
        title: i18n.t('router.titles.expired_session')
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
    auth(to, from, next)
  } else if (to.matched.some(record => record.meta.requiresRdpToken)) {
    checkRdpToken(to, from, next)
  } else {
    store.dispatch('saveNavigation', { url: to })
    next()
  }
})

export default router
