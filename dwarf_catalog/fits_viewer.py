"""
fits_viewer.py - Utility per la finestra "Apri sessione" della GUI: carica
un'anteprima visualizzabile (QPixmap) e, per i file FITS, anche il testo
dell'header.

Le immagini standard (jpg/png/tiff/bmp) vengono aperte con Pillow. I file
FITS richiedono astropy (per leggere dati e header) e numpy (dipendenza di
astropy, quindi già presente se astropy è installato) per lo stretch dei
valori in un'immagine 8 bit visualizzabile. Se astropy non è installato, la
finestra resta comunque utilizzabile: mostra un messaggio invece
dell'anteprima per i soli file FITS.
"""

import io
import os

from PyQt6.QtGui import QPixmap

from i18n import tr

RAW_EXTENSIONS_VIEW = {".fits", ".fit"}
IMAGE_EXTENSIONS_VIEW = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}


def classify_file_kind(path):
    """Ritorna 'fits', 'image' o 'other' in base all'estensione del file."""
    ext = os.path.splitext(path)[1].lower()
    if ext in RAW_EXTENSIONS_VIEW:
        return "fits"
    if ext in IMAGE_EXTENSIONS_VIEW:
        return "image"
    return "other"


def load_image_pixmap(file_path, max_size=(760, 760)):
    """Carica un'immagine standard (jpg/png/tiff/bmp) e ritorna un QPixmap
    ridimensionato, o None in caso di errore."""
    try:
        from PIL import Image
        with Image.open(file_path) as im:
            im = im.convert("RGB")
            im.thumbnail(max_size)
            buf = io.BytesIO()
            im.save(buf, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue())
        return pixmap if not pixmap.isNull() else None
    except Exception:
        return None


def load_fits_preview(file_path, max_size=(760, 760)):
    """Carica un file FITS. Ritorna una tupla (pixmap_o_None, header_text,
    messaggio_errore_o_None). header_text è sempre una stringa (vuota se
    l'header non è leggibile); messaggio_errore è non-None solo quando non è
    stato possibile produrre un'anteprima immagine."""
    try:
        from astropy.io import fits
    except ImportError:
        return None, "", tr("Per visualizzare i file FITS è necessario installare 'astropy' "
                             "(pip install astropy).")

    try:
        with fits.open(file_path, memmap=False) as hdul:
            data = None
            header = None
            for hdu in hdul:
                if hdu.data is not None:
                    data = hdu.data
                    header = hdu.header
                    break
            if header is None and len(hdul) > 0:
                header = hdul[0].header
    except Exception as exc:
        return None, "", tr("Impossibile leggere il file FITS: {exc}").format(exc=exc)

    header_text = _format_fits_header(header) if header is not None else ""

    if data is None:
        return None, header_text, tr("Il file FITS non contiene dati immagine (solo header).")

    pixmap = _fits_data_to_pixmap(data, max_size)
    if pixmap is None:
        return None, header_text, tr("Impossibile generare un'anteprima dai dati immagine del FITS.")
    return pixmap, header_text, None


def _format_fits_header(header):
    lines = []
    for card in header.cards:
        keyword = card.keyword
        if not keyword or keyword in ("COMMENT", "HISTORY", ""):
            continue
        line = f"{keyword} = {card.value}"
        if card.comment:
            line += f"   / {card.comment}"
        lines.append(line)
    return "\n".join(lines)


def _zscale_asinh_stretch(arr, finite):
    """Stretch dei valori in [0,1] per la visualizzazione, usando gli
    algoritmi di astropy.visualization (ZScale per i limiti + Asinh per la
    curva, lo stesso approccio usato da strumenti come DS9): resa migliore
    sui raw deboli rispetto a un semplice stretch percentile lineare. Se
    astropy.visualization non è disponibile, ricade su uno stretch
    percentile semplice."""
    import numpy as np
    try:
        from astropy.visualization import ZScaleInterval, AsinhStretch
        vmin, vmax = ZScaleInterval().get_limits(finite)
        if vmax <= vmin:
            raise ValueError("intervallo ZScale non valido")
        normalized = np.clip((arr - vmin) / (vmax - vmin), 0.0, 1.0)
        return AsinhStretch(a=0.1)(normalized)
    except Exception:
        lo, hi = np.percentile(finite, [1.0, 99.5])
        if hi <= lo:
            lo, hi = float(finite.min()), float(finite.max())
        if hi <= lo:
            hi = lo + 1.0
        return np.clip((arr - lo) / (hi - lo), 0.0, 1.0)


def _fits_data_to_pixmap(data, max_size):
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        return None

    try:
        arr = np.asarray(data)
        arr = np.squeeze(arr)

        if arr.ndim == 3:
            # dati a colori: es. (3, H, W) oppure (H, W, 3)
            if arr.shape[0] in (3, 4) and arr.shape[0] < arr.shape[-1]:
                arr = np.moveaxis(arr, 0, -1)
            arr = arr[..., :3]
        elif arr.ndim != 2:
            return None

        arr = arr.astype(float)
        finite = arr[np.isfinite(arr)]
        if finite.size == 0:
            return None

        stretched = _zscale_asinh_stretch(arr, finite)
        img8 = (stretched * 255).astype("uint8")

        if img8.ndim == 2:
            im = Image.fromarray(img8, mode="L")
        else:
            im = Image.fromarray(img8, mode="RGB")
        im.thumbnail(max_size)

        buf = io.BytesIO()
        im.save(buf, format="PNG")
        pixmap = QPixmap()
        pixmap.loadFromData(buf.getvalue())
        return pixmap if not pixmap.isNull() else None
    except Exception:
        return None
