export default class EntitiesUtils {
  static cleanEntities(items: any[]): Types.Entity[] {
    return items.map(
      (item: any): Types.Entity => {
        return {
          name: item.name,
          creationDate: '',
          uuid: item.uuid,
          id: ''
        };
      }
    );
  }
}
