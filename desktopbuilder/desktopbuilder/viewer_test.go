package desktopbuilder_test

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"gitlab.com/isard/isardvdi/desktopbuilder/desktopbuilder"
)

func TestViewerGet(t *testing.T) {
	assert := assert.New(t)

	cases := map[string]struct {
		XML            string
		ExpectedViewer *desktopbuilder.Viewer
		ExpectedErr    string
	}{
		"should build correctly the viewer": {
			XML: `<domain><devices>
			<graphics type='spice' port='5900' tlsPort='5901' autoport='yes' listen='0.0.0.0' passwd='f0cKt3Rf$'></graphics>
			<graphics type='vnc' port='5902' autoport='yes' websocket='5700' listen='0.0.0.0' passwd='f0cKt3Rf$'></graphics>
			</devices></domain>`,
			ExpectedViewer: &desktopbuilder.Viewer{
				Spice: []*desktopbuilder.ViewerSpice{{
					Pwd:     "f0cKt3Rf$",
					Port:    5900,
					TLSPort: 5901,
				}},
				VNC: []*desktopbuilder.ViewerVNC{{
					Pwd:           "f0cKt3Rf$",
					Port:          5902,
					WebsocketPort: 5700,
				}},
			},
		},
		"should return an error if there's an error unmarshaling the XML": {
			ExpectedErr: "unmarshal desktop XML: EOF",
		},
		"should return an error if the desktop doesn't have graphics": {
			XML:         `<domain><devices></devices></domain>`,
			ExpectedErr: "the desktop has no graphics",
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			d := &desktopbuilder.DesktopBuilder{}

			viewer, err := d.ViewerGet(tc.XML)

			if tc.ExpectedErr != "" {
				assert.EqualError(err, tc.ExpectedErr)
			} else {
				assert.NoError(err)
			}

			assert.Equal(tc.ExpectedViewer, viewer)
		})
	}
}
