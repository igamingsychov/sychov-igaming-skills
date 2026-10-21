# watch-igaming

A Claude Code plugin with one skill, `watch`. It watches a whole video, from a link (video hosting, screen and meeting recordings, a direct mp4) or a local file such as a screen recording. It takes subtitles with yt-dlp or transcribes the speech locally with Whisper, extracts frames with ffmpeg where the scene changes, matches the words with the screen by timecode, and returns a plain review, a QA table, a competitor comparison, a UX audit, meeting minutes or lecture notes. Made for casino and betting teams (QA, product, CRM), and works with any video.

## Install

```text
/plugin marketplace add igamingsychov/sychov-igaming-skills
/plugin install watch-igaming@sychov-igaming-skills
```

Then run `/reload-plugins` or start a new session.

## Use

Ask in plain words, for example `watch this video and give me a review: <link>` or `watch the recording /Users/me/Movies/walkthrough.mov and build a QA table`. You can also run the skill directly: `/watch-igaming:watch <link>`.

## Requirements

Claude Code on macOS or Linux, plus `yt-dlp` (only for links), `ffmpeg` and `whisper` (the openai-whisper package):

- macOS: `brew install yt-dlp ffmpeg openai-whisper`
- Linux: `sudo apt install ffmpeg pipx`, then `pipx install yt-dlp` and `pipx install openai-whisper`

## What it runs

The skill asks Claude to run `yt-dlp` (downloads subtitles, audio or video from the link you give), `ffmpeg` (extracts audio and frames) and `whisper` (speech recognition on your machine). Working files go to `/tmp/watch/<slug>`. The skill publishes and sends nothing without your explicit request. If a tool is missing, Claude offers to install it and shows the command.

## Notes

- If you already installed the skill with `git clone` into `~/.claude/skills/watch`, remove that copy to avoid having the skill twice.
- The skill instructions and table templates are written in Russian.
- Full documentation, limitations and an example QA table: [github.com/igamingsychov/watch-igaming](https://github.com/igamingsychov/watch-igaming). Skill page: [sychov-igaming.com/en/skills/watch](https://sychov-igaming.com/en/skills/watch/).

## License and author

MIT, see [LICENSE](LICENSE). Author: [Yevhen Sychov](https://sychov-igaming.com).
