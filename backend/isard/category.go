package isard

import (
	"io"
	"io/ioutil"
	"net/http"

	"github.com/isard-vdi/isard/backend/pkg/utils"
)

func (i *Isard) CategoryList(w http.ResponseWriter, r *http.Request) {
	rsp, err := http.Get(i.url("categories"))
	if err != nil {
		i.sugar.Errorw("list categories",
			"err", err,
		)
	}

	defer rsp.Body.Close()
	if rsp.StatusCode != http.StatusOK {
		b, _ := ioutil.ReadAll(rsp.Body)

		i.sugar.Errorw("list categories",
			"err", err,
			"code", rsp.StatusCode,
			"body", string(b),
		)

		err = utils.NewHTTPCodeErr(rsp.StatusCode)
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusOK)
	io.Copy(w, rsp.Body)
}

func (i *Isard) CategoryLoad(category string, w http.ResponseWriter, r *http.Request) {
	rsp, err := http.Get(i.url("category/" + category))
	if err != nil {
		i.sugar.Errorw("get category",
			"err", err,
			"category", category,
		)
	}

	defer rsp.Body.Close()
	if rsp.StatusCode != http.StatusOK {
		if rsp.StatusCode == http.StatusNotFound {
			w.WriteHeader(http.StatusNotFound)
			return
		}

		b, _ := ioutil.ReadAll(rsp.Body)

		i.sugar.Errorw("get category",
			"err", err,
			"code", rsp.StatusCode,
			"body", string(b),
			"category", category,
		)

		err = utils.NewHTTPCodeErr(rsp.StatusCode)
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.WriteHeader(http.StatusOK)
	io.Copy(w, rsp.Body)
}
