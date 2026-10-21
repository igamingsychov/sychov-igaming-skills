#!/usr/bin/env bash
# Copies the current skill files from the skill repositories into the plugins of this marketplace.
#   ./sync.sh            copy, then raise the patch version of each plugin whose files changed
#   ./sync.sh --no-bump  copy without changing versions
# Sources: ../watch-igaming and ../second-deposit-igaming next to this repository.
# Another folder that holds both skill repositories: SKILLS_SRC=/path ./sync.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_ROOT="${SKILLS_SRC:-$(dirname "$ROOT")}"
BUMP=1

for arg in "$@"; do
  case "$arg" in
    --no-bump) BUMP=0 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg (see ./sync.sh --help)"; exit 1 ;;
  esac
done

# plugin name | source repository folder | skill folder name (the "name" in SKILL.md)
PLUGINS=(
  "watch-igaming|watch-igaming|watch"
  "second-deposit-igaming|second-deposit-igaming|second-deposit"
)

# No macOS metadata files (._*) inside tar streams.
export COPYFILE_DISABLE=1

# Prints the source files to copy, NUL-separated, relative to the source folder.
# Files that belong to the repository page and not to the skill are skipped:
# README*, LICENSE (copied to the plugin root instead), install.sh, git files, README images.
list_files() {
  local src="$1"
  if git -C "$src" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    (cd "$src" && git ls-files -z --cached --others --exclude-standard)
  else
    (cd "$src" && find . -path ./.git -prune -o -type f -print0)
  fi | while IFS= read -r -d '' f; do
    f="${f#./}"
    case "$f" in
      README.md|README.*.md|LICENSE|install.sh|.gitignore|.gitattributes) continue ;;
      .git/*|.github/*) continue ;;
      .DS_Store|*/.DS_Store|._*|*/._*|__pycache__/*|*/__pycache__/*|*.pyc) continue ;;
      examples/*.png) continue ;;
    esac
    [ -f "$src/$f" ] || continue
    printf '%s\0' "$f"
  done
}

# Hash of a plugin's skills folder and LICENSE, to tell whether a sync changed anything.
plugin_hash() {
  local dir="$1"
  if [ -d "$dir/skills" ]; then
    (cd "$dir/skills" && find . -type f -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256 | cut -d' ' -f1)
  else
    echo "no-skills"
  fi
  if [ -f "$dir/LICENSE" ]; then
    shasum -a 256 "$dir/LICENSE" | cut -d' ' -f1
  else
    echo "no-license"
  fi
}

bump_patch() {
  python3 - "$1" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
parts = str(data.get("version", "0.0.0")).split(".")
parts[-1] = str(int(parts[-1]) + 1)
data["version"] = ".".join(parts)
with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write("\n")
print(data["version"])
PY
}

status=0
for entry in "${PLUGINS[@]}"; do
  IFS='|' read -r plugin repo skill <<<"$entry"
  src="$SRC_ROOT/$repo"
  plugin_dir="$ROOT/plugins/$plugin"
  dest="$plugin_dir/skills/$skill"
  manifest="$plugin_dir/.claude-plugin/plugin.json"

  if [ ! -f "$src/SKILL.md" ]; then
    echo "$plugin: no SKILL.md in $src, skipped"
    status=1
    continue
  fi
  if git -C "$src" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    rev="$(git -C "$src" rev-parse --short HEAD)"
    if [ -n "$(git -C "$src" status --porcelain)" ]; then
      echo "$plugin: note, $repo has uncommitted changes, copying the files as they are on disk"
    fi
  else
    rev="not a git repository"
  fi

  before="$(plugin_hash "$plugin_dir")"

  list="$(mktemp)"
  list_files "$src" >"$list"
  case "$dest" in
    "$ROOT"/plugins/*/skills/*) rm -rf "$dest" ;;
    *) echo "Unexpected destination $dest, stopped"; exit 1 ;;
  esac
  mkdir -p "$dest"
  (cd "$src" && tar -c -f - --null -T "$list") | (cd "$dest" && tar -x -f -)
  rm -f "$list"
  if [ -f "$src/LICENSE" ]; then cp "$src/LICENSE" "$plugin_dir/LICENSE"; fi

  # Every templates/, examples/, references/ or scripts/ path named in the skill's Markdown must exist.
  missing=""
  while IFS= read -r ref; do
    [ -e "$dest/$ref" ] || missing="$missing $ref"
  done < <(find "$dest" -name '*.md' -exec grep -ohE '(templates|examples|references|scripts)/[A-Za-z0-9_.-]+\.[A-Za-z0-9]+' {} + | sort -u)
  if [ -n "$missing" ]; then
    echo "$plugin: WARNING, files named in the skill but not copied:$missing"
    status=1
  fi

  after="$(plugin_hash "$plugin_dir")"
  count="$(find "$dest" -type f | wc -l | tr -d ' ')"
  version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("version", "not set"))' "$manifest" 2>/dev/null || echo "no plugin.json")"

  if [ "$before" = "$after" ]; then
    echo "$plugin: no changes ($count files from $repo @ $rev, version $version)"
  elif [ "$BUMP" -eq 1 ] && [ -f "$manifest" ]; then
    version="$(bump_patch "$manifest")"
    echo "$plugin: updated, $count files from $repo @ $rev, version raised to $version"
  else
    echo "$plugin: updated, $count files from $repo @ $rev, version $version unchanged"
  fi
done

find "$ROOT" -path "$ROOT/.git" -prune -o \( -name .DS_Store -o -name '._*' \) -type f -print -delete

echo ""
echo "Next: claude plugin validate $ROOT, then review with git status and git diff, then commit."
exit "$status"
