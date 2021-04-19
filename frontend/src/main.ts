// Theme
import 'primevue/resources/themes/saga-blue/theme.css';
// Core css
import 'primevue/resources/primevue.min.css';
// Icons
import 'primeicons/primeicons.css';
import 'primevue/resources/themes/bootstrap4-light-blue/theme.css';
import 'primeflex/primeflex.css';
import '@/assets/layout/layout.scss';

import App from '@/App.vue';
import PrimeIcons from 'primevue/config';
import PrimeVue from 'primevue/config';
import Tooltip from 'primevue/tooltip';
import VueAxios from 'vue-axios';
import axios from 'axios';
import { createApp } from 'vue';
import i18n from '@/i18n';
import router from '@/router';
import { store } from '@/store';
import ConnectionService from '@/service/ConnectionService';

ConnectionService.setClientBackend();
const app = createApp(App);
app.use(store);
app.use(router);
app.use(i18n);
app.use(PrimeVue);
app.use(PrimeIcons);
app.use(VueAxios, axios);

// Workaround for bug https://github.com/primefaces/primevue/issues/877 not fixed in 3.3.5
// eslint-disable-next-line
// @ts-ignore
app.directive('Tooltip', Tooltip);

app.mount('#app');
