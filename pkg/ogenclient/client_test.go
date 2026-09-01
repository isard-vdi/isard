package ogenclient_test

import (
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"

	"gitlab.com/isard/isardvdi/pkg/ogenclient"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestNewHTTPClient(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Opts              []ogenclient.Option
		ExpectedUserAgent string
		ExpectedErr       string
		Exercise          func(*testing.T, *http.Client)
	}{
		"should verify certificates by default": {
			ExpectedErr: "certificate signed by unknown authority",
		},
		"should reach a self-signed server if the certs are ignored": {
			Opts:              []ogenclient.Option{ogenclient.WithIgnoreCerts()},
			ExpectedUserAgent: "Go-http-client/1.1",
		},
		"should identify itself if given a user agent": {
			Opts: []ogenclient.Option{
				ogenclient.WithIgnoreCerts(),
				ogenclient.WithUserAgent("isardvdi-test"),
			},
			ExpectedUserAgent: "isardvdi-test",
		},
		"should pool a concurrent burst so the next one redials nothing": {
			Exercise: func(t *testing.T, c *http.Client) {
				const concurrency = 8

				arrived := make(chan struct{}, concurrency)
				release := [2]chan struct{}{make(chan struct{}), make(chan struct{})}
				var served atomic.Int64

				srv := httptest.NewUnstartedServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
					burst := (served.Add(1) - 1) / concurrency
					arrived <- struct{}{}
					<-release[burst]
				}))

				var opened atomic.Int64
				srv.Config.ConnState = func(_ net.Conn, state http.ConnState) {
					if state == http.StateNew {
						opened.Add(1)
					}
				}

				srv.Start()
				defer srv.Close()

				burst := func(i int) {
					var wg sync.WaitGroup
					for range concurrency {
						wg.Go(func() {
							rsp, err := c.Get(srv.URL)
							if !assert.NoError(err) {
								return
							}

							// Drained and closed, or net/http will not pool it.
							_, err = io.Copy(io.Discard, rsp.Body)
							assert.NoError(err)
							assert.NoError(rsp.Body.Close())
						})
					}

					for range concurrency {
						<-arrived
					}
					close(release[i])

					wg.Wait()
				}

				burst(0)
				afterFirst := opened.Load()

				burst(1)

				require.EqualValues(t, concurrency, afterFirst, "the first burst needs one connection per request")
				assert.EqualValues(afterFirst, opened.Load(), "the second burst must reuse the pooled connections")
			},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			cli := ogenclient.NewHTTPClient(tc.Opts...)

			if tc.Exercise != nil {
				tc.Exercise(t, cli)

				return
			}

			received := make(chan string, 1)
			srv := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				received <- r.UserAgent()
			}))
			defer srv.Close()

			rsp, err := cli.Get(srv.URL)

			if tc.ExpectedErr != "" {
				assert.ErrorContains(err, tc.ExpectedErr)

				return
			}

			require.NoError(t, err)
			defer rsp.Body.Close()

			assert.Equal(tc.ExpectedUserAgent, <-received)
		})
	}
}
