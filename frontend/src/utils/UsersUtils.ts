export default class UsersUtils {
  static cleanUsers(items: any[]): Types.User[] {
    console.log(items, 'Items****');

    return items.map(
      (item: any): Types.User => {
        return {
          name: item.name,
          surname1: item.surname,
          email: '',
          surname2: '',
          state: '',
          organizationId: '',
          roles: [],
          lastAttempt: '',
          creationDate: '',
          uuid: item.uuid,
          id: item.id,
          avatar: '',
          profile: ''
        };
      }
    );
  }

  static detailCleaner(item: any): Types.User {
    const { isardvdi_user_to_entities } = item;

    const entities =
      isardvdi_user_to_entities &&
      isardvdi_user_to_entities.length > 0 &&
      isardvdi_user_to_entities.map((item: any) => {
        return item.isardvdi_entity;
      });

    return {
      // userName: item.username,
      name: item.name,
      surname1: item.surname,
      email: '',
      surname2: '',
      state: '',
      organizationId: '',
      roles: [],
      lastAttempt: '',
      creationDate: '',
      uuid: item.uuid,
      id: item.id,
      avatar: '',
      profile: '',
      entities
    };
  }
}
