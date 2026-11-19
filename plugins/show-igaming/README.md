# show-igaming

A Claude Code plugin with one skill, `show`. Give it a site link and the steps in plain words ("tap Slots at the bottom, then More next to All providers"). Claude opens the mobile version of the site as an iPhone 15 screen, finds and taps each element, checks that every tap changed the screen, and builds a finished vertical tutorial video for players: highlight frames taken from the page itself, captions in your languages, blurred personal data, your brand colours, logo and fonts. Made for support teams that answer "how do I deposit, withdraw or find a game", and for CRM and product teams that explain a flow or a release.

## Install

```text
/plugin marketplace add igamingsychov/sychov-igaming-skills
/plugin install show-igaming@sychov-igaming-skills
```

Then run `/reload-plugins` or start a new session.

## Use

Try the demo first: `make a demo video with the show skill`. Claude starts a local test page with an invented player cabinet, records a top-up flow and renders the video. Then, for example: `make a video guide: how to find a game through search on https://your-site/en`. You can also run the skill directly: `/show-igaming:show <link and steps>`.

## Requirements

Claude Code on macOS or Linux, `python3`, `ffmpeg` and Google Chrome (Chromium and Edge work too). Windows is not supported yet.

## What it runs

The skill asks Claude to run the Python scripts in its `scripts` folder. They drive a separate headless browser with the iPhone screen size, record the steps and render the video with ffmpeg. Everything stays on your machine; nothing is uploaded.

For steps behind a login, Claude opens a separate Chrome window with its own profile folder. You sign into a test account yourself (regular or VIP, one folder each) and close the window; the skill never types passwords or codes, and your main Chrome profile is not used. Payment, withdrawal and bet buttons are never pressed: the video ends with a highlight on that button. Emails, phone numbers, card numbers, IBANs and player IDs are blurred inside the page before frames are captured. A proof sheet is checked before every render.

## Notes

- The profile folders keep the test account signed in. Keep them out of shared folders and repositories; deleting a folder signs that account out.
- Bot checks are passed by you in the sign-in window. Payment forms that open in a frame of another site are not blurred automatically; Claude adds blur zones by hand, visible on the proof sheet.
- If you already installed the skill with `git clone` into `~/.claude/skills/show`, use one copy only.
- The skill instructions are in Russian. Videos can be in any language of the site.
- Full documentation and limitations: [github.com/igamingsychov/show-igaming](https://github.com/igamingsychov/show-igaming). Skill page: [sychov-igaming.com/en/skills/show](https://sychov-igaming.com/en/skills/show/).

## License and author

MIT, see [LICENSE](LICENSE). Author: [Yevhen Sychov](https://sychov-igaming.com).

21+. Material for gambling industry professionals, not gambling advertising.
