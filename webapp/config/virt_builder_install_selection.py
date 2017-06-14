## INSERT IN DB SELECION OF VIRT-INSTALL AND VIRT-BUILDER


''''

VIRT - BUILDER
VIRT - INSTALL

'''


def create_builders():
    l=[]
    d_fedora25 = {'id': 'fedora25_gnome_office',
                  'name': 'Fedora 25 with gnome and libre office',
                  'builder':{
                      'id': 'fedora-25',
                      'options':
"""--update
--selinux-relabel
--install "@workstation-product-environment"
--install "inkscape,tmux,@libreoffice,chromium"
--install "libreoffice-langpack-ca,langpacks-es"
--root-password password:alumne
--link /usr/lib/systemd/system/graphical.target:/etc/systemd/system/default.target
--firstboot-command 'localectl set-locale LANG=es_ES.utf8'
--firstboot-command 'localectl set-keymap es'
--firstboot-command 'systemctl isolate graphical.target'
--firstboot-command 'useradd -m -p "" guest ; chage -d 0 guest'"""
                  },
                  'install':{
                      'id': 'fedora25',
                      'options': ''
                  }
                  }
    l.append(d_fedora25)
    return l

def update_virtbuilder(url="http://libguestfs.org/download/builder/index"):

    import urllib.request
    with urllib.request.urlopen(url) as response:
        f = response.read()

    s = f.decode('utf-8')
    #select only arch x86_64
    l = [a.split(']') for a in s[1:].split('\n[') if a.find('\narch=x86_64') > 0]

    list_virtbuilder = []
    for b in l:
        d = {a.split('=')[0]: a.split('=')[1] for a in b[1].split('notes')[0].split('\n')[1:] if
                   len(a) > 0 and a.find('=') > 0}
        d['id'] = b[0]
        list_virtbuilder.append(d)

    return list_virtbuilder


def update_virtinstall(from_osinfo_query=False):

    if from_osinfo_query is True:
        import subprocess
        data = subprocess.getoutput("osinfo-query os")

    else:
        from os import path
        from os import getcwd
        __location__ = path.realpath(
                path.join(getcwd(), path.dirname(__file__)))
        f=open(__location__+'/osinfo.txt')
        data = f.read()
        f.close()

    installs=[]

    for l in data.split('\n')[2:]:
        if l.find('|') > 1:

            v=[a.strip() for a in l.split('|')]

            #DEFAULT FONT
            font_type = 'font-awesome'
            font_class = 'fa-linux'

            for oslinux in ('fedora,centos,debian,freebsd,mageia,mandriva,opensuse,ubuntu,opensuse'.split(',')):
                    font_type  = 'font-linux'
                    font_class = 'fl-'+oslinux

            if v[0].find('rhel') == 0 or v[0].find('rhl') == 0:
                font_type  = 'font-linux'
                font_class = 'fl-redhat'

            elif v[0].find('win') == 0:
                font_type  = 'font-awesome'
                font_class = 'fa-windows'

            installs.append({'id':v[0].strip(),
                             'name':v[1].strip(),
                             'vers':v[2].strip(),
                             'www':v[3].strip(),
                             'font_type':font_type,
                             'icon':font_class})

    return installs


