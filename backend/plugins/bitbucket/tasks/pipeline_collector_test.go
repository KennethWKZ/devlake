/*
Licensed to the Apache Software Foundation (ASF) under one or more
contributor license agreements.  See the NOTICE file distributed with
this work for additional information regarding copyright ownership.
The ASF licenses this file to You under the Apache License, Version 2.0
(the "License"); you may not use this file except in compliance with
the License.  You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package tasks

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

func TestFilterPipelinesCreatedSince(t *testing.T) {
	cutoff := time.Date(2026, 10, 19, 0, 0, 0, 0, time.UTC)
	values := []json.RawMessage{
		json.RawMessage(`{"uuid":"{a}","created_on":"2026-11-17T03:26:00.000000+00:00"}`),
		json.RawMessage(`{"uuid":"{b}","created_on":"2026-10-19T00:00:00+00:00"}`),
		json.RawMessage(`{"uuid":"{c}","created_on":"2026-10-18T23:59:59+00:00"}`),
		json.RawMessage(`{"uuid":"{d}"}`),
	}
	kept, err := filterPipelinesCreatedSince(values, cutoff)
	assert.Nil(t, err)
	var ids []string
	for _, k := range kept {
		var p struct {
			UUID string `json:"uuid"`
		}
		assert.Nil(t, json.Unmarshal(k, &p))
		ids = append(ids, p.UUID)
	}
	// created after the cutoff, exactly at it, and with no date are kept; older ones end the newest-first scan
	assert.Equal(t, []string{"{a}", "{b}", "{d}"}, ids)

	_, err = filterPipelinesCreatedSince([]json.RawMessage{json.RawMessage(`{"created_on": 5}`)}, cutoff)
	assert.NotNil(t, err)
}
