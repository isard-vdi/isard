import Guacamole from '@isard/guacamole-common-js'
import type { Client, InputStream } from 'guacamole-common-js'

interface ClipboardData {
  type: string
  data: string | Blob
}

async function getLocalClipboard(): Promise<ClipboardData | undefined> {
  if (!navigator.clipboard?.readText) return
  try {
    return { type: 'text/plain', data: await navigator.clipboard.readText() }
  } catch {
    // Reading needs user activation; the next copy, cut or focus syncs it instead.
  }
}

async function setLocalClipboard(data: ClipboardData) {
  if (navigator.clipboard?.writeText && data.type === 'text/plain') {
    await navigator.clipboard.writeText(data.data as string)
  }
}

export function createClipboard(client: Client) {
  let cache: ClipboardData | undefined

  const setRemoteClipboard = () => {
    if (!cache) return

    const stream = client.createClipboardStream(cache.type)

    if (typeof cache.data === 'string') {
      const writer = new Guacamole.StringWriter(stream)
      writer.sendText(cache.data)
      writer.sendEnd()
    } else {
      const writer = new Guacamole.BlobWriter(stream)
      writer.oncomplete = () => writer.sendEnd()
      writer.sendBlob(cache.data)
    }
  }

  const update = () => {
    void getLocalClipboard().then((data) => {
      if (data) {
        cache = data
        setRemoteClipboard()
      }
    })
  }

  const onWindowFocus = (e: FocusEvent) => {
    if (e.target === window) update()
  }

  const install = () => {
    void getLocalClipboard().then((data) => {
      if (data) cache = data
    })
    window.addEventListener('load', update, true)
    window.addEventListener('copy', update)
    window.addEventListener('cut', update)
    window.addEventListener('focus', onWindowFocus, true)
  }

  const uninstall = () => {
    window.removeEventListener('load', update, true)
    window.removeEventListener('copy', update)
    window.removeEventListener('cut', update)
    window.removeEventListener('focus', onWindowFocus, true)
  }

  const onClipboard = (stream: InputStream, mimetype: string) => {
    if (/^text\//.exec(mimetype)) {
      const reader = new Guacamole.StringReader(stream)
      let data = ''
      reader.ontext = (text) => {
        data += text
      }
      reader.onend = () => {
        void setLocalClipboard({ type: mimetype, data })
      }
    } else {
      const reader = new Guacamole.BlobReader(stream, mimetype)
      reader.onend = () => {
        void setLocalClipboard({ type: mimetype, data: reader.getBlob() })
      }
    }
  }

  return { install, uninstall, setRemoteClipboard, onClipboard }
}

export type GuacamoleClipboard = ReturnType<typeof createClipboard>
