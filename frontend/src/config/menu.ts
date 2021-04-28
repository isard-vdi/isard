export const menu = [
  {
    label: 'desktops',
    icon: 'pi pi-fw pi-desktop',
    to: { name: 'search', params: { section: 'desktops' } }
  },
  {
    label: 'templates',
    icon: 'pi pi-fw pi-clone',
    to: { name: 'search', params: { section: 'Templates' } }
  },
  {
    label: 'media',
    icon: 'pi pi-fw pi-circle-off',
    to: { name: 'search', params: { section: 'Templates' } }
  },
  {
    label: 'users',
    icon: 'pi pi-fw pi-users',
    to: { name: 'search', params: { section: 'users' } }
  },
  {
    label: 'entities',
    icon: 'pi pi-fw pi-sitemap',
    to: { name: 'search', params: { section: 'entities' } }
  },
  {
    label: 'groups',
    icon: 'pi pi-fw pi-list',
    to: { name: 'search', params: { section: 'Groups' } }
  },
  {
    label: 'resources',
    icon: 'pi pi-fw pi-folder-open',
    items: [
      { label: 'graphics', to: { name: '' } },
      { label: 'video', to: { name: '' } },
      { label: 'boots', to: { name: '' } },
      { label: 'interfaces', to: { name: '' } },
      { label: 'network_qos', to: { name: '' } },
      { label: 'disk_qos', to: { name: '' } }
    ]
  },
  {
    label: 'updates',
    icon: 'pi pi-fw pi-download',
    items: [
      { label: 'domains', to: { name: '' } },
      { label: 'media', to: { name: '' } },
      { label: 'virt_installs', to: { name: '' } },
      { label: 'virt_builders', to: { name: '' } },
      { label: 'video_resources', to: { name: '' } },
      { label: 'viewers', to: { name: '' } }
    ]
  },
  {
    label: 'graphs',
    icon: 'pi pi-fw pi-chart-bar',
    to: { name: '' }
  },
  {
    label: 'configuration',
    icon: 'pi pi-fw pi-cog',
    items: [
      { label: 'general', to: { name: 'config' } },
      { label: 'roles', to: { name: '' } },
      { label: 'job_schedulers', to: { name: '' } },
      { label: 'database_backups', to: { name: '' } },
      { label: 'authentications', to: { name: '' } },
      { label: 'hypervisors', to: { name: '' } },
      { label: 'hypervisors_pools', to: { name: '' } }
    ]
  },
  {
    label: 'about',
    icon: 'pi pi-fw pi-info-circle',
    to: { name: '' }
  }
];
