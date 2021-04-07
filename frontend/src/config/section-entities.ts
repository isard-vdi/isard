import { TABLE_PREFIX } from './constants';
import { SectionConfig } from './sections-config';

export const SectionEntities: SectionConfig = {
  name: 'entities',
  baseUrl: '',
  query: {
    search: `
    query Entities {
      ${TABLE_PREFIX}entity {
        id
        created_at
        name
        uuid
        description
      }
    }`,
    detail: `query EntityDetail($id: bigint) {
      ${TABLE_PREFIX}entity(where: {id: {_eq: $id}}) {
        created_at
        description
        id
        name
        uuid
        ${TABLE_PREFIX}user_to_entities {
          ${TABLE_PREFIX}user {
            created_at
            email
            id
            name
            surname
            uuid
          }
        }
      }
    }`,
    update: `
    mutation UpdateEntity($id: bigint, $description: String, $name: String) {
      update_${TABLE_PREFIX}entity(where: {id: {_eq: $id}}, _set: {description: $description, name: $name}) {
        returning {
          id
        }
      }
    }
    `,
    create: `
    mutation CreateEntity($description: String, $name: String, $uuid: String) {
      insert_${TABLE_PREFIX}entity(objects: {name: $name, description: $description, uuid: $uuid}) {
        returning {
          id
        }
      }
    }
    `
  },
  table: {
    columns: [
      { field: 'id', header: 'ID' },
      { field: 'uuid', header: 'UUID' },
      { field: 'name', header: 'Name' },
      { field: 'description', header: 'Description' },
      { field: 'creationDate', header: 'Created' }
    ]
  },
  detail: 'Entity',
  defaultValues: { id: '', name: 'default name', description: '', uuid: '' }
};
