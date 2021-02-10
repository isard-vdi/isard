import { MutationTree } from 'vuex';
import { State, User } from './state';

export enum MutationTypes {
  INC_COUNTER = 'SET_COUNTER',
  LOAD_LIST_ITEMS = 'LOAD_LIST_ITEMS'
}

export type Mutations<S = State> = {
  [MutationTypes.INC_COUNTER](state: S, payload: number): void;
  [MutationTypes.LOAD_LIST_ITEMS](state: S, payload: User[]): void;
};

export const mutations: MutationTree<State> & Mutations = {
  [MutationTypes.INC_COUNTER](state: State, payload: number) {
    state.counter += payload;
  },
  [MutationTypes.LOAD_LIST_ITEMS](state: State, payload: object[]) {
    state.search = payload;
  }
};
