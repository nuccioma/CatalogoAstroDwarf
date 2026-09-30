"""
dwarf_astrometry.py - Astrometria di campo (plate solving) sull'immagine
stacked di una sessione ed etichettatura degli oggetti presenti
nell'inquadratura.

NOTA SUL NOME DEL FILE: si chiama "dwarf_astrometry.py" e non semplicemente
"astrometry.py" apposta, per non entrare in conflitto col vero pacchetto
Python "astrometry" installato dentro WSL (quello di Astrometry.net: vedi
solve_and_annotate_astrometry_net più sotto). Con un file "astrometry.py"
nella cartella del programma, se mai quella cartella fosse anche la
directory di lavoro corrente al momento di lanciare "wsl.exe" (WSL eredita
di norma la cartella corrente di chi lo lancia), l'interprete Python DENTRO
WSL troverebbe prima il nostro file (un modulo semplice, non un pacchetto)
al posto del vero pacchetto astrometry.net, con un errore del tipo
"'astrometry' is not a package". Per sicurezza, solve_and_annotate_
astrometry_net forza comunque una directory di lavoro pulita (--cd ~) prima
di lanciare solve-field, indipendentemente da questo.

Sono disponibili due metodologie alternative, scelte ogni volta
dall'utente nella finestra "Opzioni astrometria":

1. SIMBAD (via Siril). Il plate solving (determinare la corrispondenza
   pixel <-> coordinate celesti per tutta l'immagine, non solo per il
   target) viene delegato a Siril in modalità headless (siril-cli.exe),
   usando il suo catalogo Gaia locale: non richiede connessione Internet,
   a patto che l'utente abbia scaricato quel catalogo dentro Siril
   (Impostazioni -> Astrometria in Siril). Il file del catalogo stesso
   (siril_cat*.dat) NON viene letto direttamente da questo modulo: è un
   formato binario proprietario di Siril, pensato per essere consumato dal
   motore di Siril stesso. Una volta ottenuta la soluzione astrometrica
   (WCS), gli oggetti da etichettare vengono cercati in due modi,
   entrambi via SIMBAD per posizione (query sull'intero campo, non per
   nome) - richiede Internet:
     - oggetti "notevoli" con una designazione Messier/NGC/IC (galassie,
       nebulose, ammassi);
     - se richiesto, le stelle più luminose del campo che hanno un nome
       leggibile (nome proprio, designazione di Bayer/Flamsteed o sigla
       HD). Non usa l'archivio Gaia online: le sue stelle sono
       identificate solo da un ID numerico Gaia DR3, senza alcun
       significato su una foto.
   Le etichette vengono disegnate da questo modulo (funzione
   annotate_image) sull'immagine scelta dall'utente per la
   visualizzazione (FITS o jpg) - vedi plate_solve_image.

2. Astrometry.net (locale, dentro WSL). Risolve ed etichetta invece con
   Astrometry.net installato in locale in una distribuzione WSL
   (comando 'solve-field', richiamato da Windows tramite wsl.exe):
   funziona offline (a patto che l'utente abbia installato gli indici
   stellari dentro WSL), ma a differenza del percorso SIMBAD è
   Astrometry.net stesso a produrre l'immagine annotata, con i propri
   cataloghi (Messier/NGC/IC e le stelle che riconosce) - non viene
   interrogato SIMBAD, e non viene disegnato nulla da questo modulo per
   questa via. A differenza di Siril, Astrometry.net risolve "alla
   cieca" dal solo contenuto dell'immagine, senza bisogno della
   dimensione pixel/focale nell'header: l'immagine da risolvere è quindi
   la stessa scelta per la visualizzazione (FITS o jpg), non serve
   preferire sempre il FITS. Vedi solve_and_annotate_astrometry_net.

Tutte le funzioni sono difensive: ritornano un errore testuale invece di
sollevare eccezioni, così la GUI può mostrare un messaggio invece di
bloccarsi.
"""

import os
import re
import subprocess
import tempfile
import shutil
import uuid

from i18n import tr


def _run_with_timeout(fn, timeout_s, *args, **kwargs):
    """Esegue fn(*args, **kwargs) in un thread separato, con un limite
    massimo di tempo. Serve perché le interrogazioni online (SIMBAD, Gaia)
    non garantiscono sempre un timeout di rete efficace: se il server è
    molto carico o mette la richiesta in coda, altrimenti l'elaborazione
    potrebbe restare bloccata per un tempo indefinito. Solleva TimeoutError
    se il limite viene superato (il thread di rete abbandonato termina da
    solo in background, senza bloccare il chiamante)."""
    import concurrent.futures
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=timeout_s)
    except concurrent.futures.TimeoutError:
        raise TimeoutError(tr("nessuna risposta dal server entro {timeout_s} secondi").format(timeout_s=timeout_s))
    finally:
        executor.shutdown(wait=False)


def default_siril_cli_candidates():
    """Percorsi tipici di siril-cli.exe su Windows, usati come primo
    tentativo se l'utente non ne ha ancora indicato uno."""
    return [
        r"C:\Program Files\Siril\bin\siril-cli.exe",
        r"C:\Program Files (x86)\Siril\bin\siril-cli.exe",
    ]


def find_default_siril_cli():
    """Ritorna il primo percorso tipico di siril-cli.exe che esiste
    davvero su questo PC, o None se nessuno dei percorsi tipici esiste."""
    for candidate in default_siril_cli_candidates():
        if os.path.isfile(candidate):
            return candidate
    return None


def plate_solve_image(image_path, siril_cli_path, timeout=240, ra_deg=None, dec_deg=None):
    """Risolve astrometricamente image_path lanciando Siril in modalità
    headless (siril-cli.exe -d <cartella> -s <script>) con il comando
    'platesolve -catalog=localgaia' (catalogo Gaia locale, offline).

    ra_deg/dec_deg (gradi decimali, opzionali) sono una posizione
    approssimativa del centro campo da passare a Siril: necessaria quando
    il file non ha nell'header una posizione di puntamento (tipicamente un
    jpg semplice, che non ha header astronomico) - senza, Siril rifiuta di
    risolvere con l'errore "non sono state passate coordinate target, né
    l'header ne contiene alcuna". Se il file ha già un header con
    posizione (es. molti FITS del Dwarf), passarle comunque non fa danno e
    può velocizzare la ricerca.

    Ritorna una tupla (wcs, width, height, errore): wcs è un oggetto
    astropy.wcs.WCS se la risoluzione riesce (e in quel caso errore è
    None); altrimenti wcs/width/height sono None ed errore è un
    messaggio testuale da mostrare all'utente."""
    if not siril_cli_path or not os.path.isfile(siril_cli_path):
        return None, None, None, tr(
            "Non trovo siril-cli.exe nel percorso configurato. Imposta il "
            "percorso corretto da File → Imposta percorso Siril…")
    if not image_path or not os.path.isfile(image_path):
        return None, None, None, tr("File immagine non trovato: {path}").format(path=image_path)

    try:
        from astropy.io import fits
        from astropy.wcs import WCS
    except ImportError:
        return None, None, None, tr("Per l'astrometria serve la libreria 'astropy'.")

    work_dir = tempfile.mkdtemp(prefix="astrodwarf_solve_")
    try:
        output_basename = "solved"
        script_path = os.path.join(work_dir, "solve.ssf")
        # Siril accetta "/" come separatore anche su Windows; evitiamo così
        # problemi con i backslash dentro lo script.
        siril_image_path = image_path.replace("\\", "/")
        siril_output_path = os.path.join(work_dir, output_basename).replace("\\", "/")
        # 'requires' deve essere il primo comando dello script: senza,
        # Siril (dalla 1.4 in poi) si limita ad avvisare che manca e poi
        # NON esegue affatto i comandi successivi (lo script "termina con
        # successo" in una frazione di millisecondo senza aver caricato
        # né risolto nulla) - versione bassa apposta per restare
        # compatibile con installazioni Siril meno recenti.
        center_arg = f"{ra_deg:.6f},{dec_deg:.6f} " if (ra_deg is not None and dec_deg is not None) else ""
        script_content = (
            f'requires 1.2.0\n'
            f'load "{siril_image_path}"\n'
            # -nocrop: alcuni cataloghi/opzioni di Siril possono ritagliare
            # l'immagine durante la risoluzione; lo evitiamo così le
            # dimensioni della soluzione WCS restano identiche a quelle del
            # file originale (altrimenti la proiezione pixel delle etichette
            # sull'immagine visualizzata risulterebbe leggermente disallineata).
            f'platesolve {center_arg}-catalog=localgaia -nocrop\n'
            f'save "{siril_output_path}"\n'
        )
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(script_content)

        try:
            proc = subprocess.run(
                [siril_cli_path, "-d", work_dir, "-s", script_path],
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return None, None, None, tr(
                "Siril non ha risposto entro il tempo massimo previsto ({timeout}s): "
                "risoluzione astrometrica interrotta.").format(timeout=timeout)
        except OSError as exc:
            return None, None, None, tr("Impossibile avviare Siril: {exc}").format(exc=exc)

        # A seconda delle preferenze dell'installazione Siril (impostazione
        # SETEXT), 'save' scrive .fits oppure .fit: proviamo entrambe.
        output_fits = None
        for ext in (".fits", ".fit"):
            candidate = os.path.join(work_dir, output_basename + ext)
            if os.path.isfile(candidate):
                output_fits = candidate
                break

        if output_fits is None:
            detail = (proc.stderr or proc.stdout or "").strip()
            detail_bit = f"\n\nDettagli Siril:\n{detail[-1500:]}" if detail else ""
            if "non sono state passate coordinate" in detail.lower() or "no target coordinates" in detail.lower():
                return None, None, None, tr(
                    "Siril non ha una posizione approssimativa da cui partire (il file non "
                    "ha un header con il puntamento, e non è stata trovata una posizione nota "
                    "per il target). Prova a identificare prima l'oggetto con \"Identifica "
                    "oggetto (SIMBAD)\", oppure usa il FITS.{detail_bit}").format(detail_bit=detail_bit)
            if "dimensione pixel non trovata" in detail.lower() or "pixel size not found" in detail.lower():
                return None, None, None, tr(
                    "Siril non conosce la dimensione del pixel del sensore e la focale usate "
                    "per questa immagine: informazioni che un jpg semplice non porta con sé "
                    "(un FITS della sessione di solito le ha). Usa il FITS, se disponibile.{detail_bit}").format(detail_bit=detail_bit)
            return None, None, None, tr(
                "Siril non è riuscito a risolvere l'immagine (nessuna corrispondenza "
                "trovata con il catalogo). Verifica che il catalogo Gaia locale sia "
                "installato in Siril e che l'immagine mostri un campo stellare leggibile.{detail_bit}").format(detail_bit=detail_bit)

        try:
            header = fits.getheader(output_fits)
            # naxis=2: lo stack può essere a colori (FITS a 3 assi, il terzo
            # per i canali RGB) ma la soluzione WCS riguarda solo i due assi
            # spaziali; senza restringere esplicitamente a 2 assi, astropy
            # solleva un errore per l'asse dei colori privo di WCS proprio.
            wcs = WCS(header, naxis=2)
            if not wcs.has_celestial:
                return None, None, None, tr("Il file risolto da Siril non contiene una soluzione WCS valida.")
            width = int(header.get("NAXIS1", 0))
            height = int(header.get("NAXIS2", 0))
            if not width or not height:
                return None, None, None, tr("Il file risolto da Siril non riporta le dimensioni dell'immagine.")
        except Exception as exc:
            return None, None, None, tr("Impossibile leggere la soluzione astrometrica: {exc}").format(exc=exc)

        return wcs, width, height, None
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def field_footprint(wcs, width, height):
    """Ritorna (centro_coord, raggio_deg): il centro del campo inquadrato
    e il raggio (in gradi) che contiene l'intera immagine, calcolati dalla
    soluzione WCS e dalle dimensioni in pixel."""
    center = wcs.pixel_to_world(width / 2.0, height / 2.0)
    radius = 0.0
    for px, py in ((0, 0), (width, 0), (0, height), (width, height)):
        corner = wcs.pixel_to_world(px, py)
        sep = float(center.separation(corner).deg)
        if sep > radius:
            radius = sep
    return center, radius


import re as _re

_CATALOG_DSO_RE = _re.compile(
    r'^(M\s?\d{1,4}|NGC\s?\d{1,5}[A-Za-z]?|IC\s?\d{1,5}[A-Za-z]?)$', _re.IGNORECASE)


def _best_catalog_name(main_id, ids_str):
    """Tra il main_id e gli identificativi alternativi (campo 'ids' di
    SIMBAD, pipe-separated), ritorna il nome di catalogo Messier/NGC/IC da
    mostrare (preferendo Messier), oppure None se l'oggetto non ha alcuna
    designazione in questi cataloghi."""
    candidates = []
    if main_id:
        candidates.append(str(main_id).strip())
    if ids_str:
        candidates.extend(tok.strip() for tok in str(ids_str).split("|") if tok.strip())
    messier, ngc, ic = None, None, None
    for cand in candidates:
        normalized = _re.sub(r'\s+', ' ', cand).strip()
        if not _CATALOG_DSO_RE.match(normalized):
            continue
        upper = normalized.upper()
        if upper.startswith("M") and not upper.startswith(("NGC", "IC")):
            messier = messier or normalized
        elif upper.startswith("NGC"):
            ngc = ngc or normalized
        elif upper.startswith("IC"):
            ic = ic or normalized
    return messier or ngc or ic


_STAR_BAYER_RE = _re.compile(r'^\*\s+(.+)$')
_STAR_HD_RE = _re.compile(r'^HD\s?\d+$', _re.IGNORECASE)


def _best_star_name(main_id, ids_str):
    """Tra il main_id e gli identificativi alternativi, ritorna il nome più
    leggibile per una stella: nome proprio (es. 'Polaris'), poi
    designazione di Bayer/Flamsteed (es. 'alf UMi', '51 And'), poi sigla HD
    - in quest'ordine di preferenza. Ritorna None se la stella su SIMBAD
    non ha altro che sigle di catalogo illeggibili (es. solo un ID interno
    di una survey): è proprio il caso, allora, da scartare per non
    ricadere nello stesso problema delle etichette Gaia DR3 numeriche."""
    candidates = []
    if main_id:
        candidates.append(str(main_id).strip())
    if ids_str:
        candidates.extend(tok.strip() for tok in str(ids_str).split("|") if tok.strip())
    proper, bayer_flamsteed, hd = None, None, None
    for cand in candidates:
        normalized = _re.sub(r'\s+', ' ', cand).strip()
        if normalized.upper().startswith("NAME "):
            proper = proper or normalized[5:].strip()
            continue
        m = _STAR_BAYER_RE.match(normalized)
        if m and bayer_flamsteed is None:
            bayer_flamsteed = m.group(1).strip()
            continue
        if hd is None and _STAR_HD_RE.match(normalized):
            hd = normalized.upper().replace("HD", "HD ").replace("  ", " ")
    return proper or bayer_flamsteed or hd


def _angular_separation_deg(ra_deg, dec_deg, ref_coord):
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    try:
        c2 = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg)
        return float(ref_coord.separation(c2).deg)
    except Exception:
        return 999.0


def _sort_and_declutter(objects, center, radius_deg, max_objects, min_separation_deg=None,
                         target_name=None, target_ra=None, target_dec=None, sort_key=None):
    """Utilità condivisa fra find_notable_objects e find_bright_named_stars:
    ordina i candidati (per distanza dal centro, salvo un sort_key
    alternativo), garantisce facoltativamente la presenza dell'oggetto
    target, e scarta chi cade troppo vicino (entro min_separation_deg, per
    default proporzionale al raggio del campo) a un'etichetta già scelta -
    altrimenti in un campo affollato le etichette finirebbero ammassate una
    sopra l'altra, illeggibili."""
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    for obj in objects:
        obj["_sep"] = _angular_separation_deg(obj["ra_deg"], obj["dec_deg"], center)

    if sort_key is None:
        objects.sort(key=lambda o: o["_sep"])
    else:
        objects.sort(key=sort_key)

    if target_name and target_ra is not None and target_dec is not None:
        try:
            target_coord = SkyCoord(ra=target_ra * u.deg, dec=target_dec * u.deg)
        except Exception:
            target_coord = None
        if target_coord is not None:
            already_present = any(
                _angular_separation_deg(o["ra_deg"], o["dec_deg"], target_coord) < (30.0 / 3600.0)
                for o in objects
            )
            if not already_present:
                objects.insert(0, {
                    "name": target_name, "ra_deg": target_ra, "dec_deg": target_dec,
                    "otype": "", "_sep": _angular_separation_deg(target_ra, target_dec, center),
                })
                if sort_key is None:
                    objects.sort(key=lambda o: o["_sep"])
                else:
                    objects.sort(key=sort_key)

    if min_separation_deg is None:
        min_separation_deg = max(radius_deg / 15.0, 0.02)

    kept = []
    kept_coords = []
    for obj in objects:
        c = None
        try:
            c = SkyCoord(ra=obj["ra_deg"] * u.deg, dec=obj["dec_deg"] * u.deg)
        except Exception:
            pass
        if c is not None and any(
                float(c.separation(kc).deg) < min_separation_deg for kc in kept_coords):
            continue  # troppo vicino a un'etichetta già selezionata: scartato
        kept.append(obj)
        if c is not None:
            kept_coords.append(c)
        if len(kept) >= max_objects:
            break

    for obj in kept:
        obj.pop("_sep", None)
    return kept


def find_notable_objects(center, radius_deg, max_objects=60,
                          target_name=None, target_ra=None, target_dec=None,
                          min_separation_deg=None):
    """Cerca su SIMBAD (richiede Internet), per POSIZIONE su tutto il
    campo, gli oggetti 'notevoli' presenti (galassie, nebulose, ammassi).

    Un campo attorno a una galassia grande e ben studiata come M 31 può
    contenere centinaia di voci di cataloghi scientifici specialistici
    (sorgenti a raggi X, associazioni stellari, sorgenti infrarosse
    puntiformi da survey come 2MASS o Pan-STARRS...) che su SIMBAD non
    risultano "stelle semplici" ma che non sono affatto quello che ci si
    aspetta di vedere etichettato su una foto amatoriale. Per questo qui
    si tengono solo gli oggetti con una designazione nei cataloghi
    storici/divulgativi Messier, NGC o IC (lo stesso livello usato ad es.
    da Astrometry.net per le sue foto annotate), scartando tutto il resto.

    I candidati vengono raccolti tutti, ordinati per distanza dal centro
    del campo e poi decluttered (vedi _sort_and_declutter) prima di
    applicare max_objects, così restano gli oggetti davvero dentro
    l'inquadratura invece di quelli ai bordi del cerchio di ricerca. Se
    target_name/target_ra/target_dec sono forniti (l'oggetto che l'utente
    ha cercato per questa sessione), viene garantito che compaia comunque
    tra i risultati anche se SIMBAD non lo restituisce fra i primi.

    Ritorna (lista_di_dict, None) in caso di successo (lista vuota se non
    c'è nulla di notevole nel campo), oppure (None, errore)."""
    try:
        from astroquery.simbad import Simbad
        import astropy.units as u
    except ImportError:
        return None, tr("Per cercare gli oggetti nel campo serve la libreria 'astroquery'.")

    try:
        custom = Simbad()
        try:
            custom.add_votable_fields("otype")
        except Exception:
            pass
        try:
            custom.add_votable_fields("ids")
        except Exception:
            pass
        custom.TIMEOUT = 60
        result = _run_with_timeout(
            custom.query_region, 90, center, radius=radius_deg * u.deg)
    except TimeoutError as exc:
        return None, tr("Il server SIMBAD non ha risposto entro il tempo massimo ({exc}); "
                         "potrebbe essere molto carico. Riprova più tardi.").format(exc=exc)
    except Exception as exc:
        return None, tr("Interrogazione SIMBAD non riuscita (verifica la connessione Internet): {exc}").format(exc=exc)

    objects = []
    if result is not None and len(result) > 0:
        colnames = result.colnames

        def col(row, *candidates):
            for c in candidates:
                if c in colnames:
                    return row[c]
            return None

        for row in result:
            otype = col(row, "otype", "OTYPE")
            otype_str = str(otype) if otype is not None else ""
            if otype_str.startswith("*"):
                continue  # stella: non è un DSO, resta eventualmente al livello stelle luminose
            ra_val = col(row, "ra", "RA")
            dec_val = col(row, "dec", "DEC")
            main_id = col(row, "main_id", "MAIN_ID")
            ids_val = col(row, "ids", "IDS")
            display_name = _best_catalog_name(main_id, ids_val)
            if display_name is None:
                continue  # non ha una designazione Messier/NGC/IC: scartato
            if ra_val is None or dec_val is None:
                continue
            try:
                ra_deg = float(ra_val)
                dec_deg = float(dec_val)
            except (TypeError, ValueError):
                continue
            objects.append({
                "name": display_name,
                "ra_deg": ra_deg,
                "dec_deg": dec_deg,
                "otype": otype_str,
            })

    kept = _sort_and_declutter(
        objects, center, radius_deg, max_objects, min_separation_deg,
        target_name=target_name, target_ra=target_ra, target_dec=target_dec)
    return kept, None


def find_bright_named_stars(center, radius_deg, mag_limit=7.0, max_stars=25,
                             min_separation_deg=None):
    """Cerca su SIMBAD (richiede Internet) le stelle presenti nel campo che
    hanno un nome leggibile: nome proprio (es. 'Polaris'), designazione di
    Bayer/Flamsteed (es. 'alf And', '51 And') o sigla HD - vedi
    _best_star_name. Sostituisce la precedente ricerca sull'archivio Gaia:
    quelle stelle, per quanto numerose, erano etichettate solo con il loro
    ID numerico Gaia DR3 (es. "Gaia DR3 375161480591622272"), un codice
    senza alcun significato per chi guarda la foto - le stelle senza un
    nome leggibile su SIMBAD vengono qui scartate per lo stesso motivo,
    piuttosto che mostrate con una sigla altrettanto illeggibile.

    La magnitudine (per applicare mag_limit) viene cercata in
    un'interrogazione SEPARATA da quella di tipo/nome: il nome del campo
    votable per il flusso in banda V è cambiato più volte fra le versioni
    di astroquery, e se quella ricerca fallisce le stelle già trovate
    restano comunque in elenco senza filtro di magnitudine, piuttosto che
    sparire tutte (sono già solo stelle con un nome riconosciuto, un
    insieme intrinsecamente piccolo, quindi non affollano comunque la
    foto).

    Ritorna (lista_di_dict, None) in caso di successo (lista vuota se non
    ci sono stelle con nome nel campo), oppure (None, errore)."""
    try:
        from astroquery.simbad import Simbad
        import astropy.units as u
    except ImportError:
        return None, tr("Per cercare le stelle nel campo serve la libreria 'astroquery'.")

    try:
        custom = Simbad()
        try:
            custom.add_votable_fields("otype")
        except Exception:
            pass
        try:
            custom.add_votable_fields("ids")
        except Exception:
            pass
        custom.TIMEOUT = 60
        result = _run_with_timeout(
            custom.query_region, 90, center, radius=radius_deg * u.deg)
    except TimeoutError as exc:
        return None, tr("Il server SIMBAD non ha risposto entro il tempo massimo ({exc}); "
                         "potrebbe essere molto carico. Riprova più tardi.").format(exc=exc)
    except Exception as exc:
        return None, tr("Interrogazione SIMBAD non riuscita (verifica la connessione Internet): {exc}").format(exc=exc)

    stars = []
    if result is not None and len(result) > 0:
        colnames = result.colnames

        def col(row, *candidates):
            for c in candidates:
                if c in colnames:
                    return row[c]
            return None

        for row in result:
            otype = col(row, "otype", "OTYPE")
            otype_str = str(otype) if otype is not None else ""
            if not otype_str.startswith("*"):
                continue  # non è una stella
            ra_val = col(row, "ra", "RA")
            dec_val = col(row, "dec", "DEC")
            if ra_val is None or dec_val is None:
                continue
            main_id = col(row, "main_id", "MAIN_ID")
            ids_val = col(row, "ids", "IDS")
            display_name = _best_star_name(main_id, ids_val)
            if display_name is None:
                continue  # nessun nome leggibile: scartata
            try:
                ra_deg = float(ra_val)
                dec_deg = float(dec_val)
            except (TypeError, ValueError):
                continue
            stars.append({
                "name": display_name,
                "ra_deg": ra_deg,
                "dec_deg": dec_deg,
                "otype": otype_str,
                "_main_id": str(main_id).strip() if main_id else None,
                "mag": None,
            })

    if stars:
        mag_by_main_id = {}
        try:
            mag_custom = Simbad()
            mag_field_added = False
            for field in ("flux(V)", "V", "flux_v"):
                try:
                    mag_custom.add_votable_fields(field)
                    mag_field_added = True
                    break
                except Exception:
                    continue
            if mag_field_added:
                mag_result = _run_with_timeout(
                    mag_custom.query_region, 90, center, radius=radius_deg * u.deg)
                if mag_result is not None and len(mag_result) > 0:
                    mag_colnames = mag_result.colnames
                    for row in mag_result:
                        main_id_val = None
                        for c in ("main_id", "MAIN_ID"):
                            if c in mag_colnames:
                                main_id_val = row[c]
                                break
                        if main_id_val is None:
                            continue
                        mag_val = None
                        for c in ("V", "FLUX_V", "flux_v", "flux(V)", "v"):
                            if c in mag_colnames and row[c] is not None:
                                mag_val = row[c]
                                break
                        if mag_val is None:
                            continue
                        try:
                            mag_by_main_id[str(main_id_val).strip()] = float(mag_val)
                        except (TypeError, ValueError):
                            continue
        except Exception:
            pass  # ricerca magnitudine non riuscita: le stelle restano senza filtro di magnitudine

        for star in stars:
            star["mag"] = mag_by_main_id.get(star.pop("_main_id"))

        # Filtra per magnitudine solo dove è nota: una stella la cui
        # magnitudine non si è potuta recuperare resta comunque in elenco
        # (vedi motivazione sopra), ma va in fondo all'ordinamento.
        stars = [s for s in stars if s["mag"] is None or s["mag"] <= mag_limit]
        stars.sort(key=lambda s: (s["mag"] is None, s["mag"] if s["mag"] is not None else 0))

    kept = _sort_and_declutter(stars, center, radius_deg, max_stars, min_separation_deg)
    for s in kept:
        s.pop("mag", None)
    return kept, None


def project_objects_to_pixels(wcs, width, height, objects):
    """Converte le coordinate RA/Dec di ciascun oggetto in coordinate
    pixel (nel sistema della soluzione WCS, cioè dell'immagine usata per
    il plate solving) tramite quella soluzione, scartando gli oggetti che
    cadono fuori dall'immagine. Ritorna una lista di dict uguali a quelli
    in ingresso con in più le chiavi 'x'/'y'."""
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    projected = []
    for obj in objects:
        try:
            coord = SkyCoord(ra=obj["ra_deg"] * u.deg, dec=obj["dec_deg"] * u.deg)
            x, y = wcs.world_to_pixel(coord)
            x, y = float(x), float(y)
        except Exception:
            continue
        if 0 <= x <= width and 0 <= y <= height:
            item = dict(obj)
            item["x"] = x
            item["y"] = y
            projected.append(item)
    return projected


def render_fits_preview(fits_path, output_path, max_size=None):
    """Converte un FITS (anche a più canali) in un JPG visualizzabile, con
    lo stesso stretch ZScale/Asinh usato nell'anteprima della finestra
    'Apri sessione', da usare come base su cui disegnare le etichette
    quando l'utente sceglie di elaborare il FITS invece del jpg (il FITS
    stesso non è disegnabile direttamente con Pillow). Se max_size è None
    mantiene la piena risoluzione (utile perché il risultato può essere
    stampato o salvato). Ritorna (True, None) o (False, errore)."""
    try:
        from astropy.io import fits
        import numpy as np
        from PIL import Image
    except ImportError:
        return False, tr("Per elaborare il FITS servono le librerie 'astropy' e 'Pillow'.")

    try:
        from fits_viewer import _zscale_asinh_stretch
    except ImportError:
        _zscale_asinh_stretch = None

    try:
        with fits.open(fits_path, memmap=False) as hdul:
            data = None
            for hdu in hdul:
                if hdu.data is not None:
                    data = hdu.data
                    break
        if data is None:
            return False, tr("Il file FITS non contiene dati immagine.")

        arr = np.asarray(data)
        arr = np.squeeze(arr)
        if arr.ndim == 3:
            if arr.shape[0] in (3, 4) and arr.shape[0] < arr.shape[-1]:
                arr = np.moveaxis(arr, 0, -1)
            arr = arr[..., :3]
        elif arr.ndim != 2:
            return False, tr("Formato dati FITS non supportato per l'anteprima.")

        arr = arr.astype(float)
        finite = arr[np.isfinite(arr)]
        if finite.size == 0:
            return False, tr("Il file FITS non contiene valori validi.")

        if _zscale_asinh_stretch is not None:
            stretched = _zscale_asinh_stretch(arr, finite)
        else:
            lo, hi = np.percentile(finite, [1.0, 99.5])
            stretched = np.clip((arr - lo) / max(hi - lo, 1e-9), 0.0, 1.0)

        img8 = (stretched * 255).astype("uint8")
        im = Image.fromarray(img8, mode="L" if img8.ndim == 2 else "RGB")
        if max_size:
            im.thumbnail(max_size)
        im.save(output_path, quality=95)
        return True, None
    except Exception as exc:
        return False, tr("Impossibile generare l'immagine dal FITS: {exc}").format(exc=exc)


def _place_label(x, y, tw, th, img_w, img_h, r, margin=4):
    """Calcola l'angolo in alto a sinistra dove disegnare un'etichetta di
    dimensioni tw x th vicino al marker (x, y) di raggio r, tenendola
    sempre interamente dentro l'immagine (img_w x img_h): di norma a
    destra del marker, ma passa a sinistra se uscirebbe dal bordo destro,
    e viene comunque "agganciata" (clampata) dentro ai margini per non
    uscire mai dall'alto, dal basso o dai lati."""
    tx = x + r + margin
    ty = y - th / 2
    if tx + tw > img_w - margin:
        tx = x - r - margin - tw
    tx = max(margin, min(tx, img_w - tw - margin))
    ty = max(margin, min(ty, img_h - th - margin))
    return tx, ty


def annotate_image(image_path, wcs_width, wcs_height, projected_objects, output_path,
                    color_notable=(255, 210, 0), color_star=(120, 220, 255)):
    """Disegna su una COPIA di image_path un piccolo cerchio più
    un'etichetta testuale per ciascun oggetto proiettato, e la salva in
    output_path (l'originale non viene mai toccato). Le coordinate pixel
    vengono riscalate da wcs_width/wcs_height (le dimensioni del file
    usato per il plate solving) alla risoluzione reale di image_path, che
    può essere diversa (es. astrometria fatta sul FITS, etichette
    disegnate sul jpg). Il testo è sempre bianco con un contorno nero
    marcato, per restare leggibile su qualunque sfondo (nero, nebulosa
    colorata, stelle luminose...); il colore del solo cerchietto distingue
    gli oggetti SIMBAD (color_notable) dalle stelle Gaia (color_star). Le
    etichette vengono sempre tenute interamente dentro l'immagine, senza
    uscire dai bordi. Ritorna (True, None) o (False, errore)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False, tr("Per disegnare le etichette serve la libreria 'Pillow'.")

    try:
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            img_w, img_h = im.size
            scale_x = img_w / wcs_width if wcs_width else 1.0
            scale_y = img_h / wcs_height if wcs_height else 1.0

            draw = ImageDraw.Draw(im)
            font_size = max(14, img_w // 110)
            try:
                font = ImageFont.truetype("arial.ttf", size=font_size)
            except Exception:
                font = ImageFont.load_default()

            r = max(4, img_w // 260)
            stroke_width = max(2, font_size // 7)
            for obj in projected_objects:
                x = obj["x"] * scale_x
                y = obj["y"] * scale_y
                is_star = "mag" in obj
                circle_color = color_star if is_star else color_notable
                draw.ellipse([x - r, y - r, x + r, y + r], outline=circle_color, width=2)

                label = obj["name"]
                bbox = draw.textbbox((0, 0), label, font=font, stroke_width=stroke_width)
                tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
                tx, ty = _place_label(x, y, tw, th, img_w, img_h, r)
                # bbox[0]/[1] possono non essere 0 (metriche del font): li
                # sottraiamo per allineare esattamente il testo alla
                # posizione calcolata.
                draw.text((tx - bbox[0], ty - bbox[1]), label, fill=(255, 255, 255), font=font,
                           stroke_width=stroke_width, stroke_fill=(0, 0, 0))

            im.save(output_path, quality=92)
        return True, None
    except Exception as exc:
        return False, tr("Impossibile generare l'immagine con le etichette: {exc}").format(exc=exc)


# ---------------------------------------------------------------------
# Metodologia alternativa: Astrometry.net locale, dentro WSL.
# ---------------------------------------------------------------------

_WIN_DRIVE_RE = re.compile(r'^([A-Za-z]):[\\/](.*)$')


def windows_path_to_wsl(path):
    """Converte un percorso Windows (es. 'I:\\cartella\\file.fits') nel
    corrispondente percorso visto da dentro WSL (es.
    '/mnt/i/cartella/file.fits'). Se il percorso non ha una lettera di
    unità riconoscibile, si limita a normalizzare i separatori."""
    m = _WIN_DRIVE_RE.match(path)
    if not m:
        return path.replace("\\", "/")
    drive_letter = m.group(1).lower()
    rest = m.group(2).replace("\\", "/")
    return f"/mnt/{drive_letter}/{rest}"


def _wsl_to_windows_path(wsl_path, timeout=15):
    """Chiede a WSL (wslpath -w) il percorso Windows corrispondente a un
    percorso WSL, così i file prodotti da Astrometry.net dentro WSL
    possono poi essere letti/copiati con le normali funzioni Python: WSL2
    espone il proprio filesystem a Windows tramite \\\\wsl$\\<distro>\\...
    indipendentemente dal nome della distribuzione o dell'utente Linux,
    che quindi non serve conoscere. Ritorna (percorso, None) o
    (None, errore)."""
    try:
        proc = subprocess.run(
            ["wsl.exe", "--cd", "~", "-e", "wslpath", "-w", wsl_path],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        return None, tr("Non trovo wsl.exe: il Sottosistema Windows per Linux (WSL) non "
                         "risulta installato su questo PC.")
    except subprocess.TimeoutExpired:
        return None, tr("WSL non ha risposto in tempo utile.")
    except OSError as exc:
        return None, tr("Impossibile avviare WSL: {exc}").format(exc=exc)
    out = (proc.stdout or "").strip()
    if proc.returncode != 0 or not out:
        detail = (proc.stderr or proc.stdout or "").strip()
        detail_bit = f" Dettagli: {detail}" if detail else ""
        return None, tr("Impossibile tradurre il percorso WSL in percorso Windows.{detail_bit}").format(detail_bit=detail_bit)
    return out, None


def _cleanup_wsl_scratch(scratch_dir_wsl):
    """Elimina (best-effort, senza sollevare eccezioni) la cartella di
    lavoro temporanea dentro WSL usata per una risoluzione: non è
    essenziale (finisce comunque in /tmp, che WSL2 svuota ai riavvii), ma
    evita di accumulare file inutili tra un'elaborazione e l'altra."""
    try:
        subprocess.run(["wsl.exe", "--cd", "~", "-e", "rm", "-rf", scratch_dir_wsl],
                        capture_output=True, timeout=15)
    except Exception:
        pass


def _parse_field_objects_count(stdout_text):
    """Conta le righe che solve-field elenca dopo 'Your field contains:'
    (una per oggetto notevole/stella con nome riconosciuto nel campo) -
    solo per il messaggio di completamento mostrato all'utente, non
    essenziale al funzionamento."""
    count = 0
    in_list = False
    for line in stdout_text.splitlines():
        if "Your field contains:" in line:
            in_list = True
            continue
        if in_list:
            if line.strip() == "":
                break
            count += 1
    return count


def solve_and_annotate_astrometry_net(image_path, ra_hint=None, dec_hint=None,
                                       radius_hint_deg=5.0, downsample=2,
                                       timeout=300, progress_cb=None):
    """Risolve astrometricamente image_path ed etichetta il campo usando
    Astrometry.net installato in locale dentro WSL (comando 'solve-field',
    lanciato da Windows tramite wsl.exe, sulla distribuzione WSL
    predefinita) - alternativa offline a SIMBAD: a differenza di quel
    percorso, qui è Astrometry.net stesso a produrre l'immagine annotata
    (con i propri cataloghi), non viene interrogato SIMBAD né disegnato
    nulla da questo modulo.

    A differenza della risoluzione con Siril (che richiede sempre il FITS
    quando disponibile, per via della dimensione pixel/focale nell'header),
    Astrometry.net risolve "alla cieca" dal solo contenuto dell'immagine:
    image_path può quindi essere indifferentemente il FITS o il jpg dello
    stack - è lo stesso identico file su cui Astrometry.net disegna poi
    l'annotazione.

    ra_hint/dec_hint (gradi decimali, opzionali) restringono la ricerca
    attorno alla posizione nota del target, velocizzando parecchio la
    risoluzione; radius_hint_deg è il raggio di ricerca (gradi) attorno a
    quel punto (non deve corrispondere all'ampiezza del campo inquadrato:
    basta che il centro del campo sia entro questo raggio dalla posizione
    indicata). progress_cb, se fornito, viene richiamato con brevi
    messaggi di stato testuali.

    Ritorna (dict, None) in caso di successo - con 'annotated_path' (un
    file temporaneo Windows con l'immagine annotata; il chiamante decide
    se copiarlo altrove) e 'n_field_objects' (quanti oggetti Astrometry.net
    elenca come presenti nel campo) - oppure (None, errore)."""
    if not image_path or not os.path.isfile(image_path):
        return None, tr("File immagine non trovato: {path}").format(path=image_path)

    def emit(msg):
        if progress_cb:
            try:
                progress_cb(msg)
            except Exception:
                pass

    wsl_image_path = windows_path_to_wsl(image_path)
    scratch_id = uuid.uuid4().hex[:12]
    scratch_dir_wsl = f"/tmp/dwarf_catalog_astrometry/{scratch_id}"

    # --cd ~: forza la directory di lavoro dentro WSL sulla home dell'utente
    # Linux, invece di ereditare (come fa wsl.exe di norma) la cartella
    # Windows corrente di chi lancia il programma. Senza, se quella cartella
    # fosse ad es. quella del programma stesso, python3 -m (usato
    # internamente da solve-field per convertire l'immagine) potrebbe
    # anteporla al percorso di ricerca dei moduli e trovare lì un file
    # chiamato "astrometry" prima del vero pacchetto astrometry.net.
    cmd = ["wsl.exe", "--cd", "~", "-e", "solve-field", "--overwrite",
           "--downsample", str(downsample), "-D", scratch_dir_wsl]
    if ra_hint is not None and dec_hint is not None:
        cmd += ["--ra", f"{ra_hint:.6f}", "--dec", f"{dec_hint:.6f}",
                "--radius", f"{radius_hint_deg:.2f}"]
    cmd.append(wsl_image_path)

    emit(tr("Astrometria (Astrometry.net locale): avvio di solve-field dentro WSL…"))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return None, tr("Non trovo wsl.exe: il Sottosistema Windows per Linux (WSL) non "
                         "risulta installato su questo PC.")
    except subprocess.TimeoutExpired:
        return None, tr("Astrometry.net non ha risolto entro il tempo massimo previsto "
                         "({timeout}s).").format(timeout=timeout)
    except OSError as exc:
        return None, tr("Impossibile avviare WSL: {exc}").format(exc=exc)

    output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if "solve-field: command not found" in output or "solve-field: not found" in output:
        return None, tr("'solve-field' non è installato dentro WSL. Da terminale Ubuntu: "
                         "sudo apt install astrometry.net astrometry-data-2mass-08-19 "
                         "astrometry-data-tycho2")

    emit(tr("Astrometria (Astrometry.net locale): recupero dei risultati da WSL…"))
    scratch_dir_win, path_err = _wsl_to_windows_path(scratch_dir_wsl)
    if path_err:
        return None, path_err

    base = os.path.splitext(os.path.basename(image_path))[0]
    solved_marker = os.path.join(scratch_dir_win, base + ".solved")
    ngc_png = os.path.join(scratch_dir_win, base + "-ngc.png")

    if not os.path.isfile(solved_marker):
        detail = output.strip()
        detail_bit = f"\n\nDettagli:\n{detail[-1500:]}" if detail else ""
        _cleanup_wsl_scratch(scratch_dir_wsl)
        return None, tr("Astrometry.net non è riuscito a risolvere l'immagine (nessuna "
                         "corrispondenza trovata nei cataloghi installati in WSL). Verifica "
                         "di avere installato indici sufficienti per il campo di questa foto "
                         "(vedi 'astrometry-data-2mass-08-19'/'astrometry-data-tycho2').{detail_bit}").format(detail_bit=detail_bit)
    if not os.path.isfile(ngc_png):
        _cleanup_wsl_scratch(scratch_dir_wsl)
        return None, tr("Astrometry.net ha risolto l'immagine ma non ha generato il grafico "
                         "annotato (-ngc.png). Verifica l'installazione di WSL.")

    fd, temp_path = tempfile.mkstemp(suffix="_annotated_astrometry.png")
    os.close(fd)
    try:
        shutil.copy2(ngc_png, temp_path)
    except Exception as exc:
        _cleanup_wsl_scratch(scratch_dir_wsl)
        return None, tr("Impossibile copiare l'immagine annotata da WSL: {exc}").format(exc=exc)

    _cleanup_wsl_scratch(scratch_dir_wsl)

    return {
        "annotated_path": temp_path,
        "n_field_objects": _parse_field_objects_count(proc.stdout or ""),
    }, None
