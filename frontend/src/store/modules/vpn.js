import axios from 'axios'
import i18n from '@/i18n'
import router from '@/router'
import { toast } from '@/store/index.js'
import { apiV3Segment } from '../../shared/constants'

export default {
  actions: {
    fetchVpn (context) {
      return this._vm.$snotify.async(
        i18n.t('views.select-template.notification.loading.description'),
        i18n.t('views.select-template.notification.loading.title'),
        () => new Promise((resolve, reject) => {
          axios.get(`${apiV3Segment}/user/vpn/config`).then(response => {
            const el = document.createElement('a')
            const content = response.data.content
            el.setAttribute(
              'href',
              `data:${response.data.mime};charset=utf-8,${encodeURIComponent(content)}`
            )
            el.setAttribute('download', `${response.data.name}.${response.data.ext}`)
            el.style.display = 'none'
            document.body.appendChild(el)
            el.click()
            document.body.removeChild(el)
            resolve(
              toast(
                i18n.t('components.navbar.vpn.downloaded.title'),
                i18n.t('components.navbar.vpn.downloaded.description')
              )
            )
          }).catch(e => {
            if (e.response.status === 503) {
              reject(e)
              router.push({ name: 'Maintenance' })
            } else if (e.response.status === 401 || e.response.status === 403) {
              this._vm.$snotify.clear()
              reject(e)
              router.push({ name: 'ExpiredSession' })
            } else {
              reject(
                toast(
                  i18n.t('components.navbar.vpn.downloadvpn-error.title'),
                  i18n.t('components.navbar.vpn.downloadvpn-error.description')
                )
              )
            }
          })
        })
      )
    }
  }
}
