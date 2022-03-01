package collector

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/ettle/strcase"
	"github.com/influxdata/influxdb-client-go/v2/api/write"
)

type Collector interface {
	Collect(ctx context.Context) ([]*write.Point, error)
	String() string
	Close() error
}

func mergeMaps(maps ...map[string]interface{}) map[string]interface{} {
	res := map[string]interface{}{}
	for _, m := range maps {
		for k, v := range m {
			res[k] = v
		}
	}

	return res
}

func transformLibvirtData(prefix string, data interface{}) (map[string]interface{}, error) {
	b, err := json.Marshal(data)
	if err != nil {
		return nil, fmt.Errorf("marshal json data: %w", err)
	}

	res := map[string]interface{}{}
	jsonMap := map[string]interface{}{}
	if err := json.Unmarshal(b, &jsonMap); err != nil {
		return nil, fmt.Errorf("unmarshal json data: %w", err)
	}

	for k, v := range jsonMap {
		if strings.HasSuffix(k, "Set") && v.(bool) {
			k = strings.TrimSuffix(k, "Set")
			res[fmt.Sprintf("%s_%s", prefix, strcase.ToSnake(k))] = jsonMap[k]
		}
	}

	return res, nil
}
