import { getToken, useCookies } from '@/lib/auth'
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
    }
  ]
})

const cookies = useCookies()

router.beforeEach((to, from, next) => {
  if (to.matched.some((record) => record.meta.requiresAuth)) {
    const token = getToken(cookies)
    console.log('requiresAuth')
    console.log(token)
    if (!token?.type || token.type === 'login') {
      next()
    } else {
      next({ name: 'login' })
    }
  } else {
    next()
  }
})

export default router
