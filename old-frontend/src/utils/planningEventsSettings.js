// Managers with delegated GPU plannings get the same calendar interactions as
// admins (drag/click to create, click to edit) on their delegated cards.
export const planningEventsSettings = {
  eventClickActive: {
    admin: {
      month: true,
      week: true,
      day: true
    },
    manager: {
      month: true,
      week: true,
      day: true
    }
  },
  cellDoubleClickActive: {
    admin: {
      month: false,
      week: true,
      day: true
    },
    manager: {
      month: false,
      week: true,
      day: true
    }
  },
  cellDragActive: {
    admin: {
      month: false,
      week: true,
      day: true
    },
    manager: {
      month: false,
      week: true,
      day: true
    }
  },
  showAvailabilitySplit: {
    admin: {
      month: false,
      week: false,
      day: false
    },
    manager: {
      month: false,
      week: false,
      day: false
    }
  }
}
