# second-deposit-igaming

A Claude Code plugin with one skill, `second-deposit`. It reads back-office exports from a casino or betting operator (deposits with all attempts, and if you have them, withdrawals, bonuses, bets and players) and shows why first-time depositors (FTD) do not make a second deposit: one of 12 reasons for each FTD, missing second deposits and Sum Dep per reason against the norm of similar players, 24 metrics with definitions, segments with a real gap, and today's list of recent FTDs with an action for each player's state and country rules. Made for CRM and retention, product and payments teams, and the analysts who prepare the exports.

## Install

```text
/plugin marketplace add igamingsychov/sychov-igaming-skills
/plugin install second-deposit-igaming@sychov-igaming-skills
```

Then run `/reload-plugins` or start a new session.

## Use

Try the demo first: `show the second-deposit skill demo`. Claude creates a fictional workbook and builds a report from it. Then, for example: `analyze the second deposit from the exports in ~/Downloads/exports`. You can also run the skill directly: `/second-deposit-igaming:second-deposit <folder or file>`.

## Requirements

Claude Code and `python3` 3.9 or newer. No third-party libraries and no internet access are needed. Exports as CSV or XLSX with any column names; the minimum is deposits for 60-120 days with all attempts.

## What it runs

The skill asks Claude to run the Python scripts in its `scripts` folder on your exports. Results go to a `second-deposit` folder next to the exports. Claude sees column names, formats and totals, not player rows; player lists are written to files. The skill sends nothing anywhere and does not open spreadsheets by link. A daily scheduled run is added to the system scheduler only after your explicit consent.

## Notes

- A plugin's folder changes with every plugin version, so a scheduled daily run that points into it stops working after an update. For scheduled runs, install the skill with `git clone` (see the repository), or ask Claude to recreate the task after each plugin update.
- If you already installed the skill with `git clone` into `~/.claude/skills/second-deposit`, use one copy only.
- The skill instructions, references and the export template's sheet names are in Russian. Reports can be in English, Ukrainian or Russian.
- Full documentation and limitations: [github.com/igamingsychov/second-deposit-igaming](https://github.com/igamingsychov/second-deposit-igaming). Skill page: [sychov-igaming.com/en/skills/second-deposit](https://sychov-igaming.com/en/skills/second-deposit/).

## License and author

MIT, see [LICENSE](LICENSE). Author: [Yevhen Sychov](https://sychov-igaming.com).

21+. Material for gambling industry professionals, not gambling advertising.
