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
import AppLayout from '@/views/AppLayout.vue';
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
import Tooltip from 'primevue/tooltip';
import VueAxios from 'vue-axios';
import axios from 'axios';
import { createApp } from 'vue';
import i18n from '@/i18n';
import router from './router';
import { store } from './store';
import ConnectionService from './service/ConnectionService';
import IsardInputText from '@/components/shared/forms/IsardInputText.vue';
import IsardButton from '@/components/shared/forms/IsardButton.vue';

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
app.component('IsardInputText', IsardInputText);
app.component('IsardButton', IsardButton);

// Workaround for bug https://github.com/primefaces/primevue/issues/877 not fixed in 3.3.5
// eslint-disable-next-line
// @ts-ignore
app.directive('Tooltip', Tooltip);

app.mount('#app');
