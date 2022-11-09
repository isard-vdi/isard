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
    const { id, category_name: categoryName, name } = group
    return {
      id,
      label: `${name}[${categoryName}]`,
      categoryName,
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

  static parseItems (items) {
    if (items) {
      return items.map((item) => {
        return AllowedUtils.parseItem(item)
      }) || []
    } else {
      return []
    }
  }

  static parseItem (media) {
    const { id, name } = media
    return {
      id,
      label: name,
      name
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
  },
  isos: {
    parser: AllowedUtils.parseItems,
    mutations: {
      set: 'setIsos',
      setSelected: 'setSelectedIsos'
    }
  },
  floppies: {
    parser: AllowedUtils.parseItems,
    mutations: {
      set: 'setFloppies',
      setSelected: 'setSelectedFloppies'
    }
  }
}
