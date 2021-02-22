import { SectionConfig } from './sections-config';

export const SectionUsers: SectionConfig = {
  name: 'users',
  baseUrl: '',
  query: {
    search: `
    query Users {
      user {
        created_at
        email
        id
        name
        surname
        username
        uuid
      }
    }`,
    detail: ''
  },
  table: {
    columns: [
      { field: 'name', header: 'Name' },
      { field: 'surname1', header: 'Surname' },
      { field: 'userName', header: 'Username' },
      { field: 'profile', header: 'Profile' }
    ]
  }
};
