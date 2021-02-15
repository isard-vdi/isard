import UserService from '@/service/UserService';
import SearchService from '@/service/SearchService';
import { ActionContext, ActionTree } from 'vuex';
import { Mutations, MutationTypes } from './mutations';
import { State } from './state';
import UsersUtils from '@/utils/UsersUtils';
import router from '@/router';
import LoginService from '@/service/LoginService';
import { store } from '.';

const loginService = new LoginService();
const searchService = new SearchService();

type AugmentedActionContext = {
  commit<K extends keyof Mutations>(
    key: K,
    payload: Parameters<Mutations[K]>[1]
  ): ReturnType<Mutations[K]>;
} & Omit<ActionContext<State, State>, 'commit'>;

/* Action Enum*/

export enum ActionTypes {
  DO_LOCAL_LOGIN = 'DO_LOCAL_LOGIN',
  INC_COUNTER = 'SET_COUNTER',
  DO_SEARCH = 'DO_SEARCH',
  GO_SEARCH = 'GO_SEARCH'
}

/* Action Types*/
export interface Actions {
  [ActionTypes.DO_LOCAL_LOGIN](
    { commit }: AugmentedActionContext,
    payload: { usr: string; psw: string; entity: string }
  ): void;

  [ActionTypes.INC_COUNTER](
    { commit }: AugmentedActionContext,
    payload: number
  ): void;

  [ActionTypes.DO_SEARCH](
    { commit }: AugmentedActionContext,
    payload: { section: string; query: string; queryParams: string[] }
  ): void;

  [ActionTypes.GO_SEARCH](
    { commit }: AugmentedActionContext,
    payload: {
      section: string;
      url: string;
      queryParams: string[];
      editmode: boolean;
    }
  ): void;
}

/****** ACTIONS ****/
export const actions: ActionTree<State, State> & Actions = {
  [ActionTypes.DO_LOCAL_LOGIN]({ commit }, payload) {
    loginService
      .doLogin(payload.usr, payload.psw, 'local', payload.entity)
      .then((response: any): any => {
        const payload = { token: response };
        commit(MutationTypes.LOGIN_SUCCESS, payload);
        console.log('go users');
        router.push({ name: 'users-list' });
      });
  },

  [ActionTypes.INC_COUNTER]({ commit }, payload: number) {
    commit(MutationTypes.INC_COUNTER, payload);
  },

  [ActionTypes.DO_SEARCH]({ commit }, payload) {
    searchService
      .listSearch(payload.section, payload.query, payload.queryParams)
      .then((response: any): any => {
        commit(MutationTypes.LOAD_LIST_ITEMS, UsersUtils.cleanUsers(response));
      });
  },

  [ActionTypes.GO_SEARCH]({ commit }) {
    router.push({ name: 'users-list' });
  }
};
