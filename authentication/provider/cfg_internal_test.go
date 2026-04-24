package provider

import (
	"sync"
	"testing"

	"github.com/stretchr/testify/assert"
)

type testCfg struct {
	Name  string
	Value int
}

func TestCfgManagerCfg(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Initial  testCfg
		Expected testCfg
	}{
		"should return the stored value": {
			Initial:  testCfg{Name: "hello", Value: 42},
			Expected: testCfg{Name: "hello", Value: 42},
		},
		"should return zero value if initialized empty": {
			Initial:  testCfg{},
			Expected: testCfg{},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			m := &cfgManager[testCfg]{cfg: &tc.Initial}

			assert.Equal(tc.Expected, m.Cfg())
		})
	}
}

func TestCfgManagerLoadCfg(t *testing.T) {
	t.Parallel()

	assert := assert.New(t)

	cases := map[string]struct {
		Initial  testCfg
		Update   testCfg
		Expected testCfg
	}{
		"should update the stored value": {
			Initial:  testCfg{},
			Update:   testCfg{Name: "updated", Value: 42},
			Expected: testCfg{Name: "updated", Value: 42},
		},
		"should overwrite a previous value": {
			Initial:  testCfg{Name: "old", Value: 1},
			Update:   testCfg{Name: "new", Value: 99},
			Expected: testCfg{Name: "new", Value: 99},
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			m := &cfgManager[testCfg]{cfg: &tc.Initial}
			m.LoadCfg(tc.Update)

			assert.Equal(tc.Expected, m.Cfg())
		})
	}
}

func TestCfgManagerConcurrency(t *testing.T) {
	t.Parallel()

	cases := map[string]struct {
		Iterations int
	}{
		"should handle concurrent reads and writes safely": {
			Iterations: 100,
		},
	}

	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			t.Parallel()

			m := &cfgManager[testCfg]{cfg: &testCfg{}}

			var wg sync.WaitGroup

			for i := 0; i < tc.Iterations; i++ {
				wg.Add(1)
				go func(v int) {
					defer wg.Done()
					m.LoadCfg(testCfg{Value: v})
				}(i)
			}

			for i := 0; i < tc.Iterations; i++ {
				wg.Add(1)
				go func() {
					defer wg.Done()
					_ = m.Cfg()
				}()
			}

			wg.Wait()
		})
	}
}
