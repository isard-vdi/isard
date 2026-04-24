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

setup((app) => {
  app.use(i18n);
});

export default preview
