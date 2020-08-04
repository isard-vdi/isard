package isard

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"net/http"
	"net/url"
	"strings"

	"github.com/isard-vdi/isard/backend/pkg/utils"
)

type viewerType int

const (
	viewerTypeRemote viewerType = iota
	viewerTypeHTML
)

type viewerRsp struct {
	Viewer string `json:"viewer"`
}

func (i *Isard) viewer(id string, vType viewerType) (string, error) {
	var viewer string
	switch vType {
	case viewerTypeRemote:
		viewer = "spice-client"

	case viewerTypeHTML:
		viewer = "vnc-html5"

	default:
		return "", ErrUnknownViewerType
	}

	rsp, err := http.Get(i.url(fmt.Sprintf("desktop/%s/viewer/%s", id, viewer)))
	if err != nil {
		i.sugar.Errorw("get viewer",
			"err", err,
			"type", viewer,
			"id", id,
		)
		return "", fmt.Errorf("get viewer: %w", err)
	}

	defer rsp.Body.Close()
	if rsp.StatusCode != http.StatusOK {
		b, _ := ioutil.ReadAll(rsp.Body)

		err = utils.NewHTTPCodeErr(rsp.StatusCode)
		i.sugar.Errorw("get viewer",
			"err", err,
			"code", rsp.StatusCode,
			"body", string(b),
			"type", viewer,
			"id", id,
		)

		return "", fmt.Errorf("get viewer: %w", err)
	}

	v := &viewerRsp{}
	err = json.NewDecoder(rsp.Body).Decode(v)
	if err != nil {
		i.sugar.Errorw("get viewer: decode json",
			"err", err,
			"type", viewer,
			"id", id,
		)

		return "", fmt.Errorf("get viewer: decode json: %w", err)
	}

	if vType == viewerTypeHTML {
		u, err := url.Parse(v.Viewer)
		if err != nil {
			i.sugar.Errorw("decode HTML5 viewer",
				"err", err,
				"type", viewer,
				"viewer", v.Viewer,
				"id", id,
			)

			return "", fmt.Errorf("decode HTML5 viewer: %w", err)
		}

		v.Viewer = strings.Join([]string{
			u.Query().Get("host"),
			u.Query().Get("port"),
			u.Query().Get("vmHost"),
			u.Query().Get("vmPort"),
			u.Query().Get("passwd"),
		}, "|||")
	}

	return v.Viewer, nil
}

// ViewerRemote returns the remote viewer
func (i *Isard) ViewerRemote(id string) (string, error) {
	content, err := i.viewer(id, viewerTypeRemote)
	if err != nil {
		return "", err
	}

	return content, nil
}

// ViewerHTML is the contents needed for connecting to the HTML5 spice web viewer
type ViewerHTML struct {
	Host   string `json:"host,omitempty"`
	Port   string `json:"port,omitempty"`
	VMHost string `json:"vmHost,omitempty"`
	VMPort string `json:"vmPort,omitempty"`
	Token  string `json:"token,omitempty"`
}

// ViewerHTML returns the html viewer
func (i *Isard) ViewerHTML(id string) (*ViewerHTML, error) {
	content, err := i.viewer(id, viewerTypeHTML)
	if err != nil {
		return nil, err
	}

	val := strings.Split(content, "|||")

	return &ViewerHTML{
		Host:   val[0],
		Port:   val[1],
		VMHost: val[2],
		VMPort: val[3],
		Token:  val[4],
	}, nil
}
