# Esecuzione della suite dentro la sandbox DSH su Windows.
#
# Serve perche' Python 3.13+ applica davvero il mode 0o700 di
# tempfile.mkdtemp(): il token ristretto della sandbox non supera il
# controllo di accesso su quella DACL e ogni test con tmp_path fallisce
# con "Permission denied". Lo shim in tools/pytest_shim riporta il mode
# a 0o777 (su Windows i bit POSIX non contano).

$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot

$env:PYTHONPATH = Join-Path $root 'tools\pytest_shim'
$env:PYTHONDONTWRITEBYTECODE = '1'

$python = Join-Path $root '.venv\Scripts\python.exe'

if (-not (Test-Path $python)) {
    $python = 'python'
}

& $python -m pytest -p no:cacheprovider @args

exit $LASTEXITCODE
