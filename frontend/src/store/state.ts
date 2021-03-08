import { Router } from 'vue-router';

export interface State {
  search: object[];
  auth: Auth;
  ui: Ui;
  router: RouterState;
  detail?: any;
}

export interface Ui {
  menu: {
    show: boolean;
    type: string;
    colorMode: string;
    staticInactive: boolean;
    overlayActive: boolean;
    mobileActive: boolean;
  };
}

export interface Auth {
  user: Types.User;
  token: string;
  loggedIn: boolean;
}

export interface RouterState {
  layout: string;
  section: string;
  queryParams: string[];
}

export const state: State = {
  search: [
    {
      name: 'Test',
      surname1: 'surname',
      surname2: 'surname2',
      profile: 'admin'
    },
    {
      name: 'OtroTest',
      surname1: 'Otro surname',
      surname2: 'otro surname2',
      profile: 'manager'
    }
  ],
  auth: {
    user: {
      userName: '',
      email: '',
      name: '',
      surname1: '',
      surname2: '',
      status: '',
      organizationId: '',
      roles: [],
      lastAttempt: '',
      creationDate: '',
      uuid: '',
      id: '',
      avatar: '',
      profile: ''
    },
    token: '',
    loggedIn: false
  },
  ui: {
    menu: {
      show: true,
      type: 'static',
      colorMode: 'dark',
      staticInactive: false,
      overlayActive: false,
      mobileActive: false
    }
  },
  router: {
    layout: '',
    section: '',
    queryParams: []
  }
};
