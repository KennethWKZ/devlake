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

package e2e

import (
	"testing"

	"github.com/apache/devlake/core/dal"
	"github.com/apache/devlake/core/models/domainlayer/devops"
	"github.com/apache/devlake/helpers/e2ehelper"
	"github.com/apache/devlake/helpers/pluginhelper/api"
	"github.com/apache/devlake/plugins/bitbucket/impl"
	"github.com/apache/devlake/plugins/bitbucket/models"
	"github.com/apache/devlake/plugins/bitbucket/tasks"
)

// Bitbucket environment names are free text, so teams with one environment
// per region (Production-MY, Production-AU, ...) need envNamePattern to have
// those deployments counted as PRODUCTION. The fixture has 14 Production,
// 4 Staging and 9 Test deployments; matching Staging as well must promote
// those 4 and leave Test as TESTING, with the original names kept.
func TestDeploymentsEnvNamePattern(t *testing.T) {
	var bitbucket impl.Bitbucket
	dataflowTester := e2ehelper.NewDataFlowTester(t, "bitbucket", bitbucket)

	regexEnricher := api.NewRegexEnricher()
	if err := regexEnricher.TryAdd(devops.ENV_NAME_PATTERN, `(?i)^(production|staging)$`); err != nil {
		t.Fatal(err)
	}
	taskData := &tasks.BitbucketTaskData{
		Options: &tasks.BitbucketOptions{
			ConnectionId: 1,
			FullName:     "likyh/likyhphp",
			BitbucketScopeConfig: &models.BitbucketScopeConfig{
				EnvNamePattern: `(?i)^(production|staging)$`,
			},
		},
		RegexEnricher: regexEnricher,
	}

	dataflowTester.FlushTabler(&models.BitbucketRepo{})
	dataflowTester.FlushTabler(&models.BitbucketPipeline{})
	dataflowTester.FlushTabler(&models.BitbucketDeployment{})
	dataflowTester.ImportCsvIntoTabler("./snapshot_tables/_tool_bitbucket_repos_for_deployment.csv", &models.BitbucketRepo{})
	dataflowTester.ImportCsvIntoTabler("./snapshot_tables/_tool_bitbucket_pipelines_for_deployment.csv", &models.BitbucketPipeline{})
	dataflowTester.ImportCsvIntoTabler("./snapshot_tables/_tool_bitbucket_deployments_for_deployment.csv", &models.BitbucketDeployment{})
	dataflowTester.FlushTabler(&devops.CicdDeploymentCommit{})
	dataflowTester.FlushTabler(&devops.CICDDeployment{})
	dataflowTester.Subtask(tasks.ConvertiDeploymentMeta, taskData)

	count := func(where string, args ...interface{}) int64 {
		n, err := dataflowTester.Dal.Count(dal.From(&devops.CicdDeploymentCommit{}), dal.Where(where, args...))
		if err != nil {
			t.Fatal(err)
		}
		return n
	}
	if got := count("environment = ?", devops.PRODUCTION); got != 18 {
		t.Errorf("PRODUCTION deployment commits: got %d, want 18 (14 Production + 4 Staging)", got)
	}
	if got := count("environment = ? AND original_environment = ?", devops.PRODUCTION, "STAGING"); got != 4 {
		t.Errorf("promoted Staging rows keeping original_environment STAGING: got %d, want 4", got)
	}
	if got := count("environment = ?", devops.TESTING); got != 9 {
		t.Errorf("TESTING deployment commits: got %d, want 9", got)
	}
	n, err := dataflowTester.Dal.Count(dal.From(&devops.CICDDeployment{}), dal.Where("environment = ?", devops.PRODUCTION))
	if err != nil {
		t.Fatal(err)
	}
	if n != 18 {
		t.Errorf("PRODUCTION cicd_deployments: got %d, want 18", n)
	}
}
