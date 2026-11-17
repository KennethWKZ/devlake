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
	"net/http"
	"net/url"
	"time"

	"github.com/apache/devlake/core/errors"
	plugin "github.com/apache/devlake/core/plugin"
	helper "github.com/apache/devlake/helpers/pluginhelper/api"
)

const RAW_PIPELINE_TABLE = "bitbucket_api_pipelines"

// PipelineLookback is how far before the last collection an incremental run still re-reads pipelines, so a
// pipeline that was paused at a manual step (for example a production deploy) and finished later is updated.
const PipelineLookback = 30 * 24 * time.Hour

const pipelineFields = `values.uuid,values.type,values.state.name,values.state.result.name,values.state.result.type,values.state.stage.name,values.state.stage.type,` +
	`values.target.ref_name,values.target.commit.hash,` +
	`values.created_on,values.completed_on,values.duration_in_seconds,values.build_number,values.links.self,` +
	`page,pagelen,size`

var CollectApiPipelinesMeta = plugin.SubTaskMeta{
	Name:             "Collect Pipelines",
	EntryPoint:       CollectApiPipelines,
	EnabledByDefault: true,
	Description:      "Collect pipeline data from bitbucket api",
	DomainTypes:      []string{plugin.DOMAIN_TYPE_CICD},
}

func CollectApiPipelines(taskCtx plugin.SubTaskContext) errors.Error {
	rawDataSubTaskArgs, data := CreateRawDataSubTaskArgs(taskCtx, RAW_PIPELINE_TABLE)
	collectorWithState, err := helper.NewStatefulApiCollector(*rawDataSubTaskArgs)
	if err != nil {
		return err
	}

	args := helper.ApiCollectorArgs{
		ApiClient:      data.ApiClient,
		PageSize:       50,
		UrlTemplate:    "repositories/{{ .Params.FullName }}/pipelines/",
		Query:          GetQueryCreatedAndUpdated(pipelineFields, collectorWithState),
		ResponseParser: GetRawMessageFromResponse,
		GetTotalPages:  GetTotalPagesFromResponse,
	}
	// Bitbucket's pipelines endpoint ignores the `q` filter (updated_on>=...), so an incremental run used to
	// fetch every pipeline of the repository again and append it to the raw table (one more copy of each
	// pipeline per run). Incremental runs now read newest first and stop at the first page that reaches
	// pipelines created before the last collection minus PipelineLookback.
	if since := collectorWithState.GetSince(); since != nil {
		args.Query = pipelinesNewestFirstQuery
		args.GetTotalPages = nil
		args.ResponseParser = pipelinesCreatedSince(since.Add(-PipelineLookback))
	}

	err = collectorWithState.InitCollector(args)
	if err != nil {
		return err
	}

	return collectorWithState.Execute()
}

func pipelinesNewestFirstQuery(reqData *helper.RequestData) (url.Values, errors.Error) {
	query, err := GetQuery(reqData)
	if err != nil {
		return nil, err
	}
	query.Set("fields", pipelineFields)
	query.Set("sort", "-created_on")
	return query, nil
}

// pipelinesCreatedSince keeps the pipelines created at or after cutoff. With newest-first pages, a page that
// returns fewer than the page size ends the collection.
func pipelinesCreatedSince(cutoff time.Time) func(res *http.Response) ([]json.RawMessage, errors.Error) {
	return func(res *http.Response) ([]json.RawMessage, errors.Error) {
		values, err := GetRawMessageFromResponse(res)
		if err != nil {
			return nil, err
		}
		return filterPipelinesCreatedSince(values, cutoff)
	}
}

func filterPipelinesCreatedSince(values []json.RawMessage, cutoff time.Time) ([]json.RawMessage, errors.Error) {
	kept := make([]json.RawMessage, 0, len(values))
	for _, v := range values {
		var p struct {
			CreatedOn *time.Time `json:"created_on"`
		}
		if err := json.Unmarshal(v, &p); err != nil {
			return nil, errors.Default.Wrap(err, "read pipeline created_on")
		}
		if p.CreatedOn == nil || !p.CreatedOn.Before(cutoff) {
			kept = append(kept, v)
		}
	}
	return kept, nil
}
