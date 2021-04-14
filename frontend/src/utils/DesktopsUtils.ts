export default class DesktopsUtils {
  static cleanDesktops(items: any[]): Types.Desktop[] {
    return items.map(
      (item: any): Types.Desktop => {
        return {
          name: item.name,
          creationDate: item.created_at,
          uuid: item.uuid,
          id: item.id,
          description: item.description,
          state: 'stopped' // item.state ? item.state : 'stopped'
        };
      }
    );
  }

  static detailCleaner(item: any): Types.Desktop {
    return {
      description: item.description,
      name: item.name,
      creationDate: '',
      uuid: item.uuid,
      id: item.id,
      state: 'stopped' // item.state ? item.state : 'stopped'
    };
  }
}
