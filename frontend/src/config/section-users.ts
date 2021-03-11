import { SectionConfig } from './sections-config';

export const SectionUsers: SectionConfig = {
  name: 'users',
  baseUrl: '',
  query: {
    search: `
    query UsersList {
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
    detail: `query UserDetail($id: bigint) {
      user(where: {id: {_eq: $id}}) {
        email
        id
        name
        surname
        entity {
          id
          name
          uuid
        }
      }
    }`
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
