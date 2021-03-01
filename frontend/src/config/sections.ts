import { SearchEntitiesParser } from './search-parsers/search-entities-parser';
import { SearchUserParser } from './search-parsers/search-users-parser';
import { SectionEntities } from './section-entities';
import { SectionUsers } from './section-users';
import { SectionModelMap } from './sections-config';

export const sections: SectionModelMap = {
  users: {
    config: SectionUsers,
    search: {
      cleaner: SearchUserParser
    }
  },
  entities: {
    config: SectionEntities,
    search: {
      cleaner: SearchEntitiesParser
    }
  }
};
