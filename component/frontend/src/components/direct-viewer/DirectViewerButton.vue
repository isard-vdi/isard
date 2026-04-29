<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMutation } from '@tanstack/vue-query'
import { jwtDecode } from 'jwt-decode'
import { useCookies } from '@vueuse/integrations/useCookies'
import { logViewerClickMutation } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Icon } from '@/components/icon'
import { DesktopStatusEnum } from '@/gen/oas/apiv4'
import browserIcon from '@/assets/img/viewers/vnc-browser.svg?component'
import fileIcon from '@/assets/img/viewers/spice.svg?component'

interface ViewerData {
  kind: string
  protocol: string
  viewer?: string
  cookie?: string
  name?: string
  ext?: string
  mime?: string
  content?: string
}

interface Props {
  viewer: ViewerData
  state: string
  description?: string
  token: string
}

const props = defineProps<Props>()
const emit = defineEmits<{ help: [protocol: string] }>()

const { t } = useI18n()
const cookies = useCookies(['browser_viewer'])

const protocolKey = computed(() => `${props.viewer.kind}-${props.viewer.protocol}`)

const viewerNeedsIp = (key: string) => ['file-rdpgw', 'file-rdpvpn', 'browser-rdp'].includes(key)

const isWaiting = computed(
  () => props.state === DesktopStatusEnum.WAITING_IP && viewerNeedsIp(protocolKey.value)
)

const buttonText = computed(() => {
  const { kind, protocol } = props.viewer
  return t(`viewers.${kind}-${protocol}`)
})

const showHelp = computed(
  () => props.viewer.protocol === 'spice' || props.viewer.protocol === 'rdpgw'
)

const helpKey = computed(() =>
  props.viewer.protocol === 'spice'
    ? 'views.direct-viewer.help.spice.spice-help'
    : 'views.direct-viewer.help.rdp.rdp-help'
)

const logClick = useMutation(logViewerClickMutation())

function openViewer() {
  const viewer = props.viewer
  logClick.mutate({ path: { token: props.token, protocol: protocolKey.value } })

  const el = document.createElement('a')
  if (viewer.kind === 'file' && viewer.content && viewer.mime && viewer.name && viewer.ext) {
    el.setAttribute(
      'href',
      `data:${viewer.mime};charset=utf-8,${encodeURIComponent(viewer.content)}`
    )
    el.setAttribute('download', `${viewer.name}.${viewer.ext}`)
  } else if (viewer.kind === 'browser' && viewer.cookie && viewer.viewer) {
    let exp: number
    if (viewer.protocol === 'rdp') {
      const decoded = jwtDecode<{ web_viewer: { exp: number } }>(viewer.cookie)
      exp = decoded.web_viewer.exp * 1000
    } else {
      const parsed = JSON.parse(atob(decodeURIComponent(viewer.cookie))) as {
        web_viewer: { exp: number }
      }
      exp = parsed.web_viewer.exp * 1000
    }
    cookies.set('browser_viewer', viewer.cookie, {
      path: '/',
      sameSite: 'strict',
      expires: new Date(exp)
    })
    const url = new URL(viewer.viewer)
    url.searchParams.append('direct', '1')
    el.setAttribute('href', url.toString())
    el.setAttribute('target', '_blank')
    el.setAttribute('rel', 'noopener noreferrer')
  } else {
    return
  }
  el.style.display = 'none'
  document.body.appendChild(el)
  el.click()
  document.body.removeChild(el)
}
</script>

<template>
  <div
    class="bg-white rounded-[15px] py-4 px-4 text-center w-full max-w-md m-2 relative flex flex-col"
  >
    <div class="h-20 mb-3 flex items-center justify-center">
      <component
        :is="props.viewer.kind === 'browser' ? browserIcon : fileIcon"
        class="max-h-full max-w-full"
        aria-hidden="true"
      />
    </div>

    <TooltipProvider v-if="showHelp">
      <Tooltip>
        <TooltipTrigger as-child>
          <button
            type="button"
            class="absolute top-3 right-3 text-info-500 hover:text-info-700 cursor-pointer"
            :aria-label="t(helpKey)"
            @click="emit('help', viewer.protocol)"
          >
            <Icon name="help-circle" stroke-color="info-500" size="md" />
          </button>
        </TooltipTrigger>
        <!--
          ``TooltipContent`` only renders ``title`` / ``subtitle`` props,
          not slot content — passing the help text as default slot would
          render an empty tooltip.
        -->
        <TooltipContent side="top" :title="t(helpKey)" />
      </Tooltip>
    </TooltipProvider>

    <div
      v-if="isWaiting"
      class="flex items-center justify-center gap-2 mb-2 text-warning-600 font-semibold text-sm"
    >
      <Spinner size="sm" color="green" />
      <span>{{ t('views.direct-viewer.waitingip') }}</span>
    </div>

    <div v-if="props.description" class="min-h-12 flex items-center justify-center">
      <small class="text-gray-warm-600">{{ props.description }}</small>
    </div>

    <Button
      class="mt-2 w-full bg-secondary-3-500 hover:bg-secondary-3-600 border-secondary-3-500 text-base-white"
      :disabled="isWaiting"
      @click="openViewer"
    >
      {{ buttonText }}
    </Button>
  </div>
</template>
