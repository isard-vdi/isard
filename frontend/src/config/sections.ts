import { TABLE_PREFIX } from './constants';
import { SearchDesktopsParser } from './search-parsers/search-desktops-parser';
import { SearchEntitiesParser } from './search-parsers/search-entities-parser';
import { SearchUserParser } from './search-parsers/search-users-parser';
import { SectionDesktops } from './section-desktops';
import { SectionEntities } from './section-entities';
import { SectionUsers } from './section-users';
import { SectionModelMap } from './sections-config';

export const sections: SectionModelMap = {
  users: {
    config: SectionUsers,
    search: {
      cleaner: SearchUserParser,
      apiSegment: `${TABLE_PREFIX}user`
    }
  },
  entities: {
    config: SectionEntities,
    search: {
      cleaner: SearchEntitiesParser,
      apiSegment: `${TABLE_PREFIX}entity`
    }
  },
  desktops: {
    config: SectionDesktops,
    search: {
      cleaner: SearchDesktopsParser,
      apiSegment: `${TABLE_PREFIX}desktop`
    }
  }
};
