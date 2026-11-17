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

package migrationscripts

import (
	"github.com/apache/devlake/core/context"
	"github.com/apache/devlake/core/errors"
	"github.com/apache/devlake/core/plugin"
	"github.com/apache/devlake/helpers/migrationhelper"
)

var _ plugin.MigrationScript = (*addBotNamePattern)(nil)

type bitbucketScopeConfig20261118 struct {
	BotNamePattern string `mapstructure:"botNamePattern,omitempty" json:"botNamePattern" gorm:"type:varchar(255)"`
}

func (bitbucketScopeConfig20261118) TableName() string {
	return "_tool_bitbucket_scope_configs"
}

type addBotNamePattern struct{}

func (script *addBotNamePattern) Up(basicRes context.BasicRes) errors.Error {
	return migrationhelper.AutoMigrateTables(
		basicRes,
		&bitbucketScopeConfig20261118{},
	)
}

func (*addBotNamePattern) Version() uint64 {
	return 20261118090000
}

func (script *addBotNamePattern) Name() string {
	return "add bot_name_pattern to _tool_bitbucket_scope_configs"
}
