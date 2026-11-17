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

	"github.com/apache/devlake/core/models/domainlayer/crossdomain"
	"github.com/apache/devlake/helpers/e2ehelper"
	"github.com/apache/devlake/helpers/pluginhelper/api"
	"github.com/apache/devlake/plugins/bitbucket/impl"
	"github.com/apache/devlake/plugins/bitbucket/models"
	"github.com/apache/devlake/plugins/bitbucket/tasks"
	"github.com/stretchr/testify/assert"
)

// TestAccountsBotNamePattern checks that botNamePattern marks matching
// Bitbucket accounts as bots in the domain accounts table (DORA skips their
// PR comments when finding the first review), and that others stay people.
func TestAccountsBotNamePattern(t *testing.T) {
	var bitbucket impl.Bitbucket
	dataflowTester := e2ehelper.NewDataFlowTester(t, "bitbucket", bitbucket)

	dataflowTester.ImportCsvIntoRawTable("./raw_tables/_raw_bitbucket_api_issues.csv", "_raw_bitbucket_api_issues")
	dataflowTester.ImportCsvIntoRawTable("./raw_tables/_raw_bitbucket_api_pull_requests.csv", "_raw_bitbucket_api_pull_requests")
	dataflowTester.FlushTabler(&models.BitbucketAccount{})
	dataflowTester.FlushTabler(&models.BitbucketIssue{})
	dataflowTester.FlushTabler(&models.BitbucketPullRequest{})
	base := &tasks.BitbucketTaskData{Options: &tasks.BitbucketOptions{ConnectionId: 1, FullName: "likyh/likyhphp"}}
	dataflowTester.Subtask(tasks.ExtractApiIssuesMeta, base)
	dataflowTester.Subtask(tasks.ExtractApiPullRequestsMeta, base)

	bots := func(pattern string) (int, int) {
		enricher := api.NewRegexEnricher()
		if err := enricher.TryAdd(tasks.BOT_NAME_PATTERN, pattern); err != nil {
			t.Fatal(err)
		}
		taskData := &tasks.BitbucketTaskData{Options: base.Options, RegexEnricher: enricher}
		dataflowTester.FlushTabler(&crossdomain.Account{})
		dataflowTester.Subtask(tasks.ConvertAccountsMeta, taskData)
		var accounts []crossdomain.Account
		if err := dataflowTester.Dal.All(&accounts); err != nil {
			t.Fatal(err)
		}
		n := 0
		for _, a := range accounts {
			if a.IsBot {
				n++
			}
		}
		return n, len(accounts)
	}

	n, total := bots(`(?i)^TEOIAOE$`)
	assert.Equal(t, 1, total)
	assert.Equal(t, 1, n, "display name matching botNamePattern must be a bot")

	n, _ = bots(`^someone-else$`)
	assert.Equal(t, 0, n, "accounts not matching botNamePattern must not be bots")

	n, _ = bots(``)
	assert.Equal(t, 0, n, "an empty botNamePattern marks no account as a bot")
}
