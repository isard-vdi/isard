import { TABLE_PREFIX } from './constants';
import { SectionConfig } from './sections-config';

export const SectionDesktops: SectionConfig = {
  name: 'desktops',
  baseUrl: '',
  query: {
    search: `
    query SearchDesktops {
      ${TABLE_PREFIX}desktop {
        id
        name
        uuid
        description
        created_at
      }
    }`,
    detail: `query DesktopDetail($id: bigint) {
      ${TABLE_PREFIX}desktop(where: {id: {_eq: $id}}) {
        created_at
        description
        id
        name
        uuid
        ${TABLE_PREFIX}entity {
          description
          id
          created_at
          name
          uuid
        }
        ${TABLE_PREFIX}hardware {
          id
          created_at
          base_id
        }
        ${TABLE_PREFIX}user {
          id
          name
          surname
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
    }`,
    create: `
    mutation CreateDesktop {
      desktopCreate(input: {hardware: {baseId: "c1iprlstdj5tchj3i7tg", memory: 1024, vcpus: 1}, name: "Test1xy"}) {
        recordId
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
  detail: 'Desktop',
  defaultValues: {
    id: '',
    name: 'default name',
    description: 'Defaul description',
    uuid: 'Def, UUID'
  }
};
