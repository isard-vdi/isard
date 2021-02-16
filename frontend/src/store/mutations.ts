import { MutationTree } from 'vuex';
import { State } from './state';

export enum MutationTypes {
  INC_COUNTER = 'SET_COUNTER',
  LOAD_LIST_ITEMS = 'LOAD_LIST_ITEMS',
  LOGIN_SUCCESS = 'LOGIN'
}

export type Mutations<S = State> = {
  [MutationTypes.INC_COUNTER](state: S, payload: number): void;
  [MutationTypes.LOAD_LIST_ITEMS](state: S, payload: Types.User[]): void;
  [MutationTypes.LOGIN_SUCCESS](state: S, payload: { token: string }): void;
};

export const mutations: MutationTree<State> & Mutations = {
  [MutationTypes.INC_COUNTER](state: State, payload) {
    state.counter += payload;
  },
  [MutationTypes.LOAD_LIST_ITEMS](state: State, payload) {
    state.search = payload;
  },
  [MutationTypes.LOGIN_SUCCESS](state: State, payload) {
    // state = {
    //   ...state,
    //   auth: { ...state.auth, token: payload.token, loggedIn: true }
    // };
    state.auth.token = payload.token;
    state.auth.loggedIn = true;
  }
};
