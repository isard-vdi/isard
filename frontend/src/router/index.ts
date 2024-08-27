import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView
    },
    {
      path: '/login/:provider?/:category?',
      name: 'login',
      component: () => import('../views/LoginView.vue')
    }
  ]
})

export default router
