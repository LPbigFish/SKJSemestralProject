#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"

case "${1:-generate}" in
    generate)
        echo "Generating test files..."
        for spec in 10:10mb_test.bin 99:99mb_test.bin 150:150mb_test.bin; do
            size="${spec%%:*}"
            name="${spec##*:}"
            echo "  $name ($size MB)..."
            dd if=/dev/urandom of="$DIR/$name" bs=1M count="$size" 2>/dev/null
        done
        echo "Done."
        ;;
    clean)
        echo "Removing test files..."
        rm -f "$DIR"/10mb_test.bin "$DIR"/99mb_test.bin "$DIR"/150mb_test.bin
        echo "Done."
        ;;
    *)
        echo "Usage: $0 [generate|clean]"
        exit 1
        ;;
esac
