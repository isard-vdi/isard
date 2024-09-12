import axios from 'axios'
import i18n from '@/i18n'
// import router from '@/router'
import { apiV3Segment } from '../../shared/constants'
import { ErrorUtils } from '../../utils/errorUtils'

export default {
  actions: {
    fetchVpn (context) {
      ErrorUtils.showInfoMessage(this._vm.$snotify,
        i18n.t('views.select-template.notification.loading.description'),
        i18n.t('views.select-template.notification.loading.title'))

      axios.get(`${apiV3Segment}/user/vpn/config`).then(response => {
        this._vm.$snotify.clear()

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

        ErrorUtils.showInfoMessage(this._vm.$snotify,
          i18n.t('components.navbar.vpn.downloaded.description'),
          i18n.t('components.navbar.vpn.downloaded.title'), false, 2000)
      }).catch(e => {
        this._vm.$snotify.clear()

        if (e.response.status === 503) {
          window.location.pathname = '/maintenance'
        } else {
          ErrorUtils.showErrorMessage(this._vm.$snotify, e,
            i18n.t('components.navbar.vpn.downloadvpn-error.description'),
            i18n.t('components.navbar.vpn.downloadvpn-error.title'))
        }
      })
    }
  }
}
