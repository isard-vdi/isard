export interface State {
  counter: number;
  search: object[];
  auth: Auth;
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
  }
};
