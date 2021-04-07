export default class EntitiesUtils {
  static cleanEntities(items: any[]): Types.Entity[] {
    return items.map(
      (item: any): Types.Entity => {
        return {
          name: item.name,
          creationDate: item.created_at,
          uuid: item.uuid,
          id: item.id,
          description: item.description
        };
      }
    );
  }

  static detailCleaner(item: any): Types.Entity {
    const { isardvdi_user_to_entities } = item;

    const users =
      isardvdi_user_to_entities &&
      isardvdi_user_to_entities.length > 0 &&
      isardvdi_user_to_entities.map((itemEntity: any) => {
        return itemEntity.isardvdi_user;
      });

    return {
      description: item.description,
      name: item.name,
      creationDate: '',
      uuid: item.uuid,
      id: item.id,
      users
    };
  }
}
