import i18n from '@/i18n'

export class DesktopConfig {
  static tableConfig = [
    {
      key: 'action',
      label: i18n.t('components.desktop-cards.table-header.action'),
      thStyle: { width: '8cm' }
    },
    {
      key: 'viewers',
      thStyle: { width: '8cm' },
      label: i18n.t('components.desktop-cards.table-header.viewers')
    },
    {
      key: 'ip',
      sortable: true,
      label: 'IP',
      thStyle: { width: '3cm' },
      tdClass: 'pt-3'
    },
    {
      key: 'state',
      sortable: true,
      formatter: value => {
        return value ? i18n.t(`views.select-template.status.${value.toLowerCase()}.text`) : ''
      },
      sortByFormatted: true,
      label: i18n.t('components.desktop-cards.table-header.state'),
      thStyle: { width: '5cm' },
      tdClass: 'pt-3'
    },
    {
      key: 'name',
      sortable: true,
      label: i18n.t('components.desktop-cards.table-header.name'),
      thStyle: { width: '10cm' }
    },
    {
      key: 'description',
      sortable: true,
      label: i18n.t('components.desktop-cards.table-header.description'),
      tdClass: 'pt-3'
    }
  ]
}
