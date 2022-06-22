export class AllowedUtils {
  static parseAllowed (table, items) {
    return tablesConfig[table].parser(items)
  }

  static parseGroups (items) {
    if (items) {
      return items.map((item) => {
        return AllowedUtils.parseGroup(item)
      }) || []
    } else {
      return []
    }
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
    if (items) {
      return items.map((item) => {
        return AllowedUtils.parseUser(item)
      }) || []
    } else {
      return []
    }
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
      setSelected: 'setSelectedGroups',
      setChecked: 'setGroupsChecked'
    }
  },
  users: {
    parser: AllowedUtils.parseUsers,
    mutations: {
      set: 'setUsers',
      setSelected: 'setSelectedUsers',
      setChecked: 'setUsersChecked'
    }
  }
}
