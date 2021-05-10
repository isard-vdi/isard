package isard

import (
	"fmt"
	"io/ioutil"
	"net/http"

	"github.com/isard-vdi/isard/backend/pkg/utils"
)

var viewerTypeTranslation = map[string]string{
	"spice":     "spice-client",
	"rdp":       "rdp-client",
	"browser":   "vnc-html5",
	"rdp-html5": "rdp-html5",
}

func (i *Isard) Viewer(id string, viewerType string) ([]byte, error) {
	viewer, found := viewerTypeTranslation[viewerType]
	if !found {
		return nil, ErrUnknownViewerType
	}

	rsp, err := http.Get(i.url(fmt.Sprintf("desktop/%s/viewer/%s", id, viewer)))
	if err != nil {
		i.sugar.Errorw("get viewer",
			"err", err,
			"type", viewer,
			"id", id,
		)
		return nil, fmt.Errorf("get viewer: %w", err)
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

		return nil, fmt.Errorf("get viewer: %w", err)
	}

	return ioutil.ReadAll(rsp.Body)
}
