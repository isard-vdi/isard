import { RouteRecordRaw, createRouter, createWebHistory } from 'vue-router';

const routes: Array<RouteRecordRaw> = [
  {
    path: '/',
    name: 'Root',
    component: () => import('@/components/Login.vue')
  },
  {
    path: '/login',
    name: 'login',
    component: () => import('@/components/Login.vue')
  },
  {
    path: '/admin',
    name: 'admin',
    component: () => import('@/components/Dashboard.vue'),
    meta: {
      layout: 'MainLayout',
      needsAuth: true
    }
  },
  {
    path: '/templates',
    name: 'templates',
    component: () => import('@/components/TemplatesList.vue'),
    meta: {
      layout: 'MainLayout',
      needsAuth: true
    }
  },
  {
    path: '/config',
    name: 'config',
    component: () => import('@/components/Configuration.vue'),
    meta: {
      layout: 'MainLayout',
      needsAuth: true
    }
  },
  {
    path: '/users',
    name: 'users',
    component: () => import('@/components/search/Search.vue'),
    meta: {
      layout: 'MainLayout',
      needsAuth: true
    }
  },
  {
    path: '/users/:id',
    name: 'users-detail',
    component: () => import('@/components/details/User.vue'),
    meta: {
      layout: 'MainLayout',
      needsAuth: true
    }
  },
  {
    path: '/entities',
    name: 'entities',
    component: () => import('@/components/search/Search.vue'),
    meta: {
      layout: 'MainLayout',
      needsAuth: true
    }
  },
  {
    path: '/entities/:id',
    name: 'entities-detail',
    component: () => import('@/components/details/Entity.vue'),
    meta: {
      layout: 'MainLayout',
      needsAuth: true
    }
  },
  {
    path: '/entity',
    name: 'Entity',
    component: () => import('@/components/Dashboard.vue'),
    meta: {
      layout: 'MainLayout',
      needsAuth: true
    }
  },
  {
    path: '/user',
    name: 'User',
    component: () => import('@/components/Desktops.vue'),
    meta: {
      layout: 'UserLayout',
      needsAuth: true
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
