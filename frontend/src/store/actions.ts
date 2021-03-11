import { ActionContext, ActionTree } from 'vuex';
import { MutationTypes, Mutations } from './mutations';
import LoginService from '@/service/LoginService';
import SearchService from '@/service/SearchService';
import { State } from './state';
import router from '@/router';
import { store } from '.';
import { sections } from '@/config/sections';
import { DEFAULT_PAGE } from '@/config/constants';
import { remove, setCookie } from 'tiny-cookie';
import ConnectionService from '@/service/ConnectionService';

type AugmentedActionContext = {
  commit<K extends keyof Mutations>(
    key: K,
    payload: Parameters<Mutations[K]>[1]
  ): ReturnType<Mutations[K]>;
} & Omit<ActionContext<State, State>, 'commit'>;

/* Action Enum*/
export enum ActionTypes {
  DO_LOCAL_LOGIN = 'DO_LOCAL_LOGIN',
  DO_LOGOUT = 'DO_LOGOUT',
  REFRESH_CLIENT_TOKEN = 'REFRESH_CLIENT_TOKEN',
  REFRESH_TOKEN_FROM_SESSION = 'REFRESH_TOKEN_FROM_SESSION',
  SET_NAVIGATION_DATA = 'SET_NAVIGATION_DATA',
  NAVIGATE = 'NAVIGATE',
  DO_SEARCH = 'DO_SEARCH',
  GO_SEARCH = 'GO_SEARCH',
  GET_ITEM = 'GET_ITEM',
  TOGGLE_MENU = 'TOGGLE_MENU',
  CHANGE_MENU_TYPE = 'CHANGE_MENU_TYPE',
  CHANGE_MENU_COLOR_MODE = 'CHANGE_MENU_COLOR_MODE',
  CHANGE_MENU_OVERLAY_ACTIVE = 'CHANGE_MENU_OVERLAY_ACTIVE',
  CHANGE_MENU_MOBILE_ACTIVE = 'CHANGE_MENU_MOBILE_ACTIVE',
  CHANGE_MENU_STATIC_ACTIVE = 'CHANGE_MENU_STATIC_ACTIVE'
}

/* Action Types*/
export interface Actions {
  [ActionTypes.DO_LOCAL_LOGIN](
    { commit }: AugmentedActionContext,
    payload: { usr: string; psw: string; entity: string }
  ): void;

  [ActionTypes.REFRESH_TOKEN_FROM_SESSION](
    { commit }: AugmentedActionContext,
    payload: { token: string; userId: string }
  ): void;

  [ActionTypes.DO_LOGOUT](
    { commit }: AugmentedActionContext,
    payload: {}
  ): void;

  [ActionTypes.DO_SEARCH](
    { commit }: AugmentedActionContext,
    payload: {
      queryParams: string[];
      size: number;
      start: number;
      section?: string;
    }
  ): void;

  [ActionTypes.REFRESH_CLIENT_TOKEN](
    { commit }: AugmentedActionContext,
    payload: {
      token: string;
      userId: string;
    }
  ): void;

  [ActionTypes.SET_NAVIGATION_DATA](
    { commit }: AugmentedActionContext,
    payload: {
      section: string;
      url: string;
      queryParams: string[];
      editmode: boolean;
    }
  ): void;

  [ActionTypes.NAVIGATE](
    { commit }: AugmentedActionContext,
    payload: {
      section: string;
      params: any;
      url: string;
      queryParams: string[];
      editMode: boolean;
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

  [ActionTypes.GET_ITEM](
    { commit }: AugmentedActionContext,
    payload: {
      section: string;
      params: any;
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

  [ActionTypes.CHANGE_MENU_STATIC_ACTIVE](
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
      console.log(response);
      const payload = {
        token: response.login.token,
        userId: response.login.id
      };

      store.dispatch(ActionTypes.REFRESH_CLIENT_TOKEN, payload);
      router.push({ name: DEFAULT_PAGE });
    });
  },

  [ActionTypes.REFRESH_TOKEN_FROM_SESSION]({ commit }, payload) {
    ConnectionService.setClientHasura(payload.token);
    commit(MutationTypes.SET_LOGIN_DATA, payload);
  },

  [ActionTypes.DO_LOGOUT]({ commit }, payload) {
    ConnectionService.setClientBackend();
    remove('token');
    commit(MutationTypes.LOGOUT, payload);
    router.push({ name: 'login' });
  },

  [ActionTypes.REFRESH_CLIENT_TOKEN]({ commit }, payload) {
    ConnectionService.setClientHasura(payload.token);
    setCookie('token', payload.token, { expires: '1h' });
    setCookie('userId', payload.userId, { expires: '1h' });
    commit(MutationTypes.SET_LOGIN_DATA, payload);
  },

  [ActionTypes.DO_SEARCH]({ commit, getters }, payload) {
    const section: string = getters.section ? getters.section : payload.section;
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

  [ActionTypes.GET_ITEM]({ commit, getters }, payload) {
    const section: string = getters.section ? getters.section : payload.section;
    const query: string = sections[section].config?.query.detail;
    SearchService.detailSearch(query, payload.params).then(
      (response: any): any => {
        const dataItem =
          (response && response[Object.keys(response)[0]][0]) || {};
        commit(MutationTypes.GET_ITEM, dataItem);
        router.push({ name: `${section}-detail`, params: payload.params });
      }
    );
  },

  [ActionTypes.GO_SEARCH]({ commit }, payload) {
    router.push({ name: payload.section });
  },

  [ActionTypes.SET_NAVIGATION_DATA]({ commit }, payload) {
    const namedUrl = payload.section;
    const section =
      namedUrl.indexOf('-') > -1 ? namedUrl.split('-')[0] : namedUrl;

    commit(MutationTypes.SET_NAVIGATION_DATA, {
      section
    });
  },

  [ActionTypes.NAVIGATE]({ commit }, payload) {
    const { section, params, queryParams, editMode, url } = payload;
    console.log(url, 'url');
    commit(MutationTypes.SET_NAVIGATION_DATA, { section });
    router.push({ name: url, params });
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

  [ActionTypes.CHANGE_MENU_STATIC_ACTIVE]({ commit }, payload: boolean) {
    commit(MutationTypes.CHANGE_MENU_STATIC_ACTIVE, payload);
  }
};
