import { GetterTree } from 'vuex';
import { State } from './state';
import { cloneDeep } from 'lodash';

export type Getters = {
  loginToken(state: State): string;
  searchResults(state: State): any[];
  menuVisible(state: State): boolean;
  menuType(state: State): string;
  menuColorMode(state: State): string;
  menuStaticInactive(state: State): boolean;
  menuOverlayActive(state: State): boolean;
  menuMobileActive(state: State): boolean;
  section(state: State): string;
  detailForUpdate(state: State): any;
};

export const getters: GetterTree<State, State> & Getters = {
  loginToken: (state) => {
    return state.auth.token;
  },
  searchResults: (state) => {
    return state.search && state.search.map((item) => item);
  },
  menuVisible: (state) => {
    return state.ui.menu.show;
  },
  menuType: (state) => {
    return state.ui.menu.type;
  },
  menuColorMode: (state) => {
    return state.ui.menu.colorMode;
  },
  menuStaticInactive: (state) => {
    return state.ui.menu.staticInactive;
  },
  menuOverlayActive: (state) => {
    return state.ui.menu.overlayActive;
  },
  menuMobileActive: (state) => {
    return state.ui.menu.mobileActive;
  },
  section: (state) => {
    return state.router.section;
  },
  detailForUpdate: (state) => {
    return cloneDeep(state.detail);
  }
};
