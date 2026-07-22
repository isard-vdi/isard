// Booking/plan-domain helpers: create+track factories, including the
// workaround for apiv4's empty-body createPlan response.

import {
  createBookingEvent,
  createPlan,
  deleteBookingEvent,
  deletePlan,
  listAllPlans,
} from '../../src/gen/apiv4/sdk.gen'
import { unwrap } from './unwrap.js'
import { registerResource, track } from './resources.js'

registerResource('booking-id', {
  order: 10,
  delete: (client, id) => deleteBookingEvent({ client, path: { booking_id: id } }),
})
registerResource('plan-id', {
  order: 20,
  delete: (client, id) => deletePlan({ client, path: { plan_id: id } }),
})

export async function createBookingAndTrack(client, testInfo, body) {
  const created = await unwrap(createBookingEvent({ client, body }))
  if (!created?.id) throw new Error('createBookingEvent: no id in response')
  track(testInfo, 'booking-id', created.id)
  return created
}

export async function createPlanAndTrack(client, testInfo, body) {
  const created = await unwrap(createPlan({ client, body }))
  if (created?.id) {
    track(testInfo, 'plan-id', created.id)
    return created
  }
  // apiv4 returns `{}` for response_model=dict (the str id is dropped during
  // Pydantic serialization) — recover by signature; day-granularity start
  // absorbs the backend's tz/precision normalization.
  const list = (await unwrap(listAllPlans({ client })).catch(() => [])) || []
  const dayKey = (s) => new Date(s).toISOString().slice(0, 10)
  const targetDay = dayKey(body.start)
  const match = list.find(
    (p) =>
      p.item_id === body.item_id &&
      p.subitem_id === body.subitem_id &&
      p.item_type === body.item_type &&
      dayKey(p.start) === targetDay,
  )
  if (!match?.id) {
    throw new Error(
      'createPlan: empty body and no matching plan in listAllPlans (sig: ' +
        JSON.stringify({
          item_id: body.item_id,
          subitem_id: body.subitem_id,
          item_type: body.item_type,
          start: body.start,
        }) +
        ')',
    )
  }
  track(testInfo, 'plan-id', match.id)
  return match
}
