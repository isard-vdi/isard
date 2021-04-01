import { SectionConfig } from './sections-config';

export const SectionEntities: SectionConfig = {
  name: 'entities',
  baseUrl: '',
  query: {
    search: `
    query Entities {
      entity {
        id
        created_at
        name
        uuid
        description
      }
    }`,
    detail: `query EntityDetail($id: bigint) {
      entity(where: {id: {_eq: $id}}) {
        id
        name
        uuid
        users {
          name
          uuid
        }
      }
    }`,
    update: `
    mutation UpdateEntity($id: bigint, $description: String, $name: String) {
      update_entity(where: {id: {_eq: $id}}, _set: {description: $description, name: $name}) {
        returning {
          id
        }
      }
    }
    `,
    create: `
    mutation CreateEntity($description: String, $name: String, $uuid: String) {
      insert_entity(objects: {name: $name, description: $description, uuid: $uuid}) {
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
      { field: 'creationdate', header: 'Created' }
    ]
  },
  detail: 'Entity',
  defaultValues: { id: '', name: 'default name', description: '', uuid: '' }
};
