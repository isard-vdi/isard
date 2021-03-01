import EntitiesUtils from '@/utils/EntitiesUtils';

export class SearchEntitiesParser {
  static parse(items: any[]) {
    return EntitiesUtils.cleanEntities(items);
  }
}
