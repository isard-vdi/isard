import { computed } from 'vue'
import { useCookies as useAuthCookies, getBearer } from '../lib/auth'
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: import('../views/HomeView.vue'),
      meta: { title: 'router.titles.home' }
    },
    {
      path: '/login/:provider?/:category?',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: { title: 'router.titles.login' }
    },
    {
      path: '/migration',
      name: 'migration',
      component: () => import('../views/MigrationView.vue'),
      meta: { title: 'router.titles.migration', requiresAuth: true }
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('../views/RegisterView.vue'),
      meta: { title: 'router.titles.register' }
    },
    {
      path: '/maintenance',
      name: 'maintenance',
      component: () => import('../views/MaintenanceView.vue'),
      meta: { title: 'router.titles.maintenance' }
    },
    {
      path: '/notifications/:trigger',
      name: 'notifications',
      component: () => import('../views/NotificationsView.vue'),
      meta: { title: 'router.titles.notifications', requiresAuth: true }
    }
  ]
})

const cookies = useAuthCookies()
const token = computed(() => getBearer(cookies))

router.beforeEach((to, from, next) => {
  if (to.matched.some((record) => record.meta.requiresAuth)) {
    if (!token.value || !token.value || token.value === 'login') {
      next({ name: 'login' })
    } else {
      next()
    }
  } else {
    next()
  }
})

export default router
