import { ActionContext, ActionTree } from 'vuex';
import { MutationTypes, Mutations } from './mutations';
import LoginService from '@/service/LoginService';
import SearchService from '@/service/SearchService';
import { State } from './state';
import router from '@/router';
import { store } from '.';
import { refreshClientToken } from '@/main';
import { sections } from '@/config/sections';
import { DEFAULT_PAGE } from '@/config/constants';

type AugmentedActionContext = {
  commit<K extends keyof Mutations>(
    key: K,
    payload: Parameters<Mutations[K]>[1]
  ): ReturnType<Mutations[K]>;
} & Omit<ActionContext<State, State>, 'commit'>;

/* Action Enum*/
export enum ActionTypes {
  DO_LOCAL_LOGIN = 'DO_LOCAL_LOGIN',
  REFRESH_CLIENT_TOKEN = 'REFRESH_CLIENT_TOKEN',
  NAVIGATE = 'NAVIGATE',
  DO_SEARCH = 'DO_SEARCH',
  GO_SEARCH = 'GO_SEARCH',
  TOGGLE_MENU = 'TOGGLE_MENU',
  CHANGE_MENU_TYPE = 'CHANGE_MENU_TYPE',
  CHANGE_MENU_COLOR_MODE = 'CHANGE_MENU_COLOR_MODE',
  CHANGE_MENU_OVERLAY_ACTIVE = 'CHANGE_MENU_OVERLAY_ACTIVE',
  CHANGE_MENU_MOBILE_ACTIVE = 'CHANGE_MENU_MOBILE_ACTIVE',
  CHANGE_MENU_STATIC_INACTIVE = 'CHANGE_MENU_STATIC_INACTIVE'
}

/* Action Types*/
export interface Actions {
  [ActionTypes.DO_LOCAL_LOGIN](
    { commit }: AugmentedActionContext,
    payload: { usr: string; psw: string; entity: string }
  ): void;

  [ActionTypes.DO_SEARCH](
    { commit }: AugmentedActionContext,
    payload: {
      queryParams: string[];
      size: number;
      start: number;
    }
  ): void;

  [ActionTypes.REFRESH_CLIENT_TOKEN](
    { commit }: AugmentedActionContext,
    payload: {
      token: string;
    }
  ): void;

  [ActionTypes.NAVIGATE](
    { commit }: AugmentedActionContext,
    payload: {
      section: string;
      url: string;
      queryParams: string[];
      editmode: boolean;
    }
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

  [ActionTypes.TOGGLE_MENU](
    { commit }: AugmentedActionContext,
    payload: {}
  ): void;

  [ActionTypes.CHANGE_MENU_TYPE](
    { commit }: AugmentedActionContext,
    payload: string
  ): void;

  [ActionTypes.CHANGE_MENU_COLOR_MODE](
    { commit }: AugmentedActionContext,
    payload: string
  ): void;

  [ActionTypes.CHANGE_MENU_OVERLAY_ACTIVE](
    { commit }: AugmentedActionContext,
    payload: boolean
  ): void;

  [ActionTypes.CHANGE_MENU_MOBILE_ACTIVE](
    { commit }: AugmentedActionContext,
    payload: boolean
  ): void;

  [ActionTypes.CHANGE_MENU_STATIC_INACTIVE](
    { commit }: AugmentedActionContext,
    payload: boolean
  ): void;
}

/****** ACTIONS ****/
export const actions: ActionTree<State, State> & Actions = {
  [ActionTypes.DO_LOCAL_LOGIN]({ commit }, payload) {
    LoginService.doLogin(
      payload.usr,
      payload.psw,
      'local',
      payload.entity
    ).then((response: any): any => {
      const payload = { token: response.login };

      store.dispatch(ActionTypes.REFRESH_CLIENT_TOKEN, payload);
      router.push({ name: DEFAULT_PAGE });
    });
  },

  [ActionTypes.REFRESH_CLIENT_TOKEN]({ commit }, payload) {
    refreshClientToken(payload.token);
    commit(MutationTypes.LOGIN_SUCCESS, payload);
  },

  [ActionTypes.DO_SEARCH]({ commit, getters }, payload) {
    const section: string = getters.section;
    const query: string = sections[section].config?.query.search;
    SearchService.listSearch(
      query,
      payload.queryParams,
      payload.size,
      payload.start
    ).then((response: any): any => {
      const sectionConfig = sections[section];

      commit(
        MutationTypes.LOAD_LIST_ITEMS,
        sectionConfig.search?.cleaner.parse(
          response[sectionConfig.search.apiSegment]
        )
      );
    });
  },

  [ActionTypes.GO_SEARCH]({ commit }, payload) {
    router.push({ name: payload.section });
  },

  [ActionTypes.NAVIGATE]({ commit }, payload) {
    commit(MutationTypes.CHANGE_SECTION, payload);
  },

  [ActionTypes.TOGGLE_MENU]({ commit }) {
    commit(MutationTypes.TOGGLE_MENU, {});
  },

  [ActionTypes.CHANGE_MENU_TYPE]({ commit }, payload: string) {
    commit(MutationTypes.CHANGE_MENU_TYPE, payload);
  },

  [ActionTypes.CHANGE_MENU_COLOR_MODE]({ commit }, payload: string) {
    commit(MutationTypes.CHANGE_MENU_COLOR_MODE, payload);
  },

  [ActionTypes.CHANGE_MENU_OVERLAY_ACTIVE]({ commit }, payload: boolean) {
    commit(MutationTypes.CHANGE_MENU_OVERLAY_ACTIVE, payload);
  },

  [ActionTypes.CHANGE_MENU_MOBILE_ACTIVE]({ commit }, payload: boolean) {
    commit(MutationTypes.CHANGE_MENU_MOBILE_ACTIVE, payload);
  },

  [ActionTypes.CHANGE_MENU_STATIC_INACTIVE]({ commit }, payload: boolean) {
    commit(MutationTypes.CHANGE_MENU_STATIC_INACTIVE, payload);
  }
};
