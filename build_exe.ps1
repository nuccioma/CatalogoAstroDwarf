# build_exe.ps1 - Crea una versione "compatta" (eseguibile Windows
# autonomo, senza bisogno di Python installato) del Catalogo Sessioni
# Astronomiche Dwarf II / Dwarf 3, pronta da inviare ad amici.
#
# USO: apri PowerShell in QUESTA cartella (quella che contiene sia
# "dwarf_catalog\" che questo script) ed esegui:
#
#     .\build_exe.ps1
#
# Serve una connessione Internet (scarica PyInstaller e le dipendenze) e
# richiede qualche minuto. Il risultato e' uno zip pronto da condividere:
# CatalogoAstroDwarf_portable.zip - gli amici lo estraggono e avviano
# CatalogoAstroDwarf.exe, senza installare nulla.
#
# NOTA SULLA DIMENSIONE: "compatta" vuol dire "senza installazioni per chi
# la riceve", non piccola in megabyte: PyQt6 + astropy + astroquery +
# photutils portano il pacchetto finale sui 400-700 MB. E' normale.
#
# Le funzioni che si appoggiano a programmi esterni (Siril, WSL +
# Astrometry.net) NON vengono incluse in questo pacchetto: restano
# installazioni separate e opzionali, come sul tuo PC (vedi LEGGIMI_AMICI.txt
# e LEGGIMI_AMICI_EN.txt, copiati dentro il pacchetto finale come
# Leggimi.txt e Readme.txt).

$ErrorActionPreference = "Stop"

$root = $PSScriptRoot
$appDir = Join-Path $root "dwarf_catalog"
$venvDir = Join-Path $root ".venv_build"
$distDir = Join-Path $root "dist"
$buildDir = Join-Path $root "build"
$outName = "CatalogoAstroDwarf"

if (-not (Test-Path $appDir)) {
    Write-Error "Non trovo la cartella '$appDir'. Esegui questo script dalla cartella che contiene dwarf_catalog\."
}

Write-Host "1/6 - Creo un ambiente Python pulito per la build ($venvDir)..." -ForegroundColor Cyan
if (Test-Path $venvDir) { Remove-Item -Recurse -Force $venvDir }
if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 -m venv $venvDir
} else {
    & python -m venv $venvDir
}
$pyExe = Join-Path $venvDir "Scripts\python.exe"
if (-not (Test-Path $pyExe)) {
    Write-Error "Creazione dell'ambiente Python non riuscita: verifica di avere Python 3 installato."
}

Write-Host "2/6 - Installo le dipendenze (puo' richiedere qualche minuto)..." -ForegroundColor Cyan
& $pyExe -m pip install --upgrade pip
& $pyExe -m pip install -r (Join-Path $appDir "requirements.txt")
& $pyExe -m pip install pyinstaller

Write-Host "3/6 - Creo l'eseguibile con PyInstaller..." -ForegroundColor Cyan
if (Test-Path $distDir) { Remove-Item -Recurse -Force $distDir }
if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir }

# NOTA su "--collect-all pyvo": pyvo (dipendenza di astroquery, usata per il
# pulsante Astrometria/SIMBAD) include un'iconcina (pyvo/samp/data/
# astropy_icon.png) caricata da codice suo interno all'importazione. Senza
# dirlo esplicitamente a PyInstaller, quel file non viene incluso nel
# pacchetto (PyInstaller include automaticamente solo il codice Python
# individuato staticamente, non i file "dati" letti a runtime): il risultato
# era che l'eseguibile compilato, aprendo per la prima volta l'astrometria
# SIMBAD, provava a scaricare quell'icona da un indirizzo di astropy.org
# ormai non più raggiungibile e si chiudeva di colpo (il codice sorgente
# lanciato con "python main.py" non aveva questo problema perché lì pyvo è
# semplicemente installato per intero sul disco, icona compresa).
& $pyExe -m PyInstaller `
    --name $outName `
    --onedir `
    --windowed `
    --noconfirm `
    --clean `
    --collect-all astropy `
    --collect-all astroquery `
    --collect-all photutils `
    --collect-all pyvo `
    (Join-Path $appDir "main.py")

$pkgDir = Join-Path $distDir $outName
if (-not (Test-Path $pkgDir)) {
    Write-Error "PyInstaller non ha prodotto l'output atteso in '$pkgDir'."
}

Write-Host "4/6 - Ripulisco eventuali dati/impostazioni personali residui..." -ForegroundColor Cyan
foreach ($item in @("settings.ini", "catalogo_dwarf.db", "thumbnails", "logs")) {
    $p = Join-Path $pkgDir $item
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}

Write-Host "5/6 - Copio Leggimi.txt, Readme.txt e il codice sorgente per gli amici..." -ForegroundColor Cyan
$readmeIt = Join-Path $root "LEGGIMI_AMICI.txt"
if (Test-Path $readmeIt) {
    Copy-Item $readmeIt (Join-Path $pkgDir "Leggimi.txt") -Force
}
$readmeEn = Join-Path $root "LEGGIMI_AMICI_EN.txt"
if (Test-Path $readmeEn) {
    Copy-Item $readmeEn (Join-Path $pkgDir "Readme.txt") -Force
}
# Il codice sorgente Python viene incluso perche' PyQt6 e' distribuito
# sotto licenza GPLv3: distribuendo un programma costruito con PyQt6 va
# reso disponibile anche il relativo codice sorgente.
Copy-Item $appDir (Join-Path $pkgDir "codice_sorgente") -Recurse -Force
Get-ChildItem (Join-Path $pkgDir "codice_sorgente") -Recurse -Include "__pycache__" -Directory |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
foreach ($item in @("settings.ini", "catalogo_dwarf.db", "thumbnails", "logs")) {
    $p = Join-Path (Join-Path $pkgDir "codice_sorgente") $item
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}

Write-Host "6/6 - Creo lo ZIP finale..." -ForegroundColor Cyan
$zipPath = Join-Path $root "$($outName)_portable.zip"
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
Compress-Archive -Path $pkgDir -DestinationPath $zipPath

Write-Host ""
Write-Host "FATTO: $zipPath" -ForegroundColor Green
Write-Host "Puoi inviare questo file agli amici: estraggono lo zip e avviano $outName.exe, senza installare Python."
