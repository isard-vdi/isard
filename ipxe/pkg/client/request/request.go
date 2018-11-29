package request

import (
	"crypto/tls"
	"crypto/x509"
	"io"
	"io/ioutil"
	"log"
	"net/http"
	"strings"

	"github.com/isard-vdi/isard-ipxe/pkg/config"
)

// createClient creates the client that is going to be used when calling the API for both GET and POST
func createClient() (*http.Client, error) {
	config := config.Config{}
	err := config.ReadConfig()
	if err != nil {
		return nil, err
	}

	var client = &http.Client{}

	protocol := strings.Split(config.BaseURL, ":")[0]
	if protocol == "https" {
		caCert, err := ioutil.ReadFile(config.CACert)
		if err != nil {
			return nil, err
		}
		rootCAs := x509.NewCertPool()
		rootCAs.AppendCertsFromPEM(caCert)

		tlsConfig := &tls.Config{
			RootCAs: rootCAs,
		}

		client.Transport = &http.Transport{TLSClientConfig: tlsConfig}
	}

	return client, nil
}

// Request is the struct that implements mocks.WebRequest
type Request struct{}

// Get makes a GET call to the specified url. If there's no error calling the API, error will be nil;
// even if the status code is 500
func (r Request) Get(url string) (body []byte, code int, err error) {
	client, err := createClient()
	if err != nil {
		return nil, 0, err
	}

	rsp, err := client.Get(url)
	if err != nil {
		return nil, 0, err
	}
	defer func() {
		if err = rsp.Body.Close(); err != nil {
			log.Printf("error closing the response body: %s", url)
		}
	}()

	body, err = ioutil.ReadAll(rsp.Body)
	if err != nil {
		return nil, 0, err
	}

	return body, rsp.StatusCode, nil
}

// Post makes a POST call tot he specified url. If there's no error calling the API, error will be nil;
// even if the status code is 500
func (r Request) Post(url string, body io.Reader) ([]byte, int, error) {
	client, err := createClient()
	if err != nil {
		return nil, 0, err
	}

	rsp, err := client.Post(url, "application/json", body)
	if err != nil {
		return nil, 0, err
	}
	defer func() {
		if err = rsp.Body.Close(); err != nil {
			log.Printf("error closing the response body: %s", url)
		}
	}()

	rspBody, err := ioutil.ReadAll(rsp.Body)
	if err != nil {
		return nil, 0, err
	}

	return rspBody, rsp.StatusCode, nil
}
