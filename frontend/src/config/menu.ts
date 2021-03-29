export const menu = [
  {
    label: 'Desktops',
    icon: 'pi pi-fw pi-desktop',
    to: { name: 'search', params: { section: 'Desktops' } }
  },
  {
    label: 'Templates',
    icon: 'pi pi-fw pi-clone',
    to: { name: 'search', params: { section: 'Templates' } }
  },
  {
    label: 'Media',
    icon: 'pi pi-fw pi-circle-off',
    to: { name: 'search', params: { section: 'Templates' } }
  },
  {
    label: 'Users',
    icon: 'pi pi-fw pi-users',
    to: { name: 'search', params: { section: 'users' } }
  },
  {
    label: 'Entities',
    icon: 'pi pi-fw pi-sitemap',
    to: { name: 'search', params: { section: 'entities' } }
  },
  {
    label: 'Groups',
    icon: 'pi pi-fw pi-list',
    to: { name: 'search', params: { section: 'Groups' } }
  },
  {
    label: 'Resources',
    icon: 'pi pi-fw pi-folder-open',
    items: [
      { label: 'Graphics', to: { name: '' } },
      { label: 'Video', to: { name: '' } },
      { label: 'Boots', to: { name: '' } },
      { label: 'Interfaces', to: { name: '' } },
      { label: 'Network Qos', to: { name: '' } },
      { label: 'Disk Qos', to: { name: '' } }
    ]
  },
  {
    label: 'Updates',
    icon: 'pi pi-fw pi-download',
    items: [
      { label: 'Domains', to: { name: '' } },
      { label: 'Media', to: { name: '' } },
      { label: 'Virt Installs', to: { name: '' } },
      { label: 'Virt Builders', to: { name: '' } },
      { label: 'Video Resources', to: { name: '' } },
      { label: 'Viewers', to: { name: '' } }
    ]
  },
  {
    label: 'Graphs',
    icon: 'pi pi-fw pi-chart-bar',
    to: { name: '' }
  },
  {
    label: 'Configuration',
    icon: 'pi pi-fw pi-cog',
    items: [
      { label: 'General', to: { name: 'config' } },
      { label: 'Roles', to: { name: '' } },
      { label: 'Job Schedulers', to: { name: '' } },
      { label: 'Database Backups', to: { name: '' } },
      { label: 'Authentications', to: { name: '' } },
      { label: 'Hypervisors', to: { name: '' } },
      { label: 'Hypervisors pools', to: { name: '' } }
    ]
  },
  {
    label: 'About',
    icon: 'pi pi-fw pi-info-circle',
    to: { name: '' }
  }
];
