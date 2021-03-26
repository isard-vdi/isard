import { GetterTree } from 'vuex';
import { State } from './state';

export type Getters = {
  loginToken(state: State): string;
  searchResults(state: State): any[];
  menuType(state: State): string;
  menuColorMode(state: State): string;
  isMenuVisible(state: State): boolean;
  isMenuStaticActive(state: State): boolean;
  isMenuOverlayActive(state: State): boolean;
  isMenuMobileActive(state: State): boolean;
  section(state: State): string;
  detail(state: State): any;
  editMode(state: State): boolean;
  isLoading(state: State): boolean;
  createMode(state: State): boolean;
  routeName(state: State): string;
};

export const getters: GetterTree<State, State> & Getters = {
  loginToken: (state) => {
    return state.auth.token;
  },
  searchResults: (state) => {
    return state.search && state.search.map((item) => item);
  },
  menuType: (state) => {
    return state.ui.menu.type;
  },
  menuColorMode: (state) => {
    return state.ui.menu.colorMode;
  },
  isMenuVisible: (state) => {
    return state.ui.menu.show;
  },
  isMenuStaticActive: (state) => {
    return state.ui.menu.staticActive;
  },
  isMenuOverlayActive: (state) => {
    return state.ui.menu.overlayActive;
  },
  isMenuMobileActive: (state) => {
    return state.ui.menu.mobileActive;
  },
  section: (state) => {
    return state.router.section;
  },
  detail: (state) => {
    return state.detail;
  },
  editMode: (state) => {
    return state.ui.editMode;
  },
  isLoading: (state) => {
    return state.ui.isLoading;
  },
  createMode: (state) => {
    return state.ui.createMode;
  },
  routeName: (state) => {
    return state.router.routeName;
  }
};
