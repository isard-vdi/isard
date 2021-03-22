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
    }`,
    update: `
    mutation UpdateMutation($id: bigint, $mail: String, $name: String) {
      update_user(where: {id: {_eq: $id}}, _set: {email: $mail, name: $name}) {
        returning {
          id
        }
      }
    }
    `
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
