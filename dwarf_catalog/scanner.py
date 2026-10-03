"""
scanner.py - Logica di scansione delle cartelle Astronomy dei telescopi
DwarfLab (Dwarf II, Dwarf 3, Dwarf Mini, Dwarf Draco) e popolamento del
database.

La cartella radice dell'archivio ha in genere una sottocartella per ciascun
telescopio (es. "DWARF II", "DWARF 3", "DWARF MINI", "DWARF DRACO"): quale
sia il telescopio si ricava dal nome di questa cartella (vedi
normalize_telescope_name), non serve un elenco fisso - qualunque cartella
che contenga al suo interno una sottocartella "Astronomy" viene trattata
come cartella di un telescopio (vedi find_telescope_astronomy_dirs).

Dentro "Astronomy" possono comparire:

  - Sessioni normali:   DWARF_RAW_<TELE|WIDE>_<target>_EXP_<esp>_GAIN_<gain>_<data-ora>
                         contenenti i raw (.fits/.fit) ed eventualmente lo
                         stack (stacked.jpg o altro formato immagine).
  - Cartella "STARTRAILS": contiene sotto-cartelle
                         STARTRAILS_DWARF_RAW_<TELE|WIDE>_EXP_<esp>_GAIN_<gain>_<data-ora>
                         (modo mostrato come "STARTRAILS")
  - Cartella "Restacked": contiene sotto-cartelle
                         RESTACKED_DWARF_RAW_<TELE|WIDE>_<target>_<filtro>_<yyyymmdd-hhmmssfff>
                         (modo mostrato come "RESTACKED"; niente esposizione/gain)
    -> tutte e tre finiscono nella tabella principale "sessions".

  - Cartella "cali_frame" (solo Dwarf 3): Bias/dark/flat, ognuna con cam_0 (TELE)
    e cam_1 (WIDE), contenenti i master di calibrazione (bias_gain_*, flat_gain_*,
    dark_exp_*).
  - Cartella "DWARF_DARK": sotto-cartelle tipo "tele_exp_30_gain_60_bin_1[_data-ora]"
    con dentro i raw dark ripresi manualmente.
    -> cali_frame e DWARF_DARK finiscono nella tabella separata "calibration"
       (consultabile dalla GUI con il pulsante "Frame di calibrazione…").

I file catalogati nelle sessioni sono .fits/.fit (i raw) e, per gli stack,
.jpg/.jpeg/.png/.tif/.tiff (vedi STACKED_IMAGE_EXTENSIONS). Se presente, il
file "shotsInfo.json" di una sessione viene letto da parse_shots_info() per
recuperare dati aggiuntivi sullo scatto (RA/Dec richiesti, binning, scatti
fatti/da fare/in stack, temperatura minima/massima).

Le altre cartelle di primo livello dentro la cartella del telescopio (Burst,
Normal_Photos, Panoramas, Videos) restano ignorate in questa fase.
"""

import os
import re
import json
import datetime
import logging

from i18n import tr

logger = logging.getLogger("dwarf_catalog")

# Cartelle di primo livello (dentro la cartella del telescopio) da ignorare
# in questa fase: verranno eventualmente aggiunte in futuro.
IGNORED_TOP_FOLDERS = {"burst", "normal_photos", "normal photos", "panoramas", "videos"}

ASTRONOMY_FOLDER_NAME = "astronomy"
CALI_FRAME_FOLDER_NAME = "cali_frame"
DWARF_DARK_FOLDER_NAME = "dwarf_dark"
RESTACKED_FOLDER_NAME = "restacked"
STARTRAILS_FOLDER_NAME = "startrails"
SPECIAL_ASTRONOMY_SUBFOLDERS = {CALI_FRAME_FOLDER_NAME, DWARF_DARK_FOLDER_NAME, RESTACKED_FOLDER_NAME,
                                 STARTRAILS_FOLDER_NAME}

CALI_TYPE_FOLDERS = {"bias": "Bias", "dark": "Dark", "flat": "Flat"}
CAM_TO_CAMERA = {"cam_0": "TELE", "cam_1": "WIDE"}

RAW_EXTENSIONS = {".fits", ".fit"}
# Formati immagine riconosciuti per gli stack (oltre al classico stacked.jpg):
# alcuni telescopi (es. Dwarf Mini / Dwarf Draco) possono salvare lo stack
# principale o quello ad alta risoluzione in png/tif/tiff invece che jpg.
STACKED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
THUMB_SIZE = (320, 320)

# Cartelle di miniature generate dal telescopio, innestate dentro alcune
# cartelle di sessione: i loro file non vanno mai elencati nel visualizzatore
# "Apri sessione" della GUI. Anche i file .txt/.json (metadati) vengono esclusi.
THUMBNAIL_DIR_NAMES = {"thumbnail", "thumbnails"}
NON_LISTABLE_EXTENSIONS = {".txt", ".json"}

# Nome del file di metadati opzionale, presente in alcune cartelle sessione,
# con i dati dello scatto (target, RA/Dec richiesti, binning, scatti fatti/
# da fare, temperatura min/max, ecc.).
SHOTS_INFO_FILENAME = "shotsinfo.json"

# --- Sessioni "normali" ---------------------------------------------------
SESSION_NAME_RE = re.compile(
    r"^DWARF_RAW_(?:(?P<mode>TELE|WIDE)_)?(?P<target>.+?)_EXP_(?P<exp>[0-9]+(?:\.[0-9]+)?)_GAIN_(?P<gain>[0-9]+)_"
    r"(?P<y>\d{4})-(?P<mo>\d{2})-(?P<d>\d{2})-(?P<h>\d{2})-(?P<mi>\d{2})-(?P<s>\d{2})-(?P<ms>\d+)$",
    re.IGNORECASE,
)

# --- Sessioni Startrails ---------------------------------------------------
STARTRAILS_SESSION_RE = re.compile(
    r"^STARTRAILS_DWARF_RAW_(?P<mode>TELE|WIDE)_EXP_(?P<exp>[0-9]+(?:\.[0-9]+)?)_GAIN_(?P<gain>[0-9]+)_"
    r"(?P<y>\d{4})-(?P<mo>\d{2})-(?P<d>\d{2})-(?P<h>\d{2})-(?P<mi>\d{2})-(?P<s>\d{2})-(?P<ms>\d+)$",
    re.IGNORECASE,
)

# --- Sessioni Restacked (dentro la cartella "Restacked") -------------------
# Timestamp qui in formato compatto "yyyymmdd-hhmmssfff" (come nei nomi dei raw),
# non con i trattini fra i campi come nelle sessioni normali.
RESTACKED_SESSION_RE = re.compile(
    r"^RESTACKED_DWARF_RAW_(?P<mode>TELE|WIDE)_(?P<target>.+?)_(?P<filt>[A-Za-z0-9\-]+)_"
    r"(?P<y>\d{4})(?P<mo>\d{2})(?P<d>\d{2})-(?P<h>\d{2})(?P<mi>\d{2})(?P<s>\d{2})(?P<ms>\d+)$",
    re.IGNORECASE,
)

# Nome file tipico di un raw OK: "<target>_<exp>s<gain>_<filtro>_<yyyymmdd-hhmmssfff>_<tempC>"
# es. "10P Tempel_15s120_Astro_20260713-033226426_40C.fits" -> filtro "Astro"
RAW_FILENAME_RE = re.compile(
    r"^(?P<target>.+?)_(?P<exp>[0-9]+(?:\.[0-9]+)?)s(?P<gain>[0-9]+)_(?P<filt>.+?)_"
    r"(?P<ts>\d{8}-\d{9})_(?P<temp>-?\d+C)$",
    re.IGNORECASE,
)

# Il filtro si deduce dal nome dei raw OK solo per il Dwarf 3: sul Dwarf II
# i nomi dei file non lo riportano (mostrato come "---" in quel caso). Per le
# sessioni Restacked il filtro viene invece letto direttamente dal nome della
# cartella, qualunque sia il telescopio.
TELESCOPE_WITH_FILTER_IN_FILENAME = "Dwarf 3"

# --- File di calibrazione (cali_frame) -------------------------------------
BIAS_FILENAME_RE = re.compile(r"^bias_gain_(?P<gain>\d+)_bin_(?P<bin>\d+)$", re.IGNORECASE)
FLAT_FILENAME_RE = re.compile(r"^flat_gain_(?P<gain>\d+)_bin_(?P<bin>\d+)_ir_(?P<ir>\d+)$", re.IGNORECASE)
DARK_FILENAME_STACK_RE = re.compile(
    r"^dark_exp_(?P<exp>[0-9.]+)_gain_(?P<gain>\d+)_bin_(?P<bin>\d+)_(?P<temp>-?\d+)C_stack_(?P<stack>\d+)$",
    re.IGNORECASE,
)
DARK_FILENAME_TEMP_RE = re.compile(
    r"^dark_exp_(?P<exp>[0-9.]+)_gain_(?P<gain>\d+)_bin_(?P<bin>\d+)_temp_(?P<temp>-?\d+)$",
    re.IGNORECASE,
)

# --- Sessioni dark manuali (DWARF_DARK) ------------------------------------
# Il prefisso camera ("tele_"/"wide_") è presente nei nomi delle cartelle dei
# telescopi più recenti (Dwarf 3/Mini/Draco), ma non in quelle del Dwarf II
# (es. "exp_15_gain_100_bin_1"): su quel telescopio la camera è sempre e solo
# "TELE", quindi il gruppo è reso opzionale e, se assente, lo si imposta di
# default in parse_dark_session_folder_name() (richiesto da Nuccio dopo aver
# notato che tutte quelle cartelle del Dwarf II finivano ignorate).
DARK_SESSION_FOLDER_RE = re.compile(
    r"^(?:(?P<camera>tele|wide)_)?exp_(?P<exp>[0-9.]+)_gain_(?P<gain>\d+)_bin_(?P<bin>\d+)"
    r"(?:_(?P<y>\d{4})-(?P<mo>\d{2})-(?P<d>\d{2})-(?P<h>\d{2})-(?P<mi>\d{2})-(?P<s>\d{2})-(?P<ms>\d+))?$",
    re.IGNORECASE,
)
# temperatura in fondo al nome del raw dark, es. "..._27C.fits" -> 27
DARK_RAW_TEMP_RE = re.compile(r"_(-?\d+)C$", re.IGNORECASE)


def _norm(name):
    return re.sub(r"\s+", " ", name).strip().lower()


def normalize_telescope_name(raw_name):
    """Riconduce eventuali varianti di maiuscole/minuscole o spaziatura del
    nome della cartella telescopio (es. 'DWARF II', 'Dwarf  II', 'dwarf3',
    'DWARF MINI', 'DWARF DRACO') a un nome canonico ('Dwarf 3' / 'Dwarf II' /
    'Dwarf Mini' / 'Dwarf Draco'), così i filtri della GUI funzionano
    indipendentemente da come sono scritte le cartelle sul disco. 'Draco' e
    'Drago' sono riconosciuti come lo stesso telescopio (varianti del nome)."""
    norm = re.sub(r"\s+", " ", raw_name).strip()
    low = norm.lower()
    if re.search(r"\bdwarf\s*3\b", low):
        return "Dwarf 3"
    if re.search(r"\bdwarf\s*(ii|2)\b", low):
        return "Dwarf II"
    if re.search(r"\bdwarf\s*mini\b", low):
        return "Dwarf Mini"
    if re.search(r"\bdwarf\s*(draco|drago)\b", low) or re.search(r"\b(draco|drago)\b", low):
        return "Dwarf Draco"
    return norm or "Sconosciuto"


def _build_datetime(g):
    """Costruisce un datetime da un groupdict con chiavi y,mo,d,h,mi,s,ms
    (i separatori originali non contano, sono già stati estratti dalla regex)."""
    try:
        y, mo, d = int(g["y"]), int(g["mo"]), int(g["d"])
        h, mi, s = int(g["h"]), int(g["mi"]), int(g["s"])
        micro = int((g["ms"] + "000000")[:6])
        return datetime.datetime(y, mo, d, h, mi, s, micro)
    except (ValueError, KeyError, TypeError):
        return None


def parse_raw_filename(filename):
    """Analizza il nome di un file raw OK ('<target>_<esp>s<gain>_<filtro>_
    <timestamp>_<tempC>'). Ritorna un dict {filter, temperature} (entrambi
    None se non estraibili), o None se il nome non rispetta il pattern."""
    stem = os.path.splitext(filename)[0]
    m = RAW_FILENAME_RE.match(stem)
    if not m:
        return None
    filt = m.group("filt").strip()
    filt = re.sub(r"[\s_]+", "-", filt).upper() if filt else None
    temp_raw = m.group("temp")  # es. "40C" o "-5C"
    temperature = None
    if temp_raw:
        try:
            temperature = float(temp_raw[:-1])  # rimuove la "C" finale
        except ValueError:
            temperature = None
    return {"filter": filt, "temperature": temperature}


def extract_filter_from_raw_filename(filename):
    """Estrae il nome del filtro (es. VIS, ASTRO, DUO-BAND) dal nome di un
    file raw OK, se il nome rispetta il pattern noto. Ritorna None altrimenti."""
    parsed = parse_raw_filename(filename)
    return parsed["filter"] if parsed else None


def _normalize_filter_token(raw):
    return re.sub(r"[\s_]+", "-", raw.strip()).upper()


def parse_session_folder_name(name):
    """Analizza il nome di una cartella sessione (normale o Startrails).
    Ritorna un dict con i campi estratti, oppure None se il nome non
    rispetta nessuno dei pattern noti."""
    name = name.strip()

    m = SESSION_NAME_RE.match(name)
    if m:
        g = m.groupdict()
        dt = _build_datetime(g)
        if dt is None:
            return None
        return {
            "mode": g["mode"].upper() if g["mode"] else None,
            "target": g["target"].strip(),
            "filter": None,
            "exposure": float(g["exp"]),
            "gain": int(g["gain"]),
            "session_datetime": dt.isoformat(timespec="milliseconds"),
            "session_date": dt.date().isoformat(),
        }

    m = STARTRAILS_SESSION_RE.match(name)
    if m:
        g = m.groupdict()
        dt = _build_datetime(g)
        if dt is None:
            return None
        return {
            "mode": "STARTRAILS",
            "target": None,
            "filter": None,
            "exposure": float(g["exp"]),
            "gain": int(g["gain"]),
            "session_datetime": dt.isoformat(timespec="milliseconds"),
            "session_date": dt.date().isoformat(),
        }

    return None


def parse_restacked_folder_name(name):
    """Analizza il nome di una cartella dentro 'Restacked'. Ritorna un dict
    (mode='RESTACKED', target e filtro presi dal nome, niente esp/gain) o
    None se il nome non rispetta il pattern."""
    m = RESTACKED_SESSION_RE.match(name.strip())
    if not m:
        return None
    g = m.groupdict()
    dt = _build_datetime(g)
    if dt is None:
        return None
    return {
        "mode": "RESTACKED",
        "target": g["target"].strip(),
        "filter": _normalize_filter_token(g["filt"]),
        "exposure": None,
        "gain": None,
        "session_datetime": dt.isoformat(timespec="milliseconds"),
        "session_date": dt.date().isoformat(),
    }


def parse_dark_session_folder_name(name):
    """Analizza il nome di una cartella dentro DWARF_DARK. Ritorna un dict
    con camera/esposizione/gain/bin e data-ora (se presente), o None."""
    m = DARK_SESSION_FOLDER_RE.match(name.strip())
    if not m:
        return None
    g = m.groupdict()
    result = {
        # Dwarf II: nessun prefisso camera nel nome cartella -> sempre TELE
        # (il Dwarf II non ha una camera WIDE separata per i dark manuali).
        "camera": g["camera"].upper() if g["camera"] else "TELE",
        "exposure": float(g["exp"]),
        "gain": int(g["gain"]),
        "bin": int(g["bin"]),
        "session_datetime": None,
        "session_date": None,
    }
    if g.get("y"):
        dt = _build_datetime(g)
        if dt:
            result["session_datetime"] = dt.isoformat(timespec="milliseconds")
            result["session_date"] = dt.date().isoformat()
    return result


def parse_calibration_filename(frame_type, filename):
    """Analizza il nome di un file master di calibrazione (bias/dark/flat).
    Ritorna un dict con i campi estratti, o None se non riconosciuto."""
    stem = os.path.splitext(filename)[0]

    if frame_type == "Bias":
        m = BIAS_FILENAME_RE.match(stem)
        if not m:
            return None
        return {"gain": int(m.group("gain")), "bin": int(m.group("bin")),
                "exposure": None, "ir": None, "temperature": None, "stack_count": None}

    if frame_type == "Flat":
        m = FLAT_FILENAME_RE.match(stem)
        if not m:
            return None
        return {"gain": int(m.group("gain")), "bin": int(m.group("bin")),
                "exposure": None, "ir": int(m.group("ir")), "temperature": None, "stack_count": None}

    if frame_type == "Dark":
        m = DARK_FILENAME_STACK_RE.match(stem)
        if m:
            return {"gain": int(m.group("gain")), "bin": int(m.group("bin")),
                    "exposure": float(m.group("exp")), "ir": None,
                    "temperature": float(m.group("temp")), "stack_count": int(m.group("stack"))}
        m = DARK_FILENAME_TEMP_RE.match(stem)
        if m:
            return {"gain": int(m.group("gain")), "bin": int(m.group("bin")),
                    "exposure": float(m.group("exp")), "ir": None,
                    "temperature": float(m.group("temp")), "stack_count": None}
        return None

    return None


def extract_dark_temp(filename):
    stem = os.path.splitext(filename)[0]
    m = DARK_RAW_TEMP_RE.search(stem)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def read_fits_temperature(file_path):
    """Fallback opzionale: legge la temperatura dall'header FITS quando il
    nome del file non la riporta. Richiede astropy; se non installato, o se
    l'header non contiene un campo di temperatura noto, ritorna None senza
    generare errori."""
    try:
        from astropy.io import fits
    except ImportError:
        return None
    try:
        with fits.open(file_path, memmap=False) as hdul:
            header = hdul[0].header
        for key in ("CCD-TEMP", "CCDTEMP", "TEMP", "SENSOR-TEMP", "SET-TEMP", "TEMP-CCD", "FPTEMP"):
            if key in header:
                try:
                    return float(header[key])
                except (TypeError, ValueError):
                    continue
        # fallback: qualunque chiave dell'header che contenga "TEMP" con un valore numerico
        for key in header:
            if "TEMP" in key.upper():
                try:
                    return float(header[key])
                except (TypeError, ValueError):
                    continue
    except Exception as exc:
        logger.warning("Impossibile leggere la temperatura da %s: %s", file_path, exc)
    return None


def classify_astronomy_files(dirpath, filenames):
    """Classifica i file di una cartella sessione. Ritorna un dizionario
    con conteggi e percorsi dei file 'stacked'."""
    result = {
        "raw_ok": 0,
        "raw_failed": 0,
        "unrecognized": [],
        "stacked_jpg_path": None,
        "stacked_png_path": None,
        "stacked_fits_path": None,
        "stacked_tiff_path": None,
        "total_size": 0,
        "filters": set(),
        "temperatures": [],
        "sample_raw_path": None,
    }
    for fn in filenames:
        full = os.path.join(dirpath, fn)
        try:
            result["total_size"] += os.path.getsize(full)
        except OSError:
            pass

        lower = fn.lower()
        ext = os.path.splitext(fn)[1].lower()

        if lower == "stacked.jpg":
            result["stacked_jpg_path"] = full
        elif lower.startswith("stacked.") and ext in STACKED_IMAGE_EXTENSIONS:
            # Lo stack principale su alcuni telescopi (es. Dwarf Mini/Draco)
            # può non essere in jpg: viene comunque usato come anteprima.
            result["stacked_jpg_path"] = full
        elif lower.startswith("stacked-16_") and ext == ".png":
            result["stacked_png_path"] = full
        elif lower.startswith("stacked-16_") and ext in (".tif", ".tiff"):
            result["stacked_tiff_path"] = full
        elif lower.startswith("stacked-16_") and ext in RAW_EXTENSIONS:
            result["stacked_fits_path"] = full
        elif lower.startswith("failed_"):
            result["raw_failed"] += 1
        elif ext in RAW_EXTENSIONS:
            result["raw_ok"] += 1
            if result["sample_raw_path"] is None:
                result["sample_raw_path"] = full
            parsed_raw = parse_raw_filename(fn)
            if parsed_raw:
                if parsed_raw["filter"]:
                    result["filters"].add(parsed_raw["filter"])
                if parsed_raw["temperature"] is not None:
                    result["temperatures"].append(parsed_raw["temperature"])
        elif ext in NON_LISTABLE_EXTENSIONS:
            # File di metadati (shotsInfo.json, ecc.): letti a parte da
            # parse_shots_info(), non sono "file non riconosciuti".
            pass
        elif ext in STACKED_IMAGE_EXTENSIONS:
            # Altra immagine in un formato catalogabile (jpg/png/tif) ma non
            # riconosciuta come uno degli stack attesi: viene comunque
            # contata/conservata sul disco, solo non segnalata come anomalia.
            pass
        else:
            result["unrecognized"].append(fn)
    return result


def parse_shots_info(session_path, filenames=None):
    """Legge (se presente) il file shotsInfo.json nella cartella sessione:
    contiene dati dello scatto non sempre ricavabili dal nome della cartella
    o dei singoli raw (RA/Dec richiesti, binning, scatti fatti/da fare/in
    stack, temperatura minima/massima). Il nome del file viene cercato senza
    distinzione fra maiuscole/minuscole. Ritorna un dizionario (con chiavi
    sempre presenti, valori None se il dato non c'è o il file manca/non è
    leggibile) così può essere passato direttamente a upsert_session()."""
    empty = {
        "shots_binning": None, "shots_ra": None, "shots_dec": None,
        "shots_taken": None, "shots_stacked": None, "shots_to_take": None,
        "shots_temp_min": None, "shots_temp_max": None,
    }
    if filenames is None:
        try:
            filenames = [f.name for f in os.scandir(session_path) if f.is_file()]
        except OSError:
            return empty

    json_name = next((fn for fn in filenames if fn.lower() == SHOTS_INFO_FILENAME), None)
    if not json_name:
        return empty

    try:
        with open(os.path.join(session_path, json_name), "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        logger.warning("Impossibile leggere %s in '%s': %s", json_name, session_path, exc)
        return empty
    if not isinstance(data, dict):
        return empty

    def _get_ci(*keys):
        """Cerca una chiave nel JSON provando le varianti di maiuscole/
        minuscole indicate, in ordine."""
        for k in keys:
            if k in data and data[k] is not None:
                return data[k]
        return None

    def _as_int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    def _as_float(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    binning = _get_ci("binning", "Binning")
    ra = _get_ci("RA", "ra")
    dec = _get_ci("DEC", "dec", "Dec")

    return {
        "shots_binning": str(binning) if binning is not None else None,
        "shots_ra": str(ra) if ra is not None else None,
        "shots_dec": str(dec) if dec is not None else None,
        "shots_taken": _as_int(_get_ci("shotsTaken")),
        "shots_stacked": _as_int(_get_ci("shotsStacked")),
        "shots_to_take": _as_int(_get_ci("shotsToTake")),
        "shots_temp_min": _as_float(_get_ci("minTemp")),
        "shots_temp_max": _as_float(_get_ci("maxTemp")),
    }


def list_session_files(session_path):
    """Elenca ricorsivamente i file dentro una cartella sessione, per il
    visualizzatore 'Apri sessione' della GUI. Esclude eventuali sottocartelle
    Thumbnail (miniature generate dal telescopio) e i file .txt/.json.
    Ritorna una lista di percorsi assoluti, ordinata per nome file."""
    entries = []
    for dirpath, dirnames, filenames in os.walk(session_path):
        dirnames[:] = [d for d in dirnames if _norm(d) not in THUMBNAIL_DIR_NAMES]
        for fn in filenames:
            if os.path.splitext(fn)[1].lower() in NON_LISTABLE_EXTENSIONS:
                continue
            entries.append(os.path.join(dirpath, fn))
    entries.sort(key=lambda p: os.path.basename(p).lower())
    return entries


def make_stacked_thumbnail(stacked_jpg_path, thumb_dir):
    if not stacked_jpg_path:
        return None
    os.makedirs(thumb_dir, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", os.path.dirname(stacked_jpg_path))[-120:]
    thumb_path = os.path.join(thumb_dir, f"{safe_name}__stacked.png")
    try:
        from PIL import Image
        with Image.open(stacked_jpg_path) as im:
            im = im.convert("RGB")
            im.thumbnail(THUMB_SIZE)
            im.save(thumb_path, "PNG")
        return thumb_path
    except Exception as exc:
        logger.warning("Impossibile generare thumbnail per %s: %s", stacked_jpg_path, exc)
        return None


class ScanStats:
    def __init__(self):
        self.sessions_found = 0
        self.sessions_added = 0
        self.sessions_updated = 0
        self.sessions_unchanged = 0
        self.sessions_removed = 0
        self.unrecognized_folders = 0
        self.cali_added = 0
        self.cali_updated = 0
        self.cali_unchanged = 0
        self.cali_removed = 0
        self.cali_unrecognized = 0
        self.errors = 0


def find_telescope_astronomy_dirs(root_path, log):
    """Percorre root_path e ritorna una lista di tuple (astronomy_dir, telescope)
    per ogni cartella 'Astronomy' trovata, con potatura delle cartelle da
    ignorare (Burst, Normal_Photos, Panoramas, Videos)."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root_path):
        base = os.path.basename(dirpath.rstrip(os.sep))
        if _norm(base) == ASTRONOMY_FOLDER_NAME:
            raw_telescope = os.path.basename(os.path.dirname(dirpath).rstrip(os.sep)) or "Sconosciuto"
            telescope = normalize_telescope_name(raw_telescope)
            found.append((dirpath, telescope))
            dirnames[:] = []  # le sessioni sono processate direttamente, non serve scendere oltre
            continue
        # non scendere nelle cartelle da ignorare in questa fase
        dirnames[:] = [d for d in dirnames if _norm(d) not in IGNORED_TOP_FOLDERS]
    return found


def _process_session_entry(session_path, session_name, parsed, telescope, db, thumb_dir,
                            dry_run, log, stats, seen_paths):
    seen_paths.add(session_path)
    stats.sessions_found += 1

    try:
        filenames = [f.name for f in os.scandir(session_path) if f.is_file()]
    except OSError as exc:
        log(tr("ERRORE nel leggere '{path}': {exc}").format(path=session_path, exc=exc))
        stats.errors += 1
        return

    dir_mtime = str(os.path.getmtime(session_path))
    existing = db.get_session_by_path(session_path)

    # scansione incrementale: se la cartella non è cambiata (stessa mtime e
    # stesso numero di file) e la sessione esiste già, salta il ricalcolo.
    # Eccezione: se la temperatura non è ancora nota e ci sono raw OK, si
    # riprova comunque (es. astropy è stato installato dopo l'ultima scansione).
    temp_still_missing = existing is not None and existing["temperature"] is None \
        and existing["raw_ok_count"] > 0
    if existing and existing["dir_mtime"] == dir_mtime and existing["file_count"] == len(filenames) \
            and not temp_still_missing:
        stats.sessions_unchanged += 1
        if not dry_run:
            db.touch_session_last_scanned(existing["id"])
        return

    classified = classify_astronomy_files(session_path, filenames)
    if classified["unrecognized"]:
        log(tr("AVVISO: {n} file non riconosciuti in '{path}': {names}").format(
            n=len(classified['unrecognized']), path=session_path,
            names=', '.join(classified['unrecognized'][:5]))
            + (" …" if len(classified["unrecognized"]) > 5 else ""))

    shots_info = parse_shots_info(session_path, filenames)

    # il filtro può venire già dal nome della cartella (Restacked), altrimenti
    # si deduce dal nome dei raw OK solo per il Dwarf 3
    filter_name = parsed.get("filter")
    if not filter_name and telescope == TELESCOPE_WITH_FILTER_IN_FILENAME and classified["filters"]:
        filter_name = "/".join(sorted(classified["filters"]))

    # temperatura: media di quelle lette dai nomi dei raw OK; se il nome dei
    # file non la riporta (es. Dwarf II), fallback sulla lettura dell'header
    # FITS di un raw OK campione (solo in scansione reale, per non rallentare
    # il dry-run)
    if classified["temperatures"]:
        temperature = sum(classified["temperatures"]) / len(classified["temperatures"])
    elif not dry_run and classified["sample_raw_path"]:
        temperature = read_fits_temperature(classified["sample_raw_path"])
    else:
        temperature = None

    if dry_run:
        action = tr("nuova") if not existing else tr("aggiornata")
        temp_display = f"{temperature:.1f}°C" if temperature is not None else "?"
        log(tr("[DRY RUN] Sessione {action}: {name} | telescopio={telescope} | "
               "modo={mode} | target={target} | "
               "filtro={filter} | temp={temp} | raw OK={ok} | "
               "raw falliti={failed} | "
               "stack={stack}").format(
            action=action, name=session_name, telescope=telescope,
            mode=parsed['mode'] or '?', target=parsed['target'] or '?',
            filter=filter_name or '---', temp=temp_display, ok=classified['raw_ok'],
            failed=classified['raw_failed'],
            stack=tr('sì') if classified['stacked_jpg_path'] else tr('no')))
        if existing:
            stats.sessions_updated += 1
        else:
            stats.sessions_added += 1
        return

    thumb_path = None
    if classified["stacked_jpg_path"]:
        thumb_path = make_stacked_thumbnail(classified["stacked_jpg_path"], thumb_dir)

    _, was_new = db.upsert_session(
        folder_path=session_path,
        telescope=telescope,
        mode=parsed["mode"],
        target=parsed["target"],
        exposure=parsed["exposure"],
        gain=parsed["gain"],
        session_datetime=parsed["session_datetime"],
        session_date=parsed["session_date"],
        raw_ok_count=classified["raw_ok"],
        raw_failed_count=classified["raw_failed"],
        filter_name=filter_name,
        temperature=temperature,
        stacked_jpg_path=classified["stacked_jpg_path"],
        stacked_png_path=classified["stacked_png_path"],
        stacked_fits_path=classified["stacked_fits_path"],
        stacked_tiff_path=classified["stacked_tiff_path"],
        thumbnail_path=thumb_path,
        total_size=classified["total_size"],
        unrecognized_count=len(classified["unrecognized"]),
        dir_mtime=dir_mtime,
        file_count=len(filenames),
        **shots_info,
    )
    if was_new:
        stats.sessions_added += 1
    else:
        stats.sessions_updated += 1


def refresh_session_record(session_path, db, thumb_dir):
    """Ricalcola e aggiorna il record di UNA sessione già catalogata, senza
    rilanciare un'intera scansione: usato dalla GUI dopo un'operazione di
    file (elimina/rinomina/sposta) su singoli raw dentro la finestra 'Apri
    sessione', così i conteggi raw OK/falliti restano subito corretti.
    Ritorna True se la sessione esiste ancora ed è stata aggiornata, False
    se la cartella non esiste più sul disco (il chiamante può allora
    rimuoverla dal catalogo)."""
    if not os.path.isdir(session_path):
        return False
    existing = db.get_session_by_path(session_path)
    if not existing:
        return False

    folder_name = os.path.basename(session_path.rstrip(os.sep))
    parsed = parse_session_folder_name(folder_name) or parse_restacked_folder_name(folder_name)
    mode = parsed["mode"] if parsed else existing["mode"]
    target = parsed["target"] if parsed else existing["target"]
    exposure = parsed["exposure"] if parsed else existing["exposure"]
    gain = parsed["gain"] if parsed else existing["gain"]
    session_datetime = parsed["session_datetime"] if parsed else existing["session_datetime"]
    session_date = parsed["session_date"] if parsed else existing["session_date"]
    telescope = existing["telescope"]

    try:
        filenames = [f.name for f in os.scandir(session_path) if f.is_file()]
    except OSError:
        return False

    classified = classify_astronomy_files(session_path, filenames)

    filter_name = (parsed.get("filter") if parsed else None) or existing["filter"]
    if not filter_name and telescope == TELESCOPE_WITH_FILTER_IN_FILENAME and classified["filters"]:
        filter_name = "/".join(sorted(classified["filters"]))

    if classified["temperatures"]:
        temperature = sum(classified["temperatures"]) / len(classified["temperatures"])
    elif classified["sample_raw_path"]:
        temperature = read_fits_temperature(classified["sample_raw_path"])
    else:
        temperature = existing["temperature"]

    thumb_path = None
    if classified["stacked_jpg_path"]:
        thumb_path = make_stacked_thumbnail(classified["stacked_jpg_path"], thumb_dir) \
            or existing["thumbnail_path"]

    # shotsInfo.json non viene toccato da elimina/rinomina/sposta dei singoli
    # raw: se non è più leggibile per qualche motivo, si mantengono i valori
    # già catalogati invece di azzerarli.
    fresh_shots_info = parse_shots_info(session_path, filenames)
    shots_info = {
        key: (value if value is not None else existing[key])
        for key, value in fresh_shots_info.items()
    }

    dir_mtime = str(os.path.getmtime(session_path))
    db.upsert_session(
        folder_path=session_path,
        telescope=telescope,
        mode=mode,
        target=target,
        exposure=exposure,
        gain=gain,
        session_datetime=session_datetime,
        session_date=session_date,
        raw_ok_count=classified["raw_ok"],
        raw_failed_count=classified["raw_failed"],
        filter_name=filter_name,
        temperature=temperature,
        stacked_jpg_path=classified["stacked_jpg_path"],
        stacked_png_path=classified["stacked_png_path"],
        stacked_fits_path=classified["stacked_fits_path"],
        stacked_tiff_path=classified["stacked_tiff_path"],
        thumbnail_path=thumb_path,
        total_size=classified["total_size"],
        unrecognized_count=len(classified["unrecognized"]),
        dir_mtime=dir_mtime,
        file_count=len(filenames),
        **shots_info,
    )
    db.commit()
    return True


def _scan_cali_frame(cali_dir, telescope, db, dry_run, log, stats, cali_seen_paths):
    try:
        type_entries = sorted(os.scandir(cali_dir), key=lambda e: e.name)
    except OSError as exc:
        log(tr("ERRORE nel leggere '{path}': {exc}").format(path=cali_dir, exc=exc))
        stats.errors += 1
        return

    for type_entry in type_entries:
        if not type_entry.is_dir():
            continue
        frame_type = CALI_TYPE_FOLDERS.get(_norm(type_entry.name))
        if not frame_type:
            log(tr("AVVISO: cartella non riconosciuta in cali_frame, ignorata: {path}").format(path=type_entry.path))
            continue

        try:
            cam_entries = sorted(os.scandir(type_entry.path), key=lambda e: e.name)
        except OSError as exc:
            log(tr("ERRORE nel leggere '{path}': {exc}").format(path=type_entry.path, exc=exc))
            stats.errors += 1
            continue

        for cam_entry in cam_entries:
            if not cam_entry.is_dir():
                continue
            camera = CAM_TO_CAMERA.get(_norm(cam_entry.name))
            if not camera:
                log(tr("AVVISO: cartella camera non riconosciuta in cali_frame, ignorata: {path}").format(path=cam_entry.path))
                continue

            try:
                file_entries = [f for f in os.scandir(cam_entry.path)
                                 if f.is_file() and os.path.splitext(f.name)[1].lower() in RAW_EXTENSIONS]
            except OSError as exc:
                log(tr("ERRORE nel leggere '{path}': {exc}").format(path=cam_entry.path, exc=exc))
                stats.errors += 1
                continue

            for f in file_entries:
                cali_seen_paths.add(f.path)
                parsed = parse_calibration_filename(frame_type, f.name)
                if not parsed:
                    log(tr("AVVISO: file di calibrazione non riconosciuto, ignorato: {path}").format(path=f.path))
                    stats.cali_unrecognized += 1
                    continue

                try:
                    st = f.stat()
                except OSError as exc:
                    log(tr("ERRORE nel leggere '{path}': {exc}").format(path=f.path, exc=exc))
                    stats.errors += 1
                    continue

                mtime_iso = str(st.st_mtime)
                existing = db.get_calibration_by_path(f.path)
                if existing and existing["dir_mtime"] == mtime_iso and existing["total_size"] == st.st_size:
                    stats.cali_unchanged += 1
                    if not dry_run:
                        db.touch_calibration_last_scanned(existing["id"])
                    continue

                if dry_run:
                    action = tr("nuovo") if not existing else tr("aggiornato")
                    log(tr("[DRY RUN] Calibrazione {action}: {frame_type}/{camera} {name}").format(
                        action=action, frame_type=frame_type, camera=camera, name=f.name))
                    if existing:
                        stats.cali_updated += 1
                    else:
                        stats.cali_added += 1
                    continue

                _, was_new = db.upsert_calibration(
                    telescope=telescope, source="cali_frame", frame_type=frame_type, camera=camera,
                    gain=parsed["gain"], bin_=parsed["bin"], exposure=parsed["exposure"],
                    ir=parsed["ir"], temperature=parsed["temperature"], stack_count=parsed["stack_count"],
                    raw_count=None, session_datetime=None, session_date=None,
                    record_path=f.path, dir_mtime=mtime_iso, file_count=None, total_size=st.st_size,
                )
                if was_new:
                    stats.cali_added += 1
                else:
                    stats.cali_updated += 1


def _scan_dwarf_dark(dark_dir, telescope, db, dry_run, log, stats, cali_seen_paths):
    try:
        entries = sorted(os.scandir(dark_dir), key=lambda e: e.name)
    except OSError as exc:
        log(tr("ERRORE nel leggere '{path}': {exc}").format(path=dark_dir, exc=exc))
        stats.errors += 1
        return

    for entry in entries:
        if not entry.is_dir():
            continue
        parsed = parse_dark_session_folder_name(entry.name)
        if not parsed:
            log(tr("AVVISO: cartella non riconosciuta in DWARF_DARK, ignorata: {path}").format(path=entry.path))
            stats.cali_unrecognized += 1
            continue

        cali_seen_paths.add(entry.path)
        try:
            file_entries = [f for f in os.scandir(entry.path)
                             if f.is_file() and os.path.splitext(f.name)[1].lower() in RAW_EXTENSIONS]
        except OSError as exc:
            log(tr("ERRORE nel leggere '{path}': {exc}").format(path=entry.path, exc=exc))
            stats.errors += 1
            continue

        dir_mtime = str(os.path.getmtime(entry.path))
        existing = db.get_calibration_by_path(entry.path)
        # come per le sessioni: se la temperatura non è ancora nota, riprova
        # comunque (es. astropy installato dopo l'ultima scansione)
        temp_still_missing = existing is not None and existing["temperature"] is None and file_entries
        if existing and existing["dir_mtime"] == dir_mtime and existing["file_count"] == len(file_entries) \
                and not temp_still_missing:
            stats.cali_unchanged += 1
            if not dry_run:
                db.touch_calibration_last_scanned(existing["id"])
            continue

        temps = [t for t in (extract_dark_temp(f.name) for f in file_entries) if t is not None]
        if temps:
            avg_temp = sum(temps) / len(temps)
        elif not dry_run and file_entries:
            avg_temp = read_fits_temperature(file_entries[0].path)
        else:
            avg_temp = None

        total_size = 0
        for f in file_entries:
            try:
                total_size += f.stat().st_size
            except OSError:
                pass

        if dry_run:
            action = tr("nuova") if not existing else tr("aggiornata")
            temp_display = f"{avg_temp:.1f}°C" if avg_temp is not None else "?"
            log(tr("[DRY RUN] Sessione dark {action}: {name} | camera={camera} | "
                   "raw={raw} | temp media={temp}").format(
                action=action, name=entry.name, camera=parsed['camera'],
                raw=len(file_entries), temp=temp_display))
            if existing:
                stats.cali_updated += 1
            else:
                stats.cali_added += 1
            continue

        _, was_new = db.upsert_calibration(
            telescope=telescope, source="dwarf_dark", frame_type="Dark", camera=parsed["camera"],
            gain=parsed["gain"], bin_=parsed["bin"], exposure=parsed["exposure"], ir=None,
            temperature=avg_temp, stack_count=None, raw_count=len(file_entries),
            session_datetime=parsed["session_datetime"], session_date=parsed["session_date"],
            record_path=entry.path, dir_mtime=dir_mtime, file_count=len(file_entries), total_size=total_size,
        )
        if was_new:
            stats.cali_added += 1
        else:
            stats.cali_updated += 1


def scan_root(root_path, db, thumb_dir, dry_run=False, remove_orphans=True,
              progress_cb=None, log_cb=None, should_stop=None):
    stats = ScanStats()

    def log(msg):
        logger.info(msg)
        if log_cb:
            log_cb(msg)

    log(tr("Inizio scansione di: {root}").format(root=root_path)
        + (" [DRY RUN: nessuna modifica al DB]" if dry_run else ""))

    if not os.path.isdir(root_path):
        log(tr("ERRORE: la cartella '{path}' non esiste.").format(path=root_path))
        stats.errors += 1
        return stats

    astronomy_dirs = find_telescope_astronomy_dirs(root_path, log)
    log(tr("Trovate {n} cartelle 'Astronomy' (telescopi: {list}).").format(
        n=len(astronomy_dirs),
        list=', '.join(sorted({t for _, t in astronomy_dirs})) or tr('nessuno')))

    known_paths_before = db.all_session_folder_paths()
    seen_paths = set()
    cali_known_paths_before = db.all_calibration_record_paths()
    cali_seen_paths = set()
    processed = 0

    for astronomy_dir, telescope in astronomy_dirs:
        if should_stop and should_stop():
            log(tr("Scansione interrotta dall'utente."))
            break

        try:
            entries = sorted(os.scandir(astronomy_dir), key=lambda e: e.name)
        except OSError as exc:
            log(tr("ERRORE nel leggere '{path}': {exc}").format(path=astronomy_dir, exc=exc))
            stats.errors += 1
            continue

        for entry in entries:
            if should_stop and should_stop():
                break
            if not entry.is_dir():
                continue

            norm_name = _norm(entry.name)

            if norm_name == CALI_FRAME_FOLDER_NAME:
                _scan_cali_frame(entry.path, telescope, db, dry_run, log, stats, cali_seen_paths)
                continue

            if norm_name == DWARF_DARK_FOLDER_NAME:
                _scan_dwarf_dark(entry.path, telescope, db, dry_run, log, stats, cali_seen_paths)
                continue

            if norm_name == RESTACKED_FOLDER_NAME:
                try:
                    sub_entries = sorted(os.scandir(entry.path), key=lambda e: e.name)
                except OSError as exc:
                    log(tr("ERRORE nel leggere '{path}': {exc}").format(path=entry.path, exc=exc))
                    stats.errors += 1
                    continue
                for sub_entry in sub_entries:
                    if not sub_entry.is_dir():
                        continue
                    parsed = parse_restacked_folder_name(sub_entry.name)
                    if not parsed:
                        stats.unrecognized_folders += 1
                        log(tr("AVVISO: cartella in Restacked non riconosciuta come sessione, ignorata: "
                               "{path}").format(path=sub_entry.path))
                        continue
                    processed += 1
                    _process_session_entry(sub_entry.path, sub_entry.name, parsed, telescope, db,
                                            thumb_dir, dry_run, log, stats, seen_paths)
                    if progress_cb:
                        progress_cb(processed, len(astronomy_dirs), sub_entry.name)
                continue

            if norm_name == STARTRAILS_FOLDER_NAME:
                try:
                    sub_entries = sorted(os.scandir(entry.path), key=lambda e: e.name)
                except OSError as exc:
                    log(tr("ERRORE nel leggere '{path}': {exc}").format(path=entry.path, exc=exc))
                    stats.errors += 1
                    continue
                for sub_entry in sub_entries:
                    if not sub_entry.is_dir():
                        continue
                    parsed = parse_session_folder_name(sub_entry.name)
                    if not parsed:
                        stats.unrecognized_folders += 1
                        log(tr("AVVISO: cartella in STARTRAILS non riconosciuta come sessione, ignorata: "
                               "{path}").format(path=sub_entry.path))
                        continue
                    processed += 1
                    _process_session_entry(sub_entry.path, sub_entry.name, parsed, telescope, db,
                                            thumb_dir, dry_run, log, stats, seen_paths)
                    if progress_cb:
                        progress_cb(processed, len(astronomy_dirs), sub_entry.name)
                continue

            parsed = parse_session_folder_name(entry.name)
            if not parsed:
                stats.unrecognized_folders += 1
                log(tr("AVVISO: cartella in Astronomy non riconosciuta come sessione, ignorata: "
                       "{path}").format(path=entry.path))
                continue

            processed += 1
            _process_session_entry(entry.path, entry.name, parsed, telescope, db,
                                    thumb_dir, dry_run, log, stats, seen_paths)
            if progress_cb:
                progress_cb(processed, len(astronomy_dirs), entry.name)

    # Rimozione sessioni e frame di calibrazione non più presenti sul disco
    # (solo sotto root_path)
    if remove_orphans and not dry_run:
        root_norm = os.path.normpath(root_path)
        orphans = [
            p for p in known_paths_before
            if os.path.normpath(p).startswith(root_norm) and p not in seen_paths
        ]
        if orphans:
            log(tr("Rimozione di {n} sessioni non più presenti sul disco.").format(n=len(orphans)))
            db.delete_sessions_by_paths(orphans)
            stats.sessions_removed = len(orphans)

        cali_orphans = [
            p for p in cali_known_paths_before
            if os.path.normpath(p).startswith(root_norm) and p not in cali_seen_paths
        ]
        if cali_orphans:
            log(tr("Rimozione di {n} frame di calibrazione non più presenti sul disco.").format(n=len(cali_orphans)))
            db.delete_calibration_by_paths(cali_orphans)
            stats.cali_removed = len(cali_orphans)

    if not dry_run:
        db.set_meta("last_scan_root", root_path)
        db.set_meta("last_scan_time", datetime.datetime.now().isoformat(timespec="seconds"))
        db.commit()

    log(
        tr("Scansione completata. Sessioni trovate: {found}, "
           "nuove: {added}, aggiornate: {updated}, "
           "invariate: {unchanged}, rimosse: {removed}, "
           "cartelle non riconosciute: {unrecognized}, errori: {errors} | "
           "Calibrazione: nuovi={cali_added}, aggiornati={cali_updated}, "
           "invariati={cali_unchanged}, rimossi={cali_removed}, "
           "non riconosciuti={cali_unrecognized}").format(
            found=stats.sessions_found, added=stats.sessions_added,
            updated=stats.sessions_updated, unchanged=stats.sessions_unchanged,
            removed=stats.sessions_removed, unrecognized=stats.unrecognized_folders,
            errors=stats.errors, cali_added=stats.cali_added,
            cali_updated=stats.cali_updated, cali_unchanged=stats.cali_unchanged,
            cali_removed=stats.cali_removed, cali_unrecognized=stats.cali_unrecognized)
    )
    return stats
