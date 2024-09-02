import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import { appTitle } from '@/shared/constants'
import { i18n } from '@/i18n'

const { t } = i18n.global

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
      meta: {title: t('router.titles.home')},
    },
    {
      path: '/login/:provider?/:category?',
      name: 'login',
      component: () => import('../views/LoginView.vue'),
      meta: {title: t('router.titles.login')},
    }
  ]
})

export default router

router.beforeEach((to) => {
  document.title = to.meta.title ? `${appTitle} - ${to.meta.title}` : appTitle
})