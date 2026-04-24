import { TokenType, type Role } from '@/lib/auth'
import { createRouter, createWebHistory } from 'vue-router'
import { MainLayout } from '@/layouts/main'
import { useAuthStore } from '@/stores/auth'
import { useSessionStore } from '@/stores/session'
import { useSocketStore } from '@/stores/socket'
import { getUserConfigApiV4ItemUserGetConfigGet } from '@/gen/oas/apiv4'
import { resolveVue2Path, type FrontendMode } from '@/lib/frontendModeMap'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/frontend',
      name: 'root',
      redirect: { name: 'desktops' },
      component: MainLayout,
      children: [
        {
          path: 'desktops',
          name: 'desktops-root',
          meta: {
            allowedTokenTypes: ['login'],
            allowedRoles: ['admin', 'manager', 'advanced', 'user'] as Role[]
          },
          children: [
            {
              path: '',
              name: 'desktops',
              component: () => import('../views/DesktopsView.vue'),
              meta: {
                title: 'router.desktops.title',
                subtitle: 'router.desktops.subtitle',
                showMountainBg: true
              },
              children: [
                {
                  path: ':desktopId/:action(desktop-created|desktop-updated)',
                  name: 'single-desktop',
                  component: () => import('../views/DesktopsView.vue'),
                  meta: {
                    showCloudsBg: true,
                    showDotsBg: true
                  }
                }
              ]
            },
            {
              path: 'new',
              name: 'new-desktop',
              component: () => import('../views/NewDesktopView.vue'),
              meta: {
                title: 'router.desktops.new.title',
                subtitle: 'router.desktops.new.subtitle'
              }
            },
            {
              path: 'edit/:desktopId',
              name: 'edit-desktop',
              component: () => import('../views/EditDesktopView.vue'),
              meta: {
                title: 'router.desktops.edit.title',
                subtitle: 'router.desktops.edit.subtitle'
              }
            }
          ]
        },
        {
          path: 'templates',
          name: 'templates-root',
          meta: {
            allowedTokenTypes: ['login'],
            allowedRoles: ['admin', 'manager', 'advanced'] as Role[],
            hideMountainBg: true
          },
          children: [
            {
              path: '',
              name: 'templates',
              component: () => import('../views/TemplatesView.vue'),
              meta: {
                title: 'router.templates.title',
                subtitle: 'router.templates.subtitle'
              }
            },
            {
              path: 'new/:desktopId?',
              name: 'new-template',
              meta: {
                title: 'router.templates.new.title',
                subtitle: 'router.templates.new.subtitle'
              },
              component: () => import('../views/NewTemplateView.vue')
            },
            {
              path: 'edit/:templateId',
              name: 'edit-template',
              component: () => import('../views/EditTemplateView.vue'),
              meta: {
                title: 'router.templates.edit.title',
                subtitle: 'router.templates.edit.subtitle'
              }
            },
            {
              path: 'duplicate',
              name: 'duplicate-template-root',
              meta: {
                title: 'router.templates.duplicate.title',
                subtitle: 'router.templates.duplicate.subtitle'
              },
              redirect: { name: 'templates' },
              children: [
                {
                  path: ':templateId',
                  name: 'duplicate-template',
                  component: () => import('../views/DuplicateTemplateFormView.vue')
                }
              ]
            }
          ]
        },
        {
          path: 'recycle-bin',
          name: 'recycle-bin-root',
          meta: {
            allowedTokenTypes: ['login'],
            allowedRoles: ['admin', 'manager', 'advanced', 'user'] as Role[]
          },
          children: [
            {
              path: '',
              name: 'recycle-bin',
              component: () => import('../views/RecycleBinView.vue'),
              meta: {
                title: 'router.recycle-bin.title',
                subtitle: 'router.recycle-bin.subtitle'
              }
            },
            {
              path: ':recycleBinId',
              name: 'recycle-bin-entry',
              component: () => import('../views/RecycleBinEntryView.vue'),
              meta: {
                title: 'router.recycle-bin.entry.title',
                subtitle: 'router.recycle-bin.entry.subtitle'
              }
            }
          ]
        },
        {
          path: 'profile',
          name: 'profile',
          component: () => import('../views/ProfileView.vue'),
          meta: {
            title: 'router.profile.title',
            subtitle: 'router.profile.subtitle',
            hideMountainBg: true,
            allowedTokenTypes: ['login'] as TokenType[],
            allowedRoles: ['admin', 'manager', 'advanced', 'user'] as Role[]
          }
        },
        {
          path: 'media',
          name: 'media-root',
          meta: {
            allowedTokenTypes: ['login'],
            allowedRoles: ['advanced', 'manager', 'admin'] as Role[]
          },
          children: [
            {
              path: '',
              name: 'media',
              component: () => import('../views/MediaView.vue'),
              meta: {
                title: 'router.media.title',
                subtitle: 'router.media.subtitle'
              }
            }
          ]
        },
        {
          path: 'deployments',
          name: 'deployments-root',
          meta: {
            allowedTokenTypes: ['login'],
            allowedRoles: ['admin', 'manager', 'advanced'] as Role[]
          },
          children: [
            {
              path: '',
              name: 'deployments',
              component: () => import('../views/DeploymentsView.vue'),
              meta: {
                title: 'router.deployments.title',
                subtitle: 'router.deployments.subtitle'
              }
            },
            {
              path: 'shared',
              name: 'shared-deployments',
              component: () => import('../views/SharedDeploymentsView.vue'),
              meta: {
                title: 'router.shared-deployments.title',
                subtitle: 'router.shared-deployments.subtitle',
                allowedRoles: ['user', 'advanced', 'manager', 'admin'] as Role[]
              }
            },
            {
              path: 'new',
              name: 'new-deployment',
              meta: {
                title: 'router.deployments.new.title',
                subtitle: 'router.deployments.new.subtitle'
              },
              component: () => import('../views/NewDeploymentView.vue')
            },
            {
              path: ':deploymentId',
              name: 'deployment',
              component: () => import('../views/DeploymentView.vue'),
              meta: {
                title: 'router.deployment.title',
                subtitle: 'router.deployment.subtitle'
              }
            }
          ]
        },
        {
          path: 'bookings',
          name: 'bookings-root',
          meta: {
            allowedTokenTypes: ['login'],
            allowedRoles: ['admin', 'manager', 'advanced', 'user'] as Role[]
          },
          children: [
            {
              path: 'summary',
              name: 'booking-summary',
              component: () => import('../views/booking/BookingSummaryView.vue'),
              meta: {
                title: 'router.bookings.summary.title',
                subtitle: 'router.bookings.summary.subtitle'
              }
            },
            {
              path: ':type(desktop|deployment)/:id',
              name: 'booking',
              component: () => import('../views/booking/BookingView.vue'),
              meta: {
                title: 'router.bookings.item.title',
                subtitle: 'router.bookings.item.subtitle'
              }
            }
          ]
        },
        {
          path: 'planning',
          name: 'planning-root',
          meta: {
            allowedTokenTypes: ['login'],
            allowedRoles: ['admin'] as Role[]
          },
          children: [
            {
              path: '',
              name: 'planning',
              component: () => import('../views/planning/PlanningView.vue'),
              meta: {
                title: 'router.planning.title',
                subtitle: 'router.planning.subtitle'
              }
            }
          ]
        }
      ]
    },
    {
      path: '/login/:provider?/:category?',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { title: 'router.login.title', public: true }
    },
    {
      path: '/migration',
      name: 'migration',
      component: () => import('../views/MigrationView.vue'),
      meta: {
        title: 'router.migration.title',
        allowedTokenTypes: ['login', 'migration'],
        allowedRoles: ['admin', 'manager', 'advanced', 'user'] as Role[]
      }
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('../views/RegisterView.vue'),
      meta: {
        title: 'router.register.title',
        allowedTokenTypes: ['register'],
        allowedRoles: ['admin', 'manager', 'advanced', 'user'] as Role[]
      }
    },
    {
      path: '/maintenance',
      name: 'maintenance',
      component: () => import('../views/MaintenanceView.vue'),
      meta: { title: 'router.maintenance.title' }
    },
    {
      path: '/notifications/:trigger',
      name: 'notifications',
      component: () => import('../views/NotificationsView.vue'),
      meta: {
        title: 'router.notifications.title',
        allowedTokenTypes: ['login'],
        allowedRoles: ['admin', 'manager', 'advanced', 'user'] as Role[]
      }
    },
    {
      path: '/verify-email',
      name: 'verify-email',
      component: () => import('../views/EmailVerificationView.vue'),
      meta: {
        title: 'router.verify-email.title',
        allowedTokenTypes: ['email-verification-required', 'email-verification']
      }
    }
  ]
})

let cachedFrontendMode: FrontendMode | null = null

async function getFrontendMode(): Promise<FrontendMode> {
  if (cachedFrontendMode) return cachedFrontendMode
  try {
    const { data } = await getUserConfigApiV4ItemUserGetConfigGet()
    const mode = (data as { frontend_mode?: FrontendMode } | undefined)?.frontend_mode
    cachedFrontendMode = mode ?? 'deprecated'
  } catch {
    cachedFrontendMode = 'deprecated'
  }
  return cachedFrontendMode
}

router.beforeEach(async (to, from, next) => {
  const isPublic = to.meta.public
  if (isPublic) {
    return next()
  }

  const authStore = useAuthStore()
  const sessionStore = useSessionStore()
  const allowedTokenTypes = to.meta.allowedTokenTypes as TokenType | undefined
  const allowedRoles = to.meta.allowedRoles as Role | undefined

  const { token, tokenType, user } = authStore

  if (!token || !tokenType) {
    return next({ name: 'login' })
  }

  if (allowedTokenTypes && !allowedTokenTypes.includes(tokenType)) {
    return next(getRedirectForTokenType(tokenType))
  }

  if (
    tokenType === TokenType.Login &&
    allowedRoles &&
    (!user?.role_id || !allowedRoles.includes(user?.role_id))
  ) {
    // TODO: Use a new error page
    window.location.pathname = '/error/403'
  }

  if (tokenType === TokenType.Login && to.path.startsWith('/frontend')) {
    const mode = await getFrontendMode()
    if (mode === 'deprecated') {
      const vue2Path = resolveVue2Path(to) ?? '/'
      window.location.assign(vue2Path)
      return
    }
  }

  // Renew the session 1 minute before it expires
  const now = Date.now()
  const adjustedNow =
    now + (Math.abs(sessionStore.timeDrift) < 24 * 60 * 60 * 1000 ? sessionStore.timeDrift : 0) // 24h in ms

  if (
    authStore.sessionId !== 'isardvdi-service' &&
    authStore.claims &&
    authStore.claims.exp &&
    adjustedNow > authStore.claims.exp * 1000 - 60000
  ) {
    // Await the renew: otherwise socketStore.connectWithToken() below runs
    // with the soon-to-expire token and the server rejects the handshake
    // with 401 Token expired. createSocket() now reads the token from the
    // auth store at each reconnect, so once renewSession() has written the
    // new token we're good to connect.
    try {
      await authStore.renewSession()
    } catch (e) {
      console.warn('The session was expired and could not be renewed:', e)
      console.error(e)
      authStore.logout()
      return next({ name: 'login' })
    }
  }

  const socketStore = useSocketStore()
  if (!socketStore.isConnected) {
    socketStore.connectWithToken()
  }

  return next()
})

/**
 * Get the redirect route based on the token type.
 * @param type - The type of the token.
 * @returns The route object to redirect to.
 */
function getRedirectForTokenType(type: TokenType) {
  switch (type) {
    case TokenType.Login:
      return { name: 'home' }
    case TokenType.CategorySelect:
      return { name: 'login' }
    case TokenType.Register:
      return { name: 'register' }
    case TokenType.DisclaimerAcknowledgeRequired:
      // TODO: Use a new disclaimer page
      return (window.location.pathname = '/disclaimer')
    case TokenType.PasswordResetRequired:
    case TokenType.PasswordReset:
      // TODO: Use a new password reset page
      return (window.location.pathname = '/reset-password')
    case TokenType.EmailVerificationRequired:
      return { name: 'verify-email' }
    case TokenType.UserMigrationRequired:
      // TODO: Use a new export user page
      return (window.location.pathname = '/export-user')
    case TokenType.UserMigration:
      return { name: 'migration' }
    default:
      return { name: 'home' }
  }
}

export default router
