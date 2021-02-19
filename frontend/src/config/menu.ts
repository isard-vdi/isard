export const menu = [
  {
    label: 'Login',
    icon: 'pi pi-fw pi-home',
    to: { name: 'login' }
  },
  {
    label: 'Desktops',
    icon: 'pi pi-fw pi-desktop',
    to: { name: 'About' }
  },
  {
    label: 'Templates',
    icon: 'pi pi-fw pi-clone',
    to: { name: 'templates' }
  },
  {
    label: 'Configuration',
    icon: 'pi pi-fw pi-cog',
    to: { name: 'config' }
  },
  {
    label: 'Submenu prova',
    icon: 'pi pi-fw pi-sitemap',
    items: [
      { label: 'Login', icon: 'pi pi-fw pi-id-card', to: { name: 'login' } },
      { label: 'Users', icon: 'pi pi-fw pi-users', to: { name: 'templates' } },
      {
        label: 'Entities',
        icon: 'pi pi-fw pi-users',
        items: [
          {
            label: 'Sub 2',
            icon: 'pi pi-fw pi-id-card',
            to: { name: 'login' }
          },
          {
            label: 'Sub 3',
            icon: 'pi pi-fw pi-users',
            to: { name: 'templates' }
          }
        ]
      }
    ]
  }
];
