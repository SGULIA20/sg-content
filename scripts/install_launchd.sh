#!/bin/zsh
# Installs the Mac jobs (local time = Lagos, UTC+1):
#   com.sgcontent.produce            04:00 daily      make what the buffer needs (Shorts), upload scheduled to YouTube
#   com.sgcontent.publish-sglearning 08:30 daily      13:00 IST: Instagram Reel + Story + Threads for Learning with SG
#   com.sgcontent.publish-arthvan    17:00 Mon/Wed/Fri 21:30 IST: same for SG-MYTH-WORLD
#   com.sgcontent.inbox              every 2 minutes  the optional Gemini-clip path (only acts when a prompt pack is waiting)
# Set PUSH=1 when the founder has allowed automatic pushes of finished Shorts to GitHub (Instagram and Threads need the raw URL).
set -e
PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3
ROOT="$HOME/sg-content"
AGENTS="$HOME/Library/LaunchAgents"
LOGS="$ROOT/logs"
PUSH="${PUSH:-0}"
mkdir -p "$AGENTS" "$LOGS"

write_plist() {   # name, schedule xml, program args xml
cat > "$AGENTS/$1.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$1</string>
  <key>ProgramArguments</key><array><string>$PY</string>$3</array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>SG_PUSH_FROM_MAC</key><string>$PUSH</string>
  </dict>
  $2
  <key>StandardOutPath</key><string>$LOGS/$1.log</string>
  <key>StandardErrorPath</key><string>$LOGS/$1.log</string>
</dict></plist>
EOF
}

cal() { echo "<dict><key>Hour</key><integer>$1</integer><key>Minute</key><integer>$2</integer>$3</dict>"; }

write_plist com.sgcontent.produce "<key>StartCalendarInterval</key>$(cal 4 0)" \
  "<string>-m</string><string>engine.produce</string><string>--max</string><string>3</string>"
write_plist com.sgcontent.publish-sglearning "<key>StartCalendarInterval</key>$(cal 8 30)" \
  "<string>-m</string><string>engine.publish</string><string>--channel</string><string>sglearning</string>"
write_plist com.sgcontent.publish-arthvan "<key>StartCalendarInterval</key><array>$(cal 17 0 '<key>Weekday</key><integer>1</integer>')$(cal 17 0 '<key>Weekday</key><integer>3</integer>')$(cal 17 0 '<key>Weekday</key><integer>5</integer>')</array>" \
  "<string>-m</string><string>engine.publish</string><string>--channel</string><string>arthvan</string>"
write_plist com.sgcontent.inbox "<key>StartInterval</key><integer>120</integer>" \
  "<string>-m</string><string>engine.inbox</string><string>--tick</string>"

launchctl bootout "gui/$(id -u)/com.sgcontent.packs" 2>/dev/null || true
rm -f "$AGENTS/com.sgcontent.packs.plist"
for j in com.sgcontent.produce com.sgcontent.publish-sglearning com.sgcontent.publish-arthvan com.sgcontent.inbox; do
  launchctl bootout "gui/$(id -u)/$j" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$AGENTS/$j.plist"
done
launchctl list | grep sgcontent
