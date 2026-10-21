# sychov-igaming-skills

A Claude Code plugin marketplace with two open skills for casino and betting teams. Each plugin holds one skill; the skill repositories stay the source, and this repository packs them so you can install and update them with the `/plugin` command.

## Install

In a Claude Code session:

```text
/plugin marketplace add igamingsychov/sychov-igaming-skills
/plugin install watch-igaming@sychov-igaming-skills
/plugin install second-deposit-igaming@sychov-igaming-skills
```

From the shell:

```bash
claude plugin marketplace add igamingsychov/sychov-igaming-skills
claude plugin install watch-igaming@sychov-igaming-skills
claude plugin install second-deposit-igaming@sychov-igaming-skills
```

Then run `/reload-plugins` or start a new session. To get new versions later, run `claude plugin marketplace update sychov-igaming-skills` and `claude plugin update <plugin>@sychov-igaming-skills`, or turn on auto-update for this marketplace in `/plugin`.

If you already installed one of these skills with `git clone` into `~/.claude/skills`, remove that copy so the skill is not loaded twice.

## Plugins

### watch-igaming

Watches a whole video, from a link or a local file such as a screen recording. It takes subtitles with yt-dlp or transcribes the speech locally with Whisper, extracts frames with ffmpeg where the scene changes, matches the words with the screen by timecode, and returns a plain review, a QA table, a competitor comparison, a UX audit, meeting minutes or lecture notes. For QA, product and CRM teams.

- Run: ask in plain words (`watch this video and give me a review: <link>`) or `/watch-igaming:watch <link>`
- Needs: macOS or Linux with `yt-dlp`, `ffmpeg` and `whisper`
- Repository: [igamingsychov/watch-igaming](https://github.com/igamingsychov/watch-igaming)
- Page: [sychov-igaming.com/en/skills/watch](https://sychov-igaming.com/en/skills/watch/)

### second-deposit-igaming

Shows why first-time depositors (FTD) do not make a second deposit, from back-office exports: one of 12 reasons for each FTD, missing second deposits and Sum Dep per reason against the norm of similar players, 24 metrics, segments with a real gap, and a daily list of recent FTDs for the CRM with an action for each. The calculation runs in local Python scripts; Claude sees column names and totals, not player rows. For CRM and retention, product and payments teams.

- Run: `show the second-deposit skill demo`, then `analyze the second deposit from the exports in <folder>`, or `/second-deposit-igaming:second-deposit <folder>`
- Needs: `python3` 3.9 or newer
- Repository: [igamingsychov/second-deposit-igaming](https://github.com/igamingsychov/second-deposit-igaming)
- Page: [sychov-igaming.com/en/skills/second-deposit](https://sychov-igaming.com/en/skills/second-deposit/)
- A scheduled daily run points to the skill folder, and a plugin's folder changes with each version. For scheduled runs, the `git clone` install from the repository is the better fit.

## Layout

```text
.claude-plugin/marketplace.json        the marketplace: name, owner, plugin list
plugins/watch-igaming/                 plugin: .claude-plugin/plugin.json, README, LICENSE
  skills/watch/                        SKILL.md, templates/, examples/
plugins/second-deposit-igaming/        plugin: .claude-plugin/plugin.json, README, LICENSE
  skills/second-deposit/               SKILL.md, references/, scripts/, examples/
sync.sh                                copies the skill files from the skill repositories
```

## Updating the plugins (maintainer)

The skills are edited in their own repositories. To bring the changes here, keep `watch-igaming` and `second-deposit-igaming` next to this repository and run:

```bash
./sync.sh
```

The script copies `SKILL.md` and the skill's files (without `.git`, `.DS_Store`, READMEs, `install.sh` and README images), copies `LICENSE` to the plugin, checks that every `templates/`, `examples/`, `references/` and `scripts/` path named in the skill exists, and raises the patch version in `plugin.json` of each plugin whose files changed, so that installed copies update. `./sync.sh --no-bump` copies without changing versions. Then run `claude plugin validate .`, review `git diff` and commit.

## License

MIT, see [LICENSE](LICENSE).

## Author

[Yevhen Sychov](https://sychov-igaming.com)

21+. Material for gambling industry professionals, not gambling advertising.
