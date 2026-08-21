import type { Preview } from '@storybook/vue3'
import { setup } from "@storybook/vue3";

import '../src/assets/index.css';

const preview: Preview = {
  parameters: {
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i
      }
    }
  }
}

import {i18n} from "../src/lib/i18n";
import {createMemoryHistory, createRouter} from "vue-router";

// Stories rendering router-aware components need a router instance
const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }]
});

setup((app) => {
  app.use(i18n);
  app.use(router);
});

export default preview
