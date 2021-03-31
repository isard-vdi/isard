import { ROUTE_CREATE, ROUTE_DETAIL } from '@/config/constants';
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
    path: '/config',
    name: 'config',
    component: () => import('@/components/Configuration.vue'),
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
    component: () => import('@/views/About.vue'),
    meta: {
      layout: 'UserLayout',
      needsAuth: true
    }
  },
  {
    path: '/:section',
    name: 'search',
    component: () => import('@/components/search/Search.vue'),
    meta: {
      layout: 'MainLayout',
      needsAuth: true
    }
  },
  {
    path: '/:section/:id(\\d+)', // only numeric ids
    name: 'detail',
    component: () => import('@/components/details/Detail.vue'),
    meta: {
      layout: 'MainLayout',
      needsAuth: true
    }
  },
  {
    path: '/:section/new',
    name: 'create',
    component: () => import('@/components/details/Detail.vue'),
    meta: {
      layout: 'MainLayout',
      needsAuth: true
    }
  },
  {
    path: '/about',
    name: 'About',
    // route level code-splitting
    // this generates a separate chunk (about.[hash].js) for this route
    // which is lazy-loaded when the route is visited.
    component: () => import(/* webpackChunkName: 'about' */ '@/views/About.vue')
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

  console.log(to, 'RouteObject beforeEach');
  // Parse Url
  const urlParts = to.fullPath.split('?');
  const url = urlParts[0]; // Url without params
  const urlParams = urlParts[1]; // Params to use in search

  const urlSegments = url.split('/');
  const detailId = urlSegments.length > 2 ? urlSegments[2] : '';
  const section = urlSegments[1];

  store.dispatch(ActionTypes.SET_NAVIGATION_DATA, {
    routeName: to.name,
    section
  });

  if (store.getters.editMode) {
    store.dispatch(ActionTypes.END_EDIT_MODE);
  }

  if (store.getters.createMode && to.name !== 'create') {
    store.dispatch(ActionTypes.END_CREATE_MODE);
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
            if (to.name === ROUTE_DETAIL) {
              store
                .dispatch(ActionTypes.GET_ITEM, {
                  name: ROUTE_DETAIL,
                  params: { id: detailId },
                  section
                })
                .then(() => {
                  next();
                });
            } else if (to.name === ROUTE_CREATE) {
              store
                .dispatch(ActionTypes.GO_CREATE_MODE, {
                  section,
                  routeName: to.name,
                  params: { section },
                  url: to.path,
                  queryParams: [],
                  editmode: false
                })
                .then(() => {
                  next();
                });
            } else {
              next();
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
