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
    detail: ''
  },
  table: {
    columns: [{ field: 'name', header: 'Name' }]
  }
};
