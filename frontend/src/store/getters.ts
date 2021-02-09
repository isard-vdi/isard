import { GetterTree } from 'vuex';
import { State, User } from './state';

export type Getters = {
  doubleCounter(state: State): number;
  searchResults(state: State): any[];
  // searchUsers(searchResults: any[]): any[];
};

export const getters: GetterTree<State, State> & Getters = {
  doubleCounter: (state) => {
    return state.counter * 2;
  },
  searchResults: (state) => {
    console.log(state.search[1]);
    return state.search.map((item) => item);
  }
  // searchUsers: (searchResults) => {
  //   return searchResults; //clean
  // }
};
