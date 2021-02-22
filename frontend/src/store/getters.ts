import { GetterTree } from 'vuex';
import { State } from './state';

export type Getters = {
  loginToken(state: State): string;
  searchResults(state: State): any[];
  menuVisible(state: State): boolean;
  menuType(state: State): string;
  menuColorMode(state: State): string;
  menuStaticInactive(state: State): boolean;
  menuOverlayActive(state: State): boolean;
  menuMobileActive(state: State): boolean;
};

export const getters: GetterTree<State, State> & Getters = {
  loginToken: (state) => {
    return state.auth.token;
  },
  searchResults: (state) => {
    console.log(state.search && state.search.length > 0 && state.search[1]);
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
  }
};
