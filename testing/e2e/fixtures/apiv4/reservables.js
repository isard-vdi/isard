// Reservable-domain teardown registration (priority entries, GPU items).
// No create factories yet — specs create these through the UI today.

import { deletePriority, deleteReservableItem } from '../../src/gen/apiv4/sdk.gen'
import { registerResource } from './resources.js'

registerResource('priority-id', {
  order: 40,
  delete: (client, id) => deletePriority({ client, path: { priority_id: id } }),
})
registerResource('gpu-id', {
  order: 50,
  delete: (client, id) =>
    deleteReservableItem({ client, path: { reservable_type: 'gpus', item_id: id } }),
})
