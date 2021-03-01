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
import { createClient, defaultPlugins, definePlugin } from 'villus';
import i18n from '@/i18n';
import router from './router';
import { store } from './store';
import { ActionTypes } from './store/actions';

// function authPlugin({ opContext }: { opContext: any }) {
//   opContext.headers.authorization = 'Bearer <token>';
// }

const authPluginWithConfig = (config: { token: string }) => {
  // opContext will be automatically typed
  return definePlugin(({ opContext }) => {
    // Add auth headers with configurable prefix
    opContext.headers.authorization = `${config.token}`;
  });
};

export let villusClient = createClient({
  url: 'http://192.168.129.125:1312/graphql', // To env file
  use: [...defaultPlugins()]
});

export const refreshClientToken = (token: string) => {
  villusClient = createClient({
    url: 'http://192.168.129.125:8080/v1/graphql', // To env file
    use: [authPluginWithConfig({ token }), ...defaultPlugins()]
  });
};

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
  if (to.meta.needsAuth && !loggedIn) {
    router.push({ name: 'login' });
  } else {
    store.dispatch(ActionTypes.NAVIGATE, {
      section: to.name,
      url: to.fullPath,
      queryParams: [],
      editmode: false
    });
    next();
  }
});
