// Theme
import 'primevue/resources/themes/saga-blue/theme.css';
// Core css
import 'primevue/resources/primevue.min.css';
// Icons
import 'primeicons/primeicons.css';
import 'primevue/resources/themes/bootstrap4-light-blue/theme.css';
import 'primeflex/primeflex.css';
import '@/assets/layout/layout.scss';

import App from './App.vue';
import AppLayout from '@/layouts/AppLayout.vue';
import Button from 'primevue/button';
import Calendar from 'primevue/calendar';
import Card from 'primevue/card';
import Column from 'primevue/column';
import DataTable from 'primevue/datatable';
import Dropdown from 'primevue/dropdown';
import InputText from 'primevue/inputtext';
import Panel from 'primevue/panel';
import PanelMenu from 'primevue/panelmenu';
import PrimeIcons from 'primevue/config';
import PrimeVue from 'primevue/config';
import RadioButton from 'primevue/radiobutton';
import Sidebar from 'primevue/sidebar';
import VueAxios from 'vue-axios';
import axios from 'axios';
import { createApp } from 'vue';
import i18n from '@/i18n';
import router from './router';
import { store } from './store';
import { ActionTypes } from './store/actions';
import { getCookie } from 'tiny-cookie';
import ConnectionService from './service/ConnectionService';

ConnectionService.setClientBackend();
const app = createApp(App);
app.use(store);
app.use(router);
app.use(i18n);
app.use(PrimeVue);
app.use(PrimeIcons);
app.use(VueAxios, axios);

app.component('AppLayout', AppLayout);
app.component('PanelMenu', PanelMenu);
app.component('RadioButton', RadioButton);
app.component('Panel', Panel);
app.component('Calendar', Calendar);
app.component('InputText', InputText);
app.component('Dropdown', Dropdown);
app.component('Button', Button);
app.component('Card', Card);
app.component('Sidebar', Sidebar);
app.component('DataTable', DataTable);
app.component('Column', Column);
app.mount('#app');

router.beforeEach((to, from, next) => {
  const loggedIn = store.getters.loginToken;
  const tokenCookie: string = getCookie('token') || '';
  console.log(
    to,
    `****** Token value: ${tokenCookie ? 'string' : 'es nulo'} *****`
  );

  const urlParts = to.fullPath.split('?');
  console.log(urlParts, 'urlParts');
  const url = urlParts[0];
  const urlParams = urlParts[1];

  const urlSegments = url.split('/');
  const toSection = urlSegments[1];

  if (!loggedIn) {
    if (tokenCookie && tokenCookie != 'null' && tokenCookie != '') {
      // Has token, check if it's valid or refresh!!!!!
      console.log('****** logged out y Hay token *****');
      store.dispatch(ActionTypes.REFRESH_TOKEN_FROM_SESSION, {
        token: tokenCookie
      });
      store
        .dispatch(ActionTypes.NAVIGATE, {
          section: toSection,
          url: toSection,
          queryParams: [],
          editmode: false
        })
        .then(() => next());
    } else if (to.meta.needsAuth) {
      // No token && needs auth
      console.log('No hay token!!!');
      router.push({ name: 'login' });
    } else {
      // no token && no auth
      console.log(to, '**** Open ****');
      store.dispatch(ActionTypes.NAVIGATE, {
        section: to.name,
        url: to.fullPath,
        queryParams: [],
        editmode: false
      });
      next();
    }
  } else {
    // logged in
    store.dispatch(ActionTypes.NAVIGATE, {
      section: to.name,
      url: to.fullPath,
      queryParams: [],
      editmode: false
    });
    next();
  }
});
