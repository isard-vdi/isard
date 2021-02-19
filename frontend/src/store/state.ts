export interface State {
  counter: number;
  search: object[];
  auth: Auth;
  ui: Ui;
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

export const state: State = {
  counter: 0,
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
  }
};
