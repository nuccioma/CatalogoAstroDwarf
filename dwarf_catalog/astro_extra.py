"""
astro_extra.py - Funzioni astronomiche aggiuntive basate su astropy (e,
dove serve, sulle librerie collegate astroquery/photutils):

  1. resolve_object(): identificazione dell'oggetto tramite interrogazione
     online di SIMBAD (astroquery) a partire dal nome target della cartella
     sessione -> tipo, costellazione, magnitudine, coordinate RA/Dec.
  2. compute_observation_conditions(): condizioni osservative al momento
     della ripresa (astropy.coordinates + astropy.time) -> altezza/azimut
     dell'oggetto, fase lunare, distanza dalla Luna.
  3. analyze_raw_quality(): controllo qualità di un singolo raw FITS
     (astropy.stats + photutils) -> stelle rilevate, FWHM medio, sfondo.

Tutte le funzioni sono difensive: se una libreria richiesta non è
installata, o l'operazione fallisce (es. nessuna connessione a Internet
per SIMBAD), ritornano un errore testuale invece di sollevare un'eccezione,
così la GUI può mostrare un messaggio invece di bloccarsi.
"""

import datetime
import re

from i18n import tr


# Cataloghi come M/NGC/IC/HD/... sono sensibili alla spaziatura tra il
# prefisso e il numero nell'indice dei nomi di SIMBAD ("M 31" e "M31" non
# sono sempre trattati allo stesso modo): questa regex serve a generare
# entrambe le varianti a partire da un nome tipo "M31" o "M 31".
_CATALOG_PREFIX_RE = re.compile(r'^([A-Za-z]+)\s*(\d.*)$')


def _name_variants(name):
    """Ritorna una lista di varianti ragionevoli del nome (con/senza spazio
    tra prefisso del catalogo e numero) da provare in sequenza."""
    name = name.strip()
    variants = [name]
    m = _CATALOG_PREFIX_RE.match(name)
    if m:
        prefix, rest = m.group(1), m.group(2)
        for variant in (f"{prefix} {rest}", f"{prefix}{rest}"):
            if variant not in variants:
                variants.append(variant)
    return variants


def format_ra_hms(ra_deg, precision=1):
    """Formatta un'ascensione retta (gradi decimali) come stringa
    sessagesimale del tipo '00h 42m 44.3s'. Ritorna None se ra_deg è None o
    la formattazione non riesce."""
    if ra_deg is None:
        return None
    try:
        from astropy.coordinates import Angle
        import astropy.units as u
        return Angle(ra_deg, unit=u.deg).to_string(
            unit=u.hourangle, sep=("h ", "m ", "s"), precision=precision, pad=True)
    except Exception:
        return None


def format_dec_dms(dec_deg, precision=0):
    """Formatta una declinazione (gradi decimali) come stringa sessagesimale
    del tipo '+41° 16' 09\"'. Ritorna None se dec_deg è None o la
    formattazione non riesce."""
    if dec_deg is None:
        return None
    try:
        from astropy.coordinates import Angle
        import astropy.units as u
        return Angle(dec_deg, unit=u.deg).to_string(
            unit=u.deg, sep=("° ", "' ", '"'), precision=precision, alwayssign=True, pad=True)
    except Exception:
        return None


def resolve_object(target_name):
    """Identifica l'oggetto a partire dal nome target della sessione.

    Le coordinate vengono risolte tramite il resolver di nomi CDS/Sesame
    (astropy SkyCoord.from_name), lo stesso usato da planetari e software
    professionali: gestisce in modo affidabile varianti come 'M31'/'M 31'/
    'NGC224'/'NGC 224'. Solo DOPO aver ottenuto una posizione, i metadati
    dell'oggetto (tipo, magnitudine, nome principale) vengono cercati su
    SIMBAD interrogando quella POSIZIONE (query_region), non il nome: così
    un'interrogazione testuale ambigua non può restituire un oggetto
    diverso (es. 'M31' scambiato per un'altra sorgente non correlata).

    Ritorna una tupla (info_dict, errore). info_dict, se presente, contiene:
    object_type, constellation, magnitude, object_name_resolved, ra_deg,
    dec_deg (questi ultimi due sempre validi se info_dict non è None)."""
    if not target_name or not target_name.strip():
        return None, tr("Nessun nome target per questa sessione.")

    try:
        from astropy.coordinates import SkyCoord, get_constellation
        import astropy.units as u
    except ImportError:
        return None, tr("Per identificare l'oggetto serve la libreria 'astropy'.")

    name = target_name.strip()
    variants = _name_variants(name)

    coord = None
    last_error = None

    # 1) Risoluzione delle coordinate tramite il resolver di nomi CDS/Sesame:
    #    il modo più robusto per nomi comuni (Messier, NGC, IC, stelle...).
    for variant in variants:
        try:
            coord = SkyCoord.from_name(variant)
            break
        except Exception as exc:
            last_error = exc

    # 2) Ripiego: se Sesame non è raggiungibile, prova l'interrogazione
    #    diretta per identificativo su SIMBAD (stesse varianti di nome).
    if coord is None:
        try:
            from astroquery.simbad import Simbad
        except ImportError:
            return None, tr("Per identificare l'oggetto serve la libreria 'astroquery' "
                             "(pip install astroquery).")
        for variant in variants:
            try:
                result = Simbad.query_object(variant)
            except Exception as exc:
                last_error = exc
                continue
            if result is None or len(result) == 0:
                continue
            row = result[0]
            colnames = result.colnames
            ra_val = row["ra"] if "ra" in colnames else (row["RA"] if "RA" in colnames else None)
            dec_val = row["dec"] if "dec" in colnames else (row["DEC"] if "DEC" in colnames else None)
            if ra_val is None or dec_val is None:
                continue
            try:
                # Nelle versioni recenti di astroquery ra/dec sono già gradi decimali.
                coord = SkyCoord(ra=float(ra_val) * u.deg, dec=float(dec_val) * u.deg)
            except Exception:
                try:
                    coord = SkyCoord(str(ra_val), str(dec_val), unit=(u.hourangle, u.deg))
                except Exception as exc:
                    last_error = exc
                    continue
            break

    if coord is None:
        detail = f" ({last_error})" if last_error else ""
        return None, tr("Nessun oggetto trovato per '{name}'. Verifica il nome (es. "
                         "'M 31' oppure 'M31') e la connessione Internet.{detail}").format(
            name=target_name, detail=detail)

    ra_deg = float(coord.ra.deg)
    dec_deg = float(coord.dec.deg)

    info = {
        "object_type": None,
        "constellation": None,
        "magnitude": None,
        "object_name_resolved": name,
        "ra_deg": ra_deg,
        "dec_deg": dec_deg,
    }

    try:
        info["constellation"] = get_constellation(coord)
    except Exception:
        pass

    # 3) Metadati opzionali (tipo, nome principale): ricerca SIMBAD per
    #    posizione attorno alle coordinate appena risolte, con un raggio
    #    piccolo (10 arcsec). Se questa parte fallisce (libreria assente,
    #    servizio non raggiungibile, campo non disponibile in questa
    #    versione di astroquery) le coordinate restano comunque valide: i
    #    metadati restano semplicemente vuoti.
    #
    #    Il nome del campo votable per la magnitudine è cambiato più volte
    #    fra le versioni di astroquery (es. "V" vs "flux(V)"): per questo è
    #    cercata in un'interrogazione separata, così un nome di campo non
    #    più valido per la magnitudine non impedisce comunque di ottenere
    #    almeno il tipo e il nome dell'oggetto qui sopra.
    try:
        from astroquery.simbad import Simbad
        custom = Simbad()
        try:
            custom.add_votable_fields("otype")
        except Exception:
            pass
        region_result = custom.query_region(coord, radius=10 * u.arcsec)
        if region_result is not None and len(region_result) > 0:
            row = region_result[0]
            colnames = region_result.colnames

            def col(*candidates):
                for c in candidates:
                    if c in colnames:
                        return row[c]
                return None

            otype = col("otype", "OTYPE")
            resolved_name = col("main_id", "MAIN_ID")
            if otype is not None:
                info["object_type"] = str(otype)
            if resolved_name is not None:
                info["object_name_resolved"] = str(resolved_name).strip()
    except Exception:
        pass

    try:
        from astroquery.simbad import Simbad
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
            mag_result = mag_custom.query_region(coord, radius=10 * u.arcsec)
            if mag_result is not None and len(mag_result) > 0:
                row = mag_result[0]
                colnames = mag_result.colnames
                for c in ("V", "FLUX_V", "flux_v", "flux(V)", "v"):
                    if c in colnames and row[c] is not None:
                        try:
                            info["magnitude"] = float(row[c])
                        except (TypeError, ValueError):
                            pass
                        break
    except Exception:
        pass

    return info, None


def compute_observation_conditions(ra_deg, dec_deg, session_datetime_iso, lat_deg, lon_deg,
                                    elevation_m=0.0):
    """Calcola altezza/azimut dell'oggetto e condizioni lunari al momento
    della ripresa. session_datetime_iso è un ISO datetime NAIVE, assunto
    espresso nel fuso orario del sistema (viene convertito correttamente in
    UTC tenendo conto dell'ora legale/solare per quella data specifica).
    Ritorna (info_dict, errore)."""
    if ra_deg is None or dec_deg is None:
        return None, tr("Coordinate dell'oggetto non disponibili (identifica prima l'oggetto).")
    if lat_deg is None or lon_deg is None:
        return None, tr("Posizione dell'osservatore non configurata.")
    if not session_datetime_iso:
        return None, tr("Data/ora della sessione non disponibile.")

    try:
        from astropy.coordinates import EarthLocation, AltAz, SkyCoord, get_body
        from astropy.time import Time
        import astropy.units as u
    except ImportError:
        return None, tr("Per le condizioni osservative serve la libreria 'astropy'.")

    try:
        naive_dt = datetime.datetime.fromisoformat(session_datetime_iso)
        # Il datetime salvato è "ora locale del computer/telescopio al momento
        # dello scatto": astimezone() senza argomenti lo interpreta come tale
        # e lo converte correttamente in UTC (tenendo conto dell'ora legale
        # in vigore in quella data specifica).
        local_aware = naive_dt.astimezone()
        utc_dt = local_aware.astimezone(datetime.timezone.utc)

        location = EarthLocation(lat=lat_deg * u.deg, lon=lon_deg * u.deg, height=elevation_m * u.m)
        obstime = Time(utc_dt)
        altaz_frame = AltAz(obstime=obstime, location=location)

        target = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg)
        target_altaz = target.transform_to(altaz_frame)

        moon = get_body("moon", obstime, location)
        sun = get_body("sun", obstime, location)
        moon_altaz = moon.transform_to(altaz_frame)
        moon_separation = float(target.separation(moon).deg)

        # fase lunare dall'angolo di fase Sole-Terra-Luna
        import numpy as np
        phase_angle = np.arccos(
            np.clip(np.sin(sun.dec.rad) * np.sin(moon.dec.rad)
                    + np.cos(sun.dec.rad) * np.cos(moon.dec.rad) * np.cos(sun.ra.rad - moon.ra.rad), -1, 1)
        )
        moon_phase_pct = float((1 + np.cos(phase_angle)) / 2 * 100)

        return {
            "altitude_deg": float(target_altaz.alt.deg),
            "azimuth_deg": float(target_altaz.az.deg),
            "moon_phase_pct": moon_phase_pct,
            "moon_separation_deg": moon_separation,
            "moon_altitude_deg": float(moon_altaz.alt.deg),
        }, None
    except Exception as exc:
        return None, tr("Impossibile calcolare le condizioni osservative: {exc}").format(exc=exc)


# Chiavi di header FITS usate (in ordine) per rilevare che il piano 2D
# contenuto nel file è un mosaico Bayer/CFA grezzo, non ancora demosaicato.
_BAYER_HEADER_KEYS = ("BAYERPAT", "COLORTYP", "CFAIMAGE", "CFATYPE")


def _detect_bayer_pattern(header):
    """Cerca nell'header FITS un'indicazione che il piano immagine è un
    mosaico Bayer/CFA grezzo (non demosaicato). Ritorna la stringa del
    pattern (es. 'RGGB') se trovata, altrimenti None."""
    for key in _BAYER_HEADER_KEYS:
        try:
            val = header.get(key) if header is not None else None
        except Exception:
            val = None
        if val:
            return str(val).strip().upper()
    return None


def _debayer_green_plane(arr, pattern):
    """Estrae dal mosaico Bayer/CFA grezzo di un raw un singolo piano 'verde'
    a risoluzione dimezzata, pensato per l'analisi di qualità (stelle/FWHM).

    I raw FITS del Dwarf sono un mosaico Bayer non demosaicato: passarlo così
    com'è a un cercatore di stelle (pensato per immagini monocromatiche) fa
    scambiare i singoli pixel del reticolo, sotto ogni stella reale, per
    tante sorgenti separate e strettissime, gonfiando il conteggio delle
    stelle e restituendo un FWHM molto più piccolo di quello reale. Il canale
    verde (metà dei pixel di un sensore Bayer, distribuiti a scacchiera) dà
    invece un piano continuo e privo di questo artefatto, senza bisogno di
    una vera interpolazione a colori (non serve per questo controllo di
    qualità, solo per stimare stelle e nitidezza).

    'pattern' è la stringa del pattern Bayer già rilevata da
    _detect_bayer_pattern() (es. 'RGGB'), o None se non nota: in tal caso si
    assume RGGB (il più comune).

    Ritorna (piano_verde, fattore_scala_fwhm): il piano estratto ha
    risoluzione dimezzata in ogni direzione, quindi il FWHM misurato su di
    esso va moltiplicato per fattore_scala_fwhm (2.0) per essere confrontabile
    con la scala pixel dell'immagine originale."""
    # In tutti i pattern Bayer standard (RGGB/BGGR/GRBG/GBRG) il verde sta
    # sempre sulla stessa diagonale a scacchiera: se il pattern inizia con
    # 'G' il verde è dove (riga+colonna) è pari, altrimenti dove è dispari.
    green_at_even = bool(pattern and pattern[0] == "G")
    if green_at_even:
        g1 = arr[0::2, 0::2]
        g2 = arr[1::2, 1::2]
    else:
        g1 = arr[0::2, 1::2]
        g2 = arr[1::2, 0::2]
    h = min(g1.shape[0], g2.shape[0])
    w = min(g1.shape[1], g2.shape[1])
    green = (g1[:h, :w] + g2[:h, :w]) / 2.0
    return green, 2.0


def analyze_raw_quality(file_path, fwhm_guess=3.0, threshold_sigma=5.0):
    """Analizza un singolo file FITS raw: sfondo (media/rumore con sigma
    clipping) e stelle rilevate con FWHM medio (photutils). Ritorna
    (info_dict, errore). info_dict contiene sempre background_mean e
    background_noise se il file è leggibile; star_count/fwhm_px sono None
    se photutils non è disponibile o non rileva sorgenti.

    Se l'header FITS indica che il piano immagine è un mosaico Bayer/CFA
    grezzo (vedi _debayer_green_plane), l'analisi lavora su un canale verde
    estratto invece che sul mosaico intero, per non falsare stelle/FWHM. I
    FITS già a colori (3 canali) o senza indicazioni di mosaico nell'header
    (es. gli stack, già demosaicati) non sono toccati da questa correzione."""
    try:
        from astropy.io import fits
        from astropy.stats import sigma_clipped_stats
    except ImportError:
        return None, tr("Per il controllo di qualità serve la libreria 'astropy'.")

    try:
        with fits.open(file_path, memmap=False) as hdul:
            data = None
            header = None
            for hdu in hdul:
                if hdu.data is not None:
                    data = hdu.data
                    header = hdu.header
                    break
    except Exception as exc:
        return None, tr("Impossibile leggere il file FITS: {exc}").format(exc=exc)

    if data is None:
        return None, tr("Il file FITS non contiene dati immagine.")

    fwhm_scale = 1.0
    try:
        import numpy as np
        arr = np.asarray(data)
        arr = np.squeeze(arr)
        if arr.ndim == 3:
            # dati a colori: usa la luminanza per l'analisi
            if arr.shape[0] in (3, 4) and arr.shape[0] < arr.shape[-1]:
                arr = np.moveaxis(arr, 0, -1)
            arr = arr[..., :3].mean(axis=-1)
        elif arr.ndim == 2:
            pattern_hint = _detect_bayer_pattern(header)
            if pattern_hint:
                arr, fwhm_scale = _debayer_green_plane(arr, pattern_hint)
        arr = arr.astype(float)
    except Exception as exc:
        return None, tr("Impossibile elaborare i dati immagine: {exc}").format(exc=exc)

    try:
        mean, median, std = sigma_clipped_stats(arr, sigma=3.0)
    except Exception as exc:
        return None, tr("Impossibile calcolare le statistiche di sfondo: {exc}").format(exc=exc)

    star_count = None
    fwhm_px = None
    try:
        from photutils.detection import IRAFStarFinder
        finder = IRAFStarFinder(threshold=threshold_sigma * std, fwhm=fwhm_guess)
        sources = finder(arr - median)
        if sources is not None and len(sources) > 0:
            star_count = len(sources)
            fwhm_px = float(np.mean(sources["fwhm"])) * fwhm_scale
        else:
            star_count = 0
    except ImportError:
        pass  # photutils non installato: si torna comunque lo sfondo
    except Exception:
        pass  # rilevamento stelle fallito su questo file: non bloccante

    return {
        "background_mean": float(mean),
        "background_noise": float(std),
        "star_count": star_count,
        "fwhm_px": fwhm_px,
    }, None
