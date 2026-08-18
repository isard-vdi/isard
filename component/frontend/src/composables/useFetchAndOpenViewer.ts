import { computed } from 'vue'
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { useLocalStorage } from '@vueuse/core'
import { useCookies } from '@vueuse/integrations/useCookies'

import { getDesktopViewerByTypeOptions } from '@/gen/oas/apiv4/@tanstack/vue-query.gen'
import type { GetDesktopViewerByTypeData } from '@/gen/oas/apiv4'

type ViewerType = GetDesktopViewerByTypeData['path']['viewer_type']

export interface FetchAndOpenViewerVariables {
  desktopId: string
  viewer: ViewerType
}

export function useFetchAndOpenViewer() {
  const queryClient = useQueryClient()
  const cookies = useCookies(['viewerToken', 'browser_viewer'])
  const localStorage = useLocalStorage('viewers', '')

  const preferedViewers = computed<Record<string, ViewerType>>(() =>
    localStorage.value ? JSON.parse(localStorage.value) : {}
  )

  const mutation = useMutation({
    mutationFn: async ({ desktopId, viewer }: FetchAndOpenViewerVariables) => {
      const data = await queryClient.fetchQuery({
        ...getDesktopViewerByTypeOptions({
          path: { desktop_id: desktopId, viewer_type: viewer },
          throwOnError: true
        })
      })

      localStorage.value = JSON.stringify({
        ...preferedViewers.value,
        [desktopId]: viewer
      })

      if (data.kind === 'browser') {
        if (data.protocol === 'rdp') {
          // TODO: session cookie — preserved from original implementation
          alert('TODO: set session cookie for RDP viewer')
        }
        cookies.set('browser_viewer', data.cookie)
        window.open(data.viewer || undefined, '_blank')
      } else if (data.kind === 'file') {
        const el = document.createElement('a')
        el.setAttribute(
          'href',
          `data:${data.mime};charset=utf-8,${encodeURIComponent(data.content || '')}`
        )
        el.setAttribute('download', `${data.name}.${data.ext}`)
        el.style.display = 'none'
        document.body.appendChild(el)
        el.click()
        document.body.removeChild(el)
      }

      return data
    }
  })

  return {
    ...mutation,
    preferedViewers
  }
}
