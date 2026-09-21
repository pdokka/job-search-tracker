#!/bin/zsh
cd -- "${0:A:h}" || exit 1
"./.venv/bin/python3" "./run.py" refresh
result=$?
if [[ -t 0 ]]; then
  printf '\nPress Return to close this window.\n'
  read -r answer
fi
exit "$result"
