#!/bin/bash

# The array of results passed to ffmpeg in the end
results=()


# loop over arguments and add them to $results
for FILE in "$@"; do
  
    if [[ -f "$FILE" ]]; then
        # Ist eine Datei, also pfad manipulation anwenden
        FILE="/mnt/mainArray/pxe/Pi/192.168.55.70/root/home/pi/.octoprint/timelapse/${FILE##*/}"
    fi
    results+="$FILE "
done
echo "${results[@]}" > /tmp/octoprint.rewrite.log
exec ssh marcel@xeon.lan "/usr/bin/ffmpeg ${results[@]}"