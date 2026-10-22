#!/bin/sh
# The Mac presses GitHub's "Run workflow" buttons at the right minutes (22 Oct 2026: GitHub's own scheduler fired almost none of the
# day's runs). Each job only dispatches a workflow through the GitHub CLI; the engines never post or upload twice, so a run that
# GitHub also starts on its own is harmless. Lagos time is UTC+1 all year.
#
#   sh scripts/install_triggers.sh            install (or reinstall) the trigger agents
#   sh scripts/install_triggers.sh --remove   remove them
set -e
DIR="$HOME/Library/LaunchAgents"
GH="$(command -v gh || echo /opt/homebrew/bin/gh)"
LOG="$HOME/sg-content/logs/triggers.log"
mkdir -p "$DIR" "$(dirname "$LOG")"

remove_all() {
  for f in "$DIR"/com.sgcontent.trigger-*.plist; do
    [ -f "$f" ] || continue
    launchctl unload "$f" 2>/dev/null || true
    rm -f "$f"
  done
}

# write_job NAME "HH:MM[,HH:MM...] (Lagos)" REPO WORKFLOW [extra args...]
write_job() {
  name="$1"; times="$2"; repo="$3"; wf="$4"; shift 4
  plist="$DIR/com.sgcontent.trigger-$name.plist"
  cal=""
  for t in $(echo "$times" | tr ',' ' '); do
    h=${t%%:*}; m=${t##*:}
    cal="$cal<dict><key>Hour</key><integer>$((10#$h))</integer><key>Minute</key><integer>$((10#$m))</integer></dict>"
  done
  args=""
  for a in "$@"; do args="$args<string>$a</string>"; done
  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.sgcontent.trigger-$name</string>
  <key>ProgramArguments</key><array><string>$GH</string><string>workflow</string><string>run</string><string>$wf</string><string>-R</string><string>$repo</string>$args</array>
  <key>StartCalendarInterval</key><array>$cal</array>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict></plist>
EOF
  launchctl load "$plist"
}

remove_all
if [ "$1" = "--remove" ]; then echo "trigger agents removed"; exit 0; fi

SG="SGULIA20/sg-content"; AM="SGULIA20/arthvan-media"
# Lagos times = UTC + 1
write_job produce            "08:15,09:15,14:45"  "$SG" produce.yml
write_job publish-sglearning "09:35,10:35"        "$SG" publish.yml -f channel=sglearning
write_job publish-arthvan    "17:05,18:05"        "$SG" publish.yml -f channel=arthvan
write_job evening            "21:05"              "$SG" evening.yml
write_job linkedin           "04:40,06:40"        "$AM" linkedin-personal.yml -f mode=post
write_job daily-post         "15:40,16:40"        "$AM" daily-post.yml -f mode=post
write_job status             "21:30"              "$AM" status.yml
write_job telegram           "$(i=0; s=""; while [ $i -lt 24 ]; do for m in 02 17 32 47; do s="$s,$(printf '%02d' $i):$m"; done; i=$((i+1)); done; echo "${s#,}")" "$AM" telegram-commands.yml
echo "installed:"; launchctl list | grep com.sgcontent.trigger- | awk '{print "  " $3}'
