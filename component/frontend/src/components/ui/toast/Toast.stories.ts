import { type Meta, type StoryObj } from '@storybook/vue3-vite'
import { h } from 'vue'
import { Toast, Toaster, toast } from '@/components/ui/toast'
import type { ToastEntry, ToastType } from '@/components/ui/toast'
import { Button } from '@/components/ui/button'

const ICON_BY_TYPE: Record<ToastType, string | undefined> = {
  default: undefined,
  success: 'check-circle',
  info: 'info-circle',
  warning: 'alert-triangle',
  error: 'x-circle',
  loading: undefined
}

/** Build a static entry for presentational stories (sticky, so the timer never fires). */
const makeEntry = (entry: Partial<ToastEntry> = {}): ToastEntry => ({
  id: entry.id ?? 'story',
  type: entry.type ?? 'default',
  message: entry.message,
  description: entry.description,
  icon: 'icon' in entry ? entry.icon : ICON_BY_TYPE[entry.type ?? 'default'],
  component: entry.component,
  componentProps: entry.componentProps,
  actions: entry.actions ?? [],
  closeButton: entry.closeButton,
  duration: entry.duration ?? Infinity,
  class: entry.class
})

const meta: Meta<typeof Toast> = {
  component: Toast,
  title: 'UI/Toast',
  tags: ['autodocs']
}

export default meta

type Story = StoryObj<typeof meta>

const single = (entry: Partial<ToastEntry>, closeButton = false): Story => ({
  render: () => ({
    components: { Toast },
    setup: () => ({ entry: makeEntry(entry), closeButton }),
    template: `<Toast :toast="entry" :close-button="closeButton" />`
  })
})

export const Default = single({ message: 'Event has been created' })
export const Success = single({ type: 'success', message: 'Changes saved' })
export const Info = single({ type: 'info', message: 'A new update is available' })
export const Warning = single({ type: 'warning', message: 'Your session expires soon' })
export const Error = single({ type: 'error', message: 'Failed to save changes' })
export const Loading = single({ type: 'loading', message: 'Loading…' })

export const WithDescription = single({
  type: 'success',
  message: 'Changes saved',
  description: 'Your desktop configuration was updated successfully.'
})

export const WithActions = single({
  message: 'Event has been created',
  description: 'You can undo this action.',
  actions: [
    { label: 'Undo', onClick: () => console.log('Undo') },
    { label: 'View', hierarchy: 'link-color', onClick: () => console.log('View') }
  ]
})

export const WithCloseButton = single(
  { type: 'info', message: 'Dismiss me with the X button' },
  true
)

export const CustomBody = single({
  closeButton: true,
  component: () =>
    h('div', { class: 'flex flex-col gap-1' }, [
      h('p', { class: 'text-sm font-semibold text-gray-warm-800' }, 'Custom toast body'),
      h(
        'p',
        { class: 'text-sm text-gray-warm-600' },
        'Rendered from a render function via toast.custom().'
      )
    ])
})

/** Interactive demo exercising the real singleton queue, timers and transitions. */
export const Playground: Story = {
  render: () => ({
    components: { Button, Toaster },
    setup() {
      const slowPromise = () => new Promise((resolve) => setTimeout(resolve, 2000))
      return {
        toastDefault: () => toast('Event has been created'),
        toastSuccess: () => toast.success('Changes saved'),
        toastInfo: () => toast.info('A new update is available'),
        toastWarning: () => toast.warning('Your session expires soon'),
        toastError: () => toast.error('Failed to save changes', { closeButton: true }),
        toastPromise: () =>
          toast.promise(slowPromise(), {
            loading: 'Loading…',
            success: () => 'Promise toast has been added',
            error: () => 'Error'
          }),
        // No explicit duration: actionable toasts are sticky by default.
        toastAction: () =>
          toast('Event has been created', {
            actions: [{ label: 'Undo', onClick: () => console.log('Undo') }]
          })
      }
    },
    template: `
      <div class="flex flex-wrap gap-2">
        <Button @click="toastDefault">Default</Button>
        <Button @click="toastSuccess">Success</Button>
        <Button @click="toastInfo">Info</Button>
        <Button @click="toastWarning">Warning</Button>
        <Button @click="toastError">Error</Button>
        <Button @click="toastPromise">Promise</Button>
        <Button @click="toastAction">Action</Button>
      </div>
      <Toaster position="top-right" />
    `
  })
}
