#!/bin/env bash
# Warte auf FiFo Datei und schreibe suspend/resume
RUNTIME_PATH="${XDG_RUNTIME_DIR:-/tmp}"
FIFO_FILE="$RUNTIME_PATH/mqttScript-logind.fifo"
if [ ! -f "$FIFO_FILE" ]; then
    echo "FIFO Datei $FIFO_FILE nicht gefunden. Beende."
    exit 1
fi

while true; do
    if read -r line < "$FIFO_FILE"; then
        case "$line" in
            "SUSPEND")
                echo "SUSPEND empfangen."
                exit 0
                ;;
            "RESUME")
                echo "RESUME empfangen."
                echo "RESUME verarbeitet."
                exit 0
                ;;
            *)
                echo "Unbekannter Befehl: $line"
                exit 0
                ;;
        esac
    fi
done