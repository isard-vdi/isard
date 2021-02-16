import { GetterTree } from 'vuex';
import { State } from './state';

export type Getters = {
  loginToken(state: State): string;
  doubleCounter(state: State): number;
  searchResults(state: State): any[];
};

export const getters: GetterTree<State, State> & Getters = {
  loginToken: (state) => {
    return state.auth.token;
  },
  doubleCounter: (state) => {
    return state.counter * 2;
  },
  searchResults: (state) => {
    console.log(state.search && state.search.length > 0 && state.search[1]);
    return state.search && state.search.map((item) => item);
  }
};
