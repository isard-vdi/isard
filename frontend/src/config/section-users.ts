import { TABLE_PREFIX } from './constants';
import { SectionConfig } from './sections-config';

export const SectionUsers: SectionConfig = {
  name: 'users',
  baseUrl: '',
  query: {
    search: `
    query UsersList {
      ${TABLE_PREFIX}user {
        created_at
        email
        id
        name
        surname
        uuid
      }
    }`,
    detail: `query UserDetail($id: bigint) {
      ${TABLE_PREFIX}user(where: {id: {_eq: $id}}) {
        email
        name
        surname
        id
        uuid
        created_at
        ${TABLE_PREFIX}user_to_entities {
          ${TABLE_PREFIX}entity {
            id
            description
            created_at
            name
            uuid
          }
        }
      }
    }`,
    update: `
    mutation UpdateUser($id: bigint, $mail: String, $name: String) {
      update_${TABLE_PREFIX}user(where: {id: {_eq: $id}}, _set: {email: $mail, name: $name}) {
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
  },
  detail: 'User'
};
