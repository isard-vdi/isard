import { MutationTree } from 'vuex';
import { State } from './state';

export enum MutationTypes {
  LOAD_LIST_ITEMS = 'LOAD_LIST_ITEMS',
  LOGIN_SUCCESS = 'LOGIN',
  TOGGLE_MENU = 'TOGGLE_MENU',
  CHANGE_MENU_TYPE = 'CHANGE_MENU_TYPE',
  CHANGE_MENU_COLOR_MODE = 'CHANGE_MENU_COLOR_MODE',
  CHANGE_MENU_OVERLAY_ACTIVE = 'CHANGE_MENU_OVERLAY_ACTIVE',
  CHANGE_MENU_MOBILE_ACTIVE = 'CHANGE_MENU_MOBILE_ACTIVE',
  CHANGE_MENU_STATIC_INACTIVE = 'CHANGE_MENU_STATIC_INACTIVE'
}

export type Mutations<S = State> = {
  [MutationTypes.LOAD_LIST_ITEMS](state: S, payload: Types.User[]): void;
  [MutationTypes.LOGIN_SUCCESS](state: S, payload: { token: string }): void;
  [MutationTypes.TOGGLE_MENU](state: S, payload: {}): void;
  [MutationTypes.CHANGE_MENU_TYPE](state: S, payload: string): void;
  [MutationTypes.CHANGE_MENU_COLOR_MODE](state: S, payload: string): void;
  [MutationTypes.CHANGE_MENU_OVERLAY_ACTIVE](state: S, payload: boolean): void;
  [MutationTypes.CHANGE_MENU_MOBILE_ACTIVE](state: S, payload: boolean): void;
  [MutationTypes.CHANGE_MENU_STATIC_INACTIVE](state: S, payload: boolean): void;
};

export const mutations: MutationTree<State> & Mutations = {
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
  },
  [MutationTypes.TOGGLE_MENU](state: State, payload) {
    state.ui.menu.show = !state.ui.menu.show;
  },
  [MutationTypes.CHANGE_MENU_TYPE](state: State, payload) {
    state.ui.menu.type = payload;
  },
  [MutationTypes.CHANGE_MENU_COLOR_MODE](state: State, payload) {
    state.ui.menu.colorMode = payload;
  },
  [MutationTypes.CHANGE_MENU_OVERLAY_ACTIVE](state: State, payload) {
    state.ui.menu.overlayActive = payload;
  },
  [MutationTypes.CHANGE_MENU_MOBILE_ACTIVE](state: State, payload) {
    state.ui.menu.mobileActive = payload;
  },
  [MutationTypes.CHANGE_MENU_STATIC_INACTIVE](state: State, payload) {
    state.ui.menu.staticInactive = payload;
  }
};
