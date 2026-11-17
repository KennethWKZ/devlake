# MoneyMatch dashboards

`devex_dashboard.py` builds the **MoneyMatch DevEx** Grafana dashboard (uid `mm-devex`, folder `MoneyMatch`):
DORA tiles, production deploys per week and by environment, where the lead time goes, open PR age, PR flow,
pipeline success rate and a per-repository table. `moneymatch-devex.json` is its output.

```bash
python3 grafana/moneymatch/devex_dashboard.py > grafana/moneymatch/moneymatch-devex.json
# save to Grafana: POST /api/dashboards/db with {"dashboard": <json>, "folderUid": "moneymatch", "overwrite": true}
```

Not provisioned from the image on purpose: it lives in Grafana's database (the `grafana-storage` volume) so it
can be edited in the UI; re-run the script and save again to reset it.

Notes on the data:
- Weeks run Monday to Sunday in Malaysia time; weekly charts show complete weeks only.
- DevLake's PR pickup and review stages start at the first PR comment. On our Bitbucket that is the Bito
  review bot, seconds after a PR opens, so the dashboard uses "opened to merged" instead.
- Metrics come from PRs, deployments and pipelines, not commits, so GitHub forks' upstream history does not count.
- Change failure rate needs incidents; none are collected yet, so it reads "Not measured".
