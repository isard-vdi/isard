package collector

import (
	"context"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"

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

func transformLibvirtData(ts time.Time, measurement string, tags map[string]string, prefix string, data interface{}) ([]*write.Point, error) {
	// TODO: Check if there's any better way to do this
	// Marhsal and unmarshal the data interface{} to transform from a Go type to a map[string]interface{}
	b, err := json.Marshal(data)
	if err != nil {
		return nil, fmt.Errorf("marshal json data: %w", err)
	}

	jsonMap := map[string]interface{}{}
	if err := json.Unmarshal(b, &jsonMap); err != nil {
		return nil, fmt.Errorf("unmarshal json data: %w", err)
	}

	d, points := extractLibvirtData([]*write.Point{}, ts, measurement, tags, prefix, jsonMap)
	points = append(points, write.NewPoint(measurement, tags, d, ts))

	return points, nil
}

var knownStatsSlices = map[string]string{
	"stats_block": "stats_block_name",
	"stats_net":   "stats_net_name",
}

func extractLibvirtData(points []*write.Point, ts time.Time, measurement string, tags map[string]string, prefix string, data map[string]interface{}) (map[string]interface{}, []*write.Point) {
	res := map[string]interface{}{}

	for k, exists := range data {

		// Check if the field is <key>Set, which defines whether <key> has a value or not. If it does and it's true, get the <key> value
		if strings.HasSuffix(k, "Set") && exists.(bool) {
			k = strings.TrimSuffix(k, "Set")
			v := data[k]

			var key string
			if prefix == "" {
				key = strcase.ToSnake(k)
			} else {
				key = fmt.Sprintf("%s_%s", prefix, strcase.ToSnake(k))
			}

			switch val := v.(type) {
			// If it's a slice, get the key
			case []interface{}:
				// if it's not found in the known stats map, the "id" variable is going to have "" as value, which means "use the slice position (index) as ID"
				id, _ := knownStatsSlices[key]

				for i, item := range val {
					var sliceData = map[string]interface{}{}
					sliceData, points = extractLibvirtData(points, ts, measurement, tags, key, item.(map[string]interface{}))

					var idVal string
					if id == "" {
						idVal = strconv.Itoa(i)
					} else {
						idVal = sliceData[id].(string)
						delete(sliceData, id)
					}

					// Add the new point, and tag it correctly with the ID!
					p := write.NewPoint(measurement, tags, sliceData, ts)
					p.AddTag(id, idVal)

					points = append(points, p)
				}

			// If it's a map, recurse!
			case map[string]interface{}:
				var child = map[string]interface{}{}
				child, points = extractLibvirtData(points, ts, measurement, tags, key, val)
				for cK, cV := range child {
					res[cK] = cV
				}

			default:
				res[key] = v
			}
		}
	}

	return res, points
}
