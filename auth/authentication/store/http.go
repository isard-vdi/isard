package store

import (
	"context"
	"net/http"
)

const SessionStoreKey = "session"

func BuildHTTPRequest(ctx context.Context, token string) *http.Request {
	c := &http.Cookie{
		Name:  SessionStoreKey,
		Value: token,
	}

	r := &http.Request{
		Header: http.Header{
			"Cookie": []string{c.String()},
		},
	}

	return r.WithContext(ctx)
}

func GetToken(w http.ResponseWriter) (string, error) {
	r := &http.Request{Header: http.Header{
		"Cookie": []string{w.Header().Get("Set-Cookie")},
	}}

	session, err := r.Cookie(SessionStoreKey)
	if err != nil {
		return "", err
	}

	return session.Value, nil
}

func BuildHTTPResponseWriter() http.ResponseWriter {
	return &httpResponseWriter{
		header: http.Header{},
	}
}

type httpResponseWriter struct {
	header http.Header
}

func (w *httpResponseWriter) Header() http.Header {
	return w.header
}

func (w *httpResponseWriter) Write(b []byte) (int, error) {
	return 0, nil
}

func (w *httpResponseWriter) WriteHeader(i int) {}
