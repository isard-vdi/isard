package isardAdmin

import "net/http"

const LogoutURL = "http://isard-webapp:5000/isard-admin/logout/remote"

func Logout(w http.ResponseWriter, r *http.Request) error {
	req, err := http.NewRequest("GET", LogoutURL, nil)
	if err != nil {
		return err
	}
	for _, c := range r.Cookies() {
		req.AddCookie(c)
	}
	client := &http.Client{
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	for _, c := range resp.Cookies() {
		http.SetCookie(w, c)
	}
	return nil
}
