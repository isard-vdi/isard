export class AllowedUtils {
  static parseAllowed (table, items) {
    return tablesConfig[table].parser(items)
  }

  static parseGroups (items) {
    return items.map((item) => {
      return AllowedUtils.parseGroup(item)
    }) || []
  }

  static parseGroup (group) {
    const { id, parent_category: parentCategory, name } = group
    return {
      id,
      label: `${name}[${parentCategory}]`,
      parentCategory,
      name
    }
  }

  static parseUsers (items) {
    return items.map((item) => {
      return AllowedUtils.parseUser(item)
    }) || []
  }

  static parseUser (user) {
    const { id, name, uid } = user
    return {
      id,
      label: `${name}[${uid}]`,
      name,
      uid
    }
  }
}

export const tablesConfig = {
  groups: {
    parser: AllowedUtils.parseGroups,
    mutations: {
      set: 'setGroups',
      setSelected: 'setSelectedGroups'
    }
  },
  users: {
    parser: AllowedUtils.parseUsers,
    mutations: {
      set: 'setUsers',
      setSelected: 'setSelectedUsers'
    }
  }
}
