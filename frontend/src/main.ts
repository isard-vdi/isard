// Theme
import "primevue/resources/themes/saga-blue/theme.css";
// Core css
import "primevue/resources/primevue.min.css";
// Icons
import "primeicons/primeicons.css";
import "primevue/resources/themes/bootstrap4-light-blue/theme.css";
import "primeflex/primeflex.css";

import App from "./App.vue";
import PrimeIcons from "primevue/config";
import PrimeVue from "primevue/config";
import { createApp } from "vue";
import router from "./router";
import store from "./store";

createApp(App)
  .use(store)
  .use(router)
  .use(PrimeVue)
  .use(PrimeIcons)
  .mount("#app");
