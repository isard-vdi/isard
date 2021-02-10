import {
  createStore,
  Store as VuexStore,
  CommitOptions,
  DispatchOptions,
  createLogger
} from 'vuex';
import { State, state } from './state';
import { Mutations, mutations } from './mutations';
import { Actions, actions } from './actions';
import { Getters, getters } from './getters';

export type Store = Omit<
  VuexStore<State>,
  'getters' | 'commit' | 'dispatch'
> & {
  commit<K extends keyof Mutations, P extends Parameters<Mutations[K]>[1]>(
    key: K,
    payload: P,
    options?: CommitOptions
  ): ReturnType<Mutations[K]>;
} & {
  dispatch<K extends keyof Actions>(
    key: K,
    payload: Parameters<Actions[K]>[1],
    options?: DispatchOptions
  ): ReturnType<Actions[K]>;
} & {
  getters: {
    [K in keyof Getters]: ReturnType<Getters[K]>;
  };
};

export const store = createStore<State>({
  state,
  mutations,
  actions,
  getters,
  plugins: [createLogger()]
});

export function useStore() {
  return store as Store;
}
