pkgver=0.15.2
makedepends="
	cyrus-sasl-dev
	gdk-pixbuf-dev
	glib-dev
	gst-plugins-base-dev
	gstreamer-dev
	libjpeg-turbo-dev
	lz4-dev
	meson
	openssl-dev>3
	opus-dev
	orc-dev
	pixman-dev
	py3-parsing
	py3-six
	spice-protocol
	zlib-dev
	"
apk add $makedepends

## FROM GIT
apk add git
apk add abuild
git clone https://gitlab.freedesktop.org/spice/spice.git
cd spice
git checkout fe1c25f530b95d32cc81bc1a395d80ace631d2dd
	abuild-meson \
		-Db_lto=true \
		-Dgstreamer=1.0 \
		-Dlz4=true \
		-Dsasl=true \
		-Dopus=enabled \
		-Dsmartcard=disabled \
		. output
	meson compile -C output

## FROM TAR (As in alpine pkg build)
# source="https://www.spice-space.org/download/releases/spice-server/spice-$pkgver.tar.bz2"
# wget -O- "$source" | tar xj || exit 1
# cd spice-$pkgver

# ./configure --prefix=/usr --sysconfdir=/etc \
# 	--localstatedir=/var --libdir=/usr/lib
# make
# make install
cp /usr/lib/libspice-server.so.1* /isard/volatiles/