#!/usr/bin/env python3
"""Build the MoneyMatch DevEx Grafana dashboard (uid mm-devex) as JSON on stdout.

Reads DevLake's MySQL through the devlake-mysql-api datasource. Weeks run Monday to Sunday in
Malaysia time (UTC+8); weekly charts show complete weeks only, so the running week never reads as a drop.
Metrics come from pull requests, deployments and pipelines, not commits, so the upstream history of the
GitHub forks never inflates them.
"""
import json

DS = {"type": "mysql", "uid": "devlake-mysql-api"}


def myt(x):
    return f"date_add({x}, interval 8 hour)"


def monday(x):
    return f"date_sub(date({myt(x)}), interval weekday({myt(x)}) day)"


# Complete weeks inside the time range: first Monday on/after the start, last Monday a full week before the end.
WEEKS = f"""weeks(w) as (
  select date_add({monday('$__timeFrom()')}, interval if(weekday({myt('$__timeFrom()')}) = 0 and time({myt('$__timeFrom()')}) = '00:00:00', 0, 7) day)
  union all
  select date_add(w, interval 7 day) from weeks
  where date_add(w, interval 7 day) <= date_sub({monday('$__timeTo()')}, interval 7 day)
)"""

DEPLOYS = """_d as (
  select cdc.cicd_deployment_id as id, max(cdc.finished_date) as fin,
         max(cdc.original_environment) as env, max(cdc.cicd_scope_id) as scope
  from cicd_deployment_commits cdc
  join project_mapping pm on cdc.cicd_scope_id = pm.row_id and pm.`table` = 'cicd_scopes'
  where pm.project_name in (${project}) and cdc.cicd_scope_id in (${repo})
    and cdc.result = 'SUCCESS' and cdc.environment = 'PRODUCTION'
  group by 1
  having $__timeFilter(max(cdc.finished_date))
)"""

# PRs whose deployment finished in the range (DevLake's own lead-time population).
DEPLOYED_PRS = """_p as (
  select distinct pr.id, pr.base_repo_id as repo, ppm.pr_cycle_time, ppm.pr_coding_time, ppm.pr_pickup_time,
         ppm.pr_review_time, ppm.pr_deploy_time, timestampdiff(minute, pr.created_date, pr.merged_date) as pr_open_time,
         cdc.finished_date as fin
  from pull_requests pr
  join project_pr_metrics ppm on ppm.id = pr.id
  join project_mapping pm on pr.base_repo_id = pm.row_id and pm.`table` = 'repos'
  join cicd_deployment_commits cdc on ppm.deployment_commit_id = cdc.id
  where pm.project_name in (${project}) and pr.base_repo_id in (${repo}) and pr.author_id in (${author})
    and pr.merged_date is not null and ppm.pr_cycle_time is not null
    and $__timeFilter(cdc.finished_date)
)"""

PROJECT_REPOS = """select r.id from repos r join project_mapping pm on pm.row_id = r.id and pm.`table` = 'repos'
  where pm.project_name in (${project}) and r.id in (${repo})"""

panels = []
_id = 0


def panel(kind, title, desc, grid, sql, **extra):
    global _id
    _id += 1
    p = {
        "id": _id, "type": kind, "title": title, "description": desc, "datasource": DS,
        "gridPos": dict(zip("xywh", grid)),
        "targets": [{"refId": "A", "datasource": DS, "format": "table", "rawQuery": True, "editorMode": "code", "rawSql": sql.strip()}],
    }
    p.update(extra)
    panels.append(p)


def stat(unit=None, decimals=None, text=False):
    defaults = {"color": {"mode": "fixed", "fixedColor": "text"}}
    if unit:
        defaults["unit"] = unit
    if decimals is not None:
        defaults["decimals"] = decimals
    return {
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": {"reduceOptions": {"calcs": ["lastNotNull"], "fields": "/.*/" if text else "", "values": False},
                    "colorMode": "none", "graphMode": "none", "textMode": "value", "justifyMode": "center",
                    "orientation": "auto", "showPercentChange": False, "wideLayout": True},
    }


def bars(unit=None, stacking="none", horizontal=False, x=None, legend=True, decimals=None, show_value="auto", max_=None):
    defaults = {"color": {"mode": "palette-classic"}, "custom": {"fillOpacity": 85, "lineWidth": 0, "gradientMode": "none",
                                                               "axisSoftMin": 0, "axisPlacement": "auto"}}
    if unit:
        defaults["unit"] = unit
    if decimals is not None:
        defaults["decimals"] = decimals
    if max_ is not None:
        defaults["max"] = max_
    opts = {"orientation": "horizontal" if horizontal else "vertical", "stacking": stacking, "showValue": show_value,
            "groupWidth": 0.7, "barWidth": 0.9, "xTickLabelRotation": 0, "xTickLabelSpacing": 100,
            "legend": {"showLegend": legend, "displayMode": "list", "placement": "bottom"},
            "tooltip": {"mode": "multi", "sort": "none"}}
    if x:
        opts["xField"] = x
    return {"fieldConfig": {"defaults": defaults, "overrides": []}, "options": opts}


# Row 1: DORA tiles -------------------------------------------------------------------------------
panel("stat", "Deploy days a week",
      "Average number of days a week with at least one successful production deployment (Malaysia time). "
      "DORA deployment frequency. Elite: on demand, several a day.",
      (0, 0, 6, 4),
      f"""with {DEPLOYS}
select round(count(distinct date({myt('fin')})) / greatest(timestampdiff(day, $__timeFrom(), $__timeTo()) / 7, 1), 1) as value from _d""",
      **stat(decimals=1))

panel("stat", "Production deploys",
      "Successful production deployments in the range. Each region and worker deployment counts once "
      "(a release to MY, AU, SG, NZ and BN is five).",
      (6, 0, 6, 4),
      f"with {DEPLOYS} select count(*) as value from _d", **stat(decimals=0))

panel("stat", "Lead time for changes",
      "Median time from a pull request's first commit to its production deployment, for pull requests "
      "deployed in the range. DORA lead time for changes.",
      (12, 0, 6, 4),
      f"""with {DEPLOYED_PRS},
_r as (select pr_cycle_time, percent_rank() over (order by pr_cycle_time) as rk from _p)
select max(pr_cycle_time) as value from _r where rk <= 0.5""",
      **stat(unit="m", decimals=1))

panel("stat", "Change failure rate",
      "Needs incidents. DevLake has none for this project yet, so change failure rate and recovery time "
      "are not measured. They are not zero.",
      (18, 0, 6, 4),
      """select case when count(*) = 0 then 'Not measured' else concat(count(*), ' incidents') end as value
from incidents i join project_mapping pm on pm.row_id = i.scope_id where pm.project_name in (${project})""",
      **stat(text=True))

# Row 2: delivery ------------------------------------------------------------------------------------
panel("barchart", "Production deploys per week",
      "Successful production deployments per complete week (Monday to Sunday, Malaysia time). "
      "The running week is left out until it ends.",
      (0, 4, 16, 8),
      f"""with recursive {WEEKS}, {DEPLOYS}
select date_format(w, '%d %b') as week, count(_d.id) as Deploys
from weeks left join _d on {monday('_d.fin')} = w
group by w order by w""",
      **bars(x="week", legend=False, decimals=0))

panel("barchart", "Deploys by environment",
      "Successful production deployments in the range, by Bitbucket environment name without its "
      "PRODUCTION- prefix (MY is PRODUCTION-MY). (pipeline) is a deployment found from a pipeline name.",
      (16, 4, 8, 8),
      f"""with {DEPLOYS}
select coalesce(nullif(replace(env, 'PRODUCTION-', ''), ''), '(pipeline)') as environment, count(*) as Deploys
from _d group by 1 order by 2 desc limit 12""",
      **bars(horizontal=True, x="environment", legend=False, decimals=0))

# Row 3: where the lead time goes --------------------------------------------------------------------
# DevLake's pickup and review stages start at the first PR comment; on Bitbucket that is the Bito review bot,
# seconds after the PR opens, so they are replaced by "opened to merged" from PR timestamps.
STAGES = [("pr_coding_time", "Coding"), ("pr_open_time", "Open, until merged"),
          ("pr_deploy_time", "Merged, until deployed")]
union = "\n  union all ".join(
    f"select {monday('fin')} as w, '{label}' as stage, {col} as v from _p where {col} is not null"
    for col, label in STAGES)
tot = " + ".join(f"coalesce(max(case when m.stage = '{label}' then m.med end), 0)" for _, label in STAGES)
pivot = ",\n  ".join(
    f"round(100 * max(case when m.stage = '{label}' then m.med end) / nullif({tot}, 0)) as `{label}`" for _, label in STAGES)
panel("barchart", "Where the lead time goes",
      "Share of each week's lead time spent in each stage (from the median hours of each stage), for pull requests "
      "deployed in each complete week: first commit to PR "
      "opened (coding), PR opened to merged (review and rework), merged to production deploy. Medians are "
      "per stage, so they do not add up to the lead time exactly. Review is not split further because the "
      "Bito bot comments on most PRs within seconds.",
      (0, 12, 16, 9),
      f"""with recursive {WEEKS}, {DEPLOYED_PRS},
_s as (
  {union}
),
_r as (select w, stage, v, percent_rank() over (partition by w, stage order by v) as rk from _s),
_n as (select w, stage, count(*) as n from _s group by w, stage),
m as (select _r.w, _r.stage, if(max(_n.n) < 5, null, max(_r.v)) as med from _r
      join _n on _n.w = _r.w and _n.stage = _r.stage where _r.rk <= 0.5 group by _r.w, _r.stage)
select date_format(weeks.w, '%d %b') as week,
  {pivot}
from weeks left join m on m.w = weeks.w
group by weeks.w order by weeks.w""",
      **bars(unit="percent", stacking="normal", x="week", decimals=0, show_value="never", max_=100))

panel("barchart", "Open pull requests by age",
      "Pull requests open right now, by days since they were opened. Not affected by the time range.",
      (16, 12, 8, 9),
      f"""select b.bucket as age, count(pr.id) as `Open PRs`
from (select 1 as k, 'Under 1 day' as bucket union all select 2, '1 to 3 days' union all select 3, '3 to 7 days'
      union all select 4, '1 to 4 weeks' union all select 5, 'Over 4 weeks') b
left join (
  select pr.id, case when timestampdiff(hour, pr.created_date, utc_timestamp()) < 24 then 1
                     when timestampdiff(day, pr.created_date, utc_timestamp()) < 3 then 2
                     when timestampdiff(day, pr.created_date, utc_timestamp()) < 7 then 3
                     when timestampdiff(day, pr.created_date, utc_timestamp()) < 28 then 4 else 5 end as k
  from pull_requests pr where pr.status = 'OPEN' and pr.author_id in (${{author}}) and pr.base_repo_id in ({PROJECT_REPOS})
) pr on pr.k = b.k
group by b.k, b.bucket order by b.k""",
      **bars(x="age", legend=False, decimals=0))

# Row 4: flow and CI ---------------------------------------------------------------------------------
panel("barchart", "Pull requests opened and merged per week",
      "Pull requests opened and merged in each complete week (Malaysia time).",
      (0, 21, 12, 8),
      f"""with recursive {WEEKS},
_pr as (select pr.created_date, pr.merged_date from pull_requests pr
        where pr.author_id in (${{author}}) and pr.base_repo_id in ({PROJECT_REPOS}))
select date_format(w, '%d %b') as week,
  (select count(*) from _pr where {monday('_pr.created_date')} = w) as Opened,
  (select count(*) from _pr where _pr.merged_date is not null and {monday('_pr.merged_date')} = w) as Merged
from weeks order by w""",
      **bars(x="week", decimals=0))

panel("barchart", "Pipeline success rate per week",
      "Share of finished Bitbucket pipelines that succeeded, per complete week. Stopped or still-running "
      "pipelines are left out.",
      (12, 21, 12, 8),
      f"""with recursive {WEEKS},
_c as (
  select p.finished_date, p.result from cicd_pipelines p
  join project_mapping pm on pm.row_id = p.cicd_scope_id and pm.`table` = 'cicd_scopes'
  where pm.project_name in (${{project}}) and p.cicd_scope_id in (${{repo}}) and p.result in ('SUCCESS', 'FAILURE')
    and $__timeFilter(p.finished_date)
)
select date_format(w, '%d %b') as week,
  round(100 * sum(_c.result = 'SUCCESS') / nullif(count(_c.result), 0)) as `Succeeded %`
from weeks left join _c on {monday('_c.finished_date')} = w
group by w order by w""",
      **bars(unit="percent", x="week", legend=False, decimals=0))

# Row 5: per repository ------------------------------------------------------------------------------
table = {
    "fieldConfig": {"defaults": {"custom": {"align": "auto", "cellOptions": {"type": "auto"}, "filterable": False}},
                    "overrides": [
                        {"matcher": {"id": "byName", "options": "Median lead time"}, "properties": [{"id": "unit", "value": "m"}, {"id": "decimals", "value": 1}, {"id": "noValue", "value": "not linked"}]},
                        {"matcher": {"id": "byName", "options": "Pipeline success"}, "properties": [{"id": "noValue", "value": "under 5 runs"}]},
                        {"matcher": {"id": "byName", "options": "Pipeline success"}, "properties": [{"id": "unit", "value": "percent"}]},
                        {"matcher": {"id": "byName", "options": "Last production deploy"}, "properties": [{"id": "unit", "value": "dateTimeFromNow"}, {"id": "noValue", "value": "none in range"}]},
                    ]},
    "options": {"showHeader": True, "cellHeight": "sm", "sortBy": [{"displayName": "Production deploys", "desc": True}],
                "footer": {"show": False, "reducer": ["sum"], "fields": ""}},
}
panel("table", "By repository",
      "Per repository in the range: production deployments and deploy days, median lead time for pull "
      "requests deployed (not linked: no merged PR was matched to a production deployment), pull requests "
      "merged, and the share of finished pipelines that succeeded. "
      "Repositories with no activity in the range are left out.",
      (0, 29, 24, 19),
      f"""with {DEPLOYS}, {DEPLOYED_PRS},
_lr as (select repo, pr_cycle_time, percent_rank() over (partition by repo order by pr_cycle_time) as rk from _p),
_lt as (select repo, max(pr_cycle_time) as med from _lr where rk <= 0.5 group by repo),
_dep as (select scope, count(*) as n, count(distinct date({myt('fin')})) as days, max(fin) as last from _d group by scope),
_mer as (select base_repo_id as repo, count(*) as n from pull_requests
         where merged_date is not null and author_id in (${{author}}) and $__timeFilter(merged_date) group by 1),
_ci as (select cicd_scope_id as scope, if(count(*) < 5, null, round(100 * sum(result = 'SUCCESS') / count(*))) as ok, count(*) as runs from cicd_pipelines
        where result in ('SUCCESS', 'FAILURE') and $__timeFilter(finished_date) group by 1)
select substring_index(r.name, '/', -1) as Repository,
  coalesce(_dep.n, 0) as `Production deploys`, coalesce(_dep.days, 0) as `Deploy days`,
  _lt.med as `Median lead time`, coalesce(_mer.n, 0) as `PRs merged`, _ci.ok as `Pipeline success`,
  _dep.last as `Last production deploy`
from repos r
join project_mapping pm on pm.row_id = r.id and pm.`table` = 'repos' and pm.project_name in (${{project}})
left join _dep on _dep.scope = r.id left join _lt on _lt.repo = r.id
left join _mer on _mer.repo = r.id left join _ci on _ci.scope = r.id
where r.id in (${{repo}}) and (_dep.n is not null or _mer.n is not null or _ci.runs is not null)
order by 2 desc, 5 desc""",
      **table)

dashboard = {
    "uid": "mm-devex",
    "title": "MoneyMatch DevEx",
    "tags": ["moneymatch", "dora", "devex"],
    "timezone": "Asia/Kuala_Lumpur",
    "editable": True,
    "graphTooltip": 1,
    "refresh": "",
    "time": {"from": "now-90d", "to": "now"},
    "timepicker": {},
    "schemaVersion": 41,
    "templating": {"list": [
        {"name": "project", "label": "Project", "type": "query", "datasource": DS,
         "query": "select distinct project_name from project_mapping order by 1", "refresh": 1,
         "current": {"text": "moneymatch", "value": "moneymatch"}, "multi": False, "includeAll": False},
        {"name": "repo", "label": "Repository", "type": "query", "datasource": DS,
         "query": "select substring_index(r.name, '/', -1) as __text, r.id as __value from repos r "
                  "join project_mapping pm on pm.row_id = r.id and pm.`table` = 'repos' "
                  "where pm.project_name in (${project}) order by 1",
         "refresh": 1, "multi": True, "includeAll": True, "current": {"text": ["All"], "value": ["$__all"]}, "sort": 0},
        {"name": "author", "label": "PR author", "type": "query", "datasource": DS,
         "description": "Filters the pull request panels and the lead time. Deployments and pipelines are not per author.",
         "query": "select max(pr.author_name) as __text, pr.author_id as __value from pull_requests pr "
                  "join project_mapping pm on pm.row_id = pr.base_repo_id and pm.`table` = 'repos' "
                  "where pm.project_name in (${project}) and pr.created_date >= date_sub(utc_timestamp(), interval 1 year) "
                  "and pr.author_id <> '' group by pr.author_id order by 1",
         "refresh": 1, "multi": True, "includeAll": True, "current": {"text": ["All"], "value": ["$__all"]}, "sort": 0},
    ]},
    "panels": panels,
}
# Grafana quotes a single-value variable only with a format; :sqlstring quotes and escapes every value.
out = json.dumps(dashboard, indent=1)
for var in ("project", "repo", "author"):
    out = out.replace("${" + var + "}", "${" + var + ":sqlstring}")
print(out)
