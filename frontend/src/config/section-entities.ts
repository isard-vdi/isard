import { SectionConfig } from './sections-config';

export const SectionEntities: SectionConfig = {
  name: 'entities',
  baseUrl: '',
  query: {
    search: `
    query Entities {
      entity {
        created_at
        id
        name
        uuid
      }
    }`,
    detail: `query EntityDetail($id: bigint) {
      entity(where: {id: {_eq: $id}}) {
        id
        name
        uuid
        users {
          name
          surname
          uuid
        }
      }
    }`
  },
  table: {
    columns: [
      { field: 'id', header: 'ID' },
      { field: 'uuid', header: 'UUID' },
      { field: 'name', header: 'Name' },
      { field: 'created_at', header: 'Created' }
    ]
  }
};
