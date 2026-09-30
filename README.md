# Catalogo Sessioni Astronomiche DWARF

Catalogo per organizzare e consultare le sessioni astrofotografiche dei
telescopi **Dwarf II, Dwarf 3, Dwarf Mini e Dwarf Draco**: scansiona le
cartelle delle tue riprese e crea un archivio ricercabile per data,
target, filtro, ecc., con anteprima degli stack e alcune funzioni extra.

Sviluppato per uso personale e condiviso liberamente con la comunità
italiana dei possessori di telescopi Dwarf.

## Download rapido (consigliato per chi non conosce GitHub)

Se non hai familiarità con GitHub e vuoi solo usare il programma, il modo
più semplice è:

1. Vai alla pagina delle **[Release](https://github.com/nuccioma/CatalogoAstroDwarf/releases/latest)**.
2. Nella sezione "Assets" in fondo, scarica il file
   `CatalogoAstroDwarf_portable.zip`.
3. Estrai lo zip in una cartella qualsiasi del tuo PC ed esegui
   `CatalogoAstroDwarf.exe`: non serve installare Python né altro.

Le istruzioni dettagliate (con anche le funzioni opzionali) sono nel file
`Leggimi.txt` incluso nello zip.

Le sezioni seguenti riguardano invece chi preferisce usare il codice
sorgente Python direttamente (es. per modificarlo).

## Funzionalità principali

- Scansione automatica delle cartelle create dai telescopi Dwarf (sessioni
  normali, Restacked, STARTRAILS, frame di calibrazione Bias/Dark/Flat)
- Archivio ricercabile e filtrabile per telescopio, modalità, target, data
- Anteprima delle immagini stack (jpg/FITS) con finestra di ingrandimento,
  zoom e stampa
- Identificazione dell'oggetto ripreso e condizioni osservative (altezza,
  azimut, fase lunare) tramite interrogazione a SIMBAD
- Astrometria: etichettatura degli oggetti nel campo inquadrato, con due
  metodologie a scelta (Siril + SIMBAD, oppure Astrometry.net locale via
  WSL)
- Analisi di qualità dei singoli raw (stelle rilevate, FWHM, rumore di
  fondo) per scartare i peggiori prima dello stacking
- Operazioni sui file (rinomina/sposta/copia/elimina) direttamente
  dall'archivio
- Interfaccia disponibile in italiano e inglese

## Requisiti

- **Python 3** (consigliata una versione recente, 3.10 o superiore) -
  scaricabile gratuitamente da [python.org](https://www.python.org/downloads/)
- Pensato e testato su **Windows** (alcune funzioni opzionali, come
  Astrometry.net via WSL, sono specifiche di Windows), ma il catalogo di
  base funziona su qualunque sistema operativo dove giri PyQt6

## Come avviarlo

```powershell
git clone https://github.com/nuccioma/CatalogoAstroDwarf.git
cd CatalogoAstroDwarf
pip install -r dwarf_catalog\requirements.txt
python dwarf_catalog\main.py
```

(In alternativa a `git clone`, si può semplicemente scaricare lo zip del
repository da GitHub - pulsante verde "Code" -> "Download ZIP" - ed
estrarlo.)

Il primo comando installa le librerie necessarie (richiede una
connessione Internet, va fatto solo la prima volta); il secondo avvia il
programma, e va ripetuto ogni volta che lo si vuole riaprire.

Al primo avvio, imposta la tua "Cartella radice" (quella che contiene le
cartelle Dwarf II / Dwarf 3 / ecc., con dentro "Astronomy" - dove il
Dwarf salva le sessioni), poi premi "Scansiona ora". Il programma crea da
solo, accanto ai suoi file, il proprio database (`catalogo_dwarf.db`) e
le proprie impostazioni: non tocca né modifica in alcun modo le foto/raw
originali.

### Uso da riga di comando (senza aprire la finestra)

```powershell
python dwarf_catalog\main.py --scan "D:\Cartelle_RAW" [--dry-run] [--no-remove-orphans]
```

Utile per pianificare la scansione automaticamente (es. Utilità di
pianificazione di Windows). Vedi `python dwarf_catalog\main.py --help`
per tutte le opzioni.

## Creare un eseguibile Windows (facoltativo)

Chi preferisce un `.exe` autonomo (senza dover installare Python) può
generarlo da sé con lo script incluso, su Windows:

```powershell
.\build_exe.ps1
```

Crea un pacchetto portatile (`CatalogoAstroDwarf_portable.zip`, circa
400-700 MB per via delle librerie scientifiche incluse) pronto da
condividere: chi lo riceve estrae lo zip e avvia `CatalogoAstroDwarf.exe`,
senza installare nulla. Lo script include automaticamente anche il
codice sorgente nel pacchetto, come richiesto dalla licenza GPLv3 di
PyQt6 (vedi sotto).

## Funzioni opzionali (richiedono programmi esterni)

Il resto del catalogo funziona normalmente senza; installa questi solo
se ti interessano le funzioni corrispondenti:

| Funzione | Richiede | Note |
|---|---|---|
| Identifica oggetto (SIMBAD) | Connessione Internet | Nessun altro programma |
| Astrometria - metodo SIMBAD | [Siril](https://siril.org) con catalogo Gaia locale scaricato (Siril -> Impostazioni -> Astrometria) | Percorso di `siril-cli.exe` da impostare in File -> "Imposta percorso Siril..." |
| Astrometria - metodo Astrometry.net | WSL (Ubuntu) con `sudo apt install astrometry.net astrometry-data-2mass-08-19 astrometry-data-tycho2` | Alternativa offline a Siril |

Entrambe le ricerche SIMBAD (identificazione oggetto, etichette del
campo) richiedono una connessione Internet.

> **Nota sull'"Analizza qualità raw"** (numero di stelle, FWHM): questi
> valori sono calcolati con un algoritmo proprio del programma, utili per
> confrontare i file tra loro all'interno della stessa sessione. Possono
> differire leggermente da altri programmi (DeepSkyStacker, Siril, Fusion
> Lab, ecc.), che usano algoritmi diversi: è normale.

## Lingua dell'interfaccia

Il programma parte in italiano. Per passare all'inglese: menu File ->
Lingua -> English (va richiuso e riaperto il programma perché il cambio
abbia effetto).

## Licenza

Software libero, distribuito senza garanzie. Costruito con
[PyQt6](https://www.riverbankcomputing.com/software/pyqt/) (Riverbank
Computing, licenza GPLv3 - per questo anche il codice di questo
repository è rilasciato sotto licenza **GPLv3**, vedi [LICENSE](LICENSE)),
[astropy](https://www.astropy.org/), [astroquery](https://astroquery.readthedocs.io/),
[photutils](https://photutils.readthedocs.io/) e [Pillow](https://python-pillow.org/).

Creato da Nuccio Mandarà con l'aiuto di Claude AI (Anthropic).
