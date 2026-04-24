import { z } from 'zod'

const dateRe = /^\d{4}-\d{2}-\d{2}$/
const timeRe = /^\d{2}:\d{2}$/

export const bookingEventSchema = z
  .object({
    title: z.string().max(80),
    startDate: z.string().regex(dateRe, 'required'),
    startTime: z.string().regex(timeRe, 'required'),
    endDate: z.string().regex(dateRe, 'required'),
    endTime: z.string().regex(timeRe, 'required')
  })
  .superRefine((v, ctx) => {
    const start = new Date(`${v.startDate}T${v.startTime}`)
    const end = new Date(`${v.endDate}T${v.endTime}`)
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return
    const now = new Date()
    if (start < now) {
      ctx.addIssue({ path: ['startDate'], code: 'custom', message: 'past-booking' })
    }
    if (end <= start) {
      ctx.addIssue({ path: ['endDate'], code: 'custom', message: 'end-before-start' })
    }
    if ((end.getTime() - start.getTime()) / 60_000 < 5) {
      ctx.addIssue({ path: ['endTime'], code: 'custom', message: 'minimum-time' })
    }
  })

export type BookingEventInput = z.input<typeof bookingEventSchema>
