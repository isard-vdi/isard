import UserService from '@/service/UserService';
import { ActionContext, ActionTree } from 'vuex';
import { Mutations, MutationTypes } from './mutations';
import { State, User } from './state';

const userService = new UserService();

type AugmentedActionContext = {
  commit<K extends keyof Mutations>(
    key: K,
    payload: Parameters<Mutations[K]>[1]
  ): ReturnType<Mutations[K]>;
} & Omit<ActionContext<State, State>, 'commit'>;

export enum ActionTypes {
  INC_COUNTER = 'SET_COUNTER',
  DO_SEARCH = 'DO_SEARCH'
}

export interface Actions {
  [ActionTypes.INC_COUNTER](
    { commit }: AugmentedActionContext,
    payload: number
  ): void;
  [ActionTypes.DO_SEARCH](
    { commit }: AugmentedActionContext,
    payload: string
  ): void;
}

export const actions: ActionTree<State, State> & Actions = {
  [ActionTypes.INC_COUNTER]({ commit }, payload: number) {
    commit(MutationTypes.INC_COUNTER, payload);
  },
  [ActionTypes.DO_SEARCH]({ commit }, payload: string) {
    userService.getUsers().then((response: any): any => {
      commit(MutationTypes.LOAD_LIST_ITEMS, response);
    });
  }
};
