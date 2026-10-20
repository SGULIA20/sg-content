#!/bin/zsh
# Installs the two Mac jobs for the paste-and-drop flow (docs/spec-gemini-clips.md): inbox tick every 2 minutes, prompt packs at 07:00 Lagos.
set -e
PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3
ROOT="$HOME/sg-content"
AGENTS="$HOME/Library/LaunchAgents"
LOGS="$ROOT/logs"
mkdir -p "$AGENTS" "$LOGS"

write_plist() {   # name, interval-or-calendar xml, program args xml
cat > "$AGENTS/$1.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$1</string>
  <key>ProgramArguments</key><array><string>$PY</string>$3</array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>EnvironmentVariables</key><dict><key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string></dict>
  $2
  <key>StandardOutPath</key><string>$LOGS/$1.log</string>
  <key>StandardErrorPath</key><string>$LOGS/$1.log</string>
</dict></plist>
EOF
}

write_plist com.sgcontent.inbox "<key>StartInterval</key><integer>120</integer>" "<string>-m</string><string>engine.inbox</string><string>--tick</string>"
write_plist com.sgcontent.packs "<key>StartCalendarInterval</key><dict><key>Hour</key><integer>7</integer><key>Minute</key><integer>0</integer></dict>" \
  "<string>-m</string><string>engine.produce</string><string>--mode</string><string>pack</string><string>--max</string><string>2</string>"

for j in com.sgcontent.inbox com.sgcontent.packs; do
  launchctl bootout "gui/$(id -u)/$j" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$AGENTS/$j.plist"
done
launchctl list | grep sgcontent
