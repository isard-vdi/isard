import { RouteRecordRaw, createRouter, createWebHistory } from 'vue-router';

const routes: Array<RouteRecordRaw> = [
  {
    path: '/',
    name: 'Login',
    component: () => import('@/components/Login.vue')
  },
  {
    path: '/admin',
    name: 'Admin',
    component: () => import('@/components/Dashboard.vue'),
    meta: {
      layout: 'MainLayout'
    }
  },
  {
    path: '/entity',
    name: 'Entity',
    component: () => import('@/components/Dashboard.vue'),
    meta: {
      layout: 'EntityLayout'
    }
  },
  {
    path: '/user',
    name: 'User',
    component: () => import('@/components/Desktops.vue'),
    meta: {
      layout: 'UserLayout'
    }
  },
  {
    path: '/about',
    name: 'About',
    // route level code-splitting
    // this generates a separate chunk (about.[hash].js) for this route
    // which is lazy-loaded when the route is visited.
    component: () =>
      import(/* webpackChunkName: 'about' */ '../views/About.vue')
  }
];

const router = createRouter({
  history: createWebHistory(process.env.BASE_URL),
  routes
});

export default router;
