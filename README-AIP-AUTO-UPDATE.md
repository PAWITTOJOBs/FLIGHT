# Thailand AIP automatic updater

Runs every Monday at 18:00 Thailand time.

GitHub Actions cron uses UTC, so the workflow uses:

```yaml
- cron: "0 11 * * 1"
```

The updater:

1. Reads `https://aip.caat.or.th/`.
2. Detects **Currently Effective Issue**.
3. Does not activate **Next Issues** before their effective date.
4. Downloads selected AIP HTML pages to `data/aip-thailand/current/html/`.
5. Writes `data/aip-thailand/current/metadata.json`.
6. Commits only when the source snapshot changes.

No Claude, OpenAI, or other AI service is used.

## Install

Copy `.github/` and `scripts/` into the root of your repository and push once.

Then enable:

**Settings → Actions → General → Workflow permissions → Read and write permissions**

You can also run it manually from:

**Actions → Update Thailand AIP → Run workflow**

## Note

This workflow mirrors authoritative AIP source pages. It does not yet convert every AIP table into the JavaScript arrays embedded in FLIGHT-PLANNER. That deterministic parser can be added as the next step and run in the same Action without AI.
