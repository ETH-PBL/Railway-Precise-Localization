#!/bin/bash
MD5_HASH=06eedad2341ad7156de5a992dcce194c
ZIP_URL=https://zenodo.org/record/7823090/files/Railway-Precise-Localization-data.zip
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
ZIP_PATH="$SCRIPT_DIR/full_dataset.zip"

EXISTING_MD5=($(md5sum $ZIP_PATH))
[[ -f $ZIP_PATH && "$MD5_HASH" = "$EXISTING_MD5" ]] && echo "Dataset already downloaded" || wget $ZIP_URL -O $ZIP_PATH

TMP=$(mktemp -d)
unzip full_dataset.zip -d $TMP
cp -R $TMP/Railway-Precise-Localization-data/* .
rm -r $TMP
