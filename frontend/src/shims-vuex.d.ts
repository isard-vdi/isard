import { ComponentCustomProperties } from 'vue';
import { Store } from 'vuex';
import { State } from './store';

declare module '@vue/runtime-core' {
  interface ComponentCustomProperties {
    $store: Store<State>;
  }
}
