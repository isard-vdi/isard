import { store } from '@/store';
import { ActionTypes } from '@/store/actions';
import { getCookie } from 'tiny-cookie';
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
    component: () => import('@/components/search/Search.vue'),
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
    component: () => import('@/components/search/Search.vue'),
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

router.beforeEach((to, from, next) => {
  const loggedIn = store.getters.loginToken;
  const tokenCookie: string = getCookie('token') || '';
  const userIdCookie: string = getCookie('userId') || '';

  // Parse Url
  const urlParts = to.fullPath.split('?');
  const url = urlParts[0]; // Url without params
  const urlParams = urlParts[1]; // Params to use in search

  const urlSegments = url.split('/');
  const detailId = urlSegments.length > 2 ? urlSegments[2] : '';
  const section = urlSegments[1];

  if (store.getters.editMode) {
    store.dispatch(ActionTypes.END_EDIT_MODE);
  }

  if (to.meta.needsAuth) {
    if (!loggedIn) {
      console.log('*** Logged OUT ***');
      if (tokenCookie && tokenCookie != 'null' && tokenCookie != '') {
        // Has token, check if it's valid or refresh!!!!!
        console.log(to, '*** Has token ***');
        store
          .dispatch(ActionTypes.REFRESH_TOKEN_FROM_SESSION, {
            token: tokenCookie,
            userId: userIdCookie
          })
          .then(() => {
            if (detailId && detailId.length > 0) {
              store.dispatch(ActionTypes.GET_ITEM, {
                section,
                params: { id: detailId }
              });
            } else {
              store.dispatch(ActionTypes.NAVIGATE, {
                section,
                params: { id: detailId },
                url: to.name
              });
            }
          });
      } else {
        // No token && needs auth
        console.log('*** Logged OUT and NO Token ***');
        router.push({ name: 'login' });
      }
    } else {
      // logged in
      console.log(to, '***** Logged in *****');
      store.dispatch(ActionTypes.SET_NAVIGATION_DATA, {
        section,
        params: { id: detailId },
        url: to.path,
        queryParams: [],
        editmode: false
      });
      next();
    }
  } else {
    console.log(to, '**** Open ****');
    store.dispatch(ActionTypes.SET_NAVIGATION_DATA, {
      section: to.name,
      url: to.fullPath,
      queryParams: [],
      editmode: false
    });
    next();
  }
});

export default router;
