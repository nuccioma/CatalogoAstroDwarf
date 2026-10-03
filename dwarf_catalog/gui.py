"""
gui.py - Interfaccia grafica PyQt6 per il catalogo sessioni astronomiche
Dwarf II / Dwarf 3 / Dwarf Mini / Dwarf Draco.
"""

import os
import sys
import shutil
import logging
import datetime

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QSettings, QUrl, QDate, QTimer, QRect, QPoint
from PyQt6.QtGui import QIcon, QPixmap, QDesktopServices, QAction, QActionGroup
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QFileDialog, QCheckBox, QRadioButton, QProgressBar,
    QPlainTextEdit, QSplitter, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QAbstractItemView, QMessageBox, QStatusBar, QDateEdit, QFrame,
    QDialog, QInputDialog, QDialogButtonBox, QButtonGroup, QScrollArea, QSizePolicy,
    QLayout
)

from db import CatalogDB
from scanner import scan_root, list_session_files, refresh_session_record, ScanStats
from fits_viewer import classify_file_kind, load_image_pixmap, load_fits_preview
import file_ops
from i18n import tr, set_language, get_language, LANGUAGES

# Quando il programma è "congelato" in un eseguibile autonomo (PyInstaller),
# __file__ punta dentro una cartella temporanea di estrazione (specie in
# modalità --onefile, ricreata a ogni avvio): usare quella come cartella
# dell'app farebbe perdere impostazioni/database/miniature a ogni riavvio.
# In quel caso la cartella dell'app è invece quella del file .exe.
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
# File .ini (non registro di sistema) dove vengono salvate posizione, dimensioni,
# larghezza colonne e proporzioni degli splitter delle tre finestre, ripristinate
# all'avvio successivo.
SETTINGS_PATH = os.path.join(APP_DIR, "settings.ini")

# Foglio di stile applicato all'intera applicazione: bottoni un po' più grandi
# e leggermente colorati (azzurro), per renderli più visibili nell'interfaccia
# (richiesto da Nuccio). Si applica a tutte le finestre/dialoghi, non solo alla
# finestra principale.
APP_STYLESHEET = """
QPushButton {
    background-color: #eaf2fb;
    border: 1px solid #7fa8d0;
    border-radius: 5px;
    padding: 5px 14px;
    min-height: 22px;
    font-size: 10pt;
}
QPushButton:hover {
    background-color: #d5e6f7;
}
QPushButton:pressed {
    background-color: #b9d5ef;
}
QPushButton:disabled {
    background-color: #f0f0f0;
    color: #a0a0a0;
    border: 1px solid #cccccc;
}
"""


def make_settings():
    return QSettings(SETTINGS_PATH, QSettings.Format.IniFormat)

logger = logging.getLogger("dwarf_catalog")


def human_size(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


# --- Selezione a checkbox e azioni sui file, comuni alle tre tabelle -------
# (elenco sessioni, elenco frame di calibrazione, elenco file di una sessione)

def make_checkbox_item(user_data=None):
    """Cella con checkbox per la colonna di selezione (colonna 0) di una
    tabella. user_data (id di catalogo o percorso file) viene salvato nella
    cella stessa, così le azioni non devono più andarlo a ricercare altrove."""
    item = QTableWidgetItem()
    item.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    item.setCheckState(Qt.CheckState.Unchecked)
    if user_data is not None:
        item.setData(Qt.ItemDataRole.UserRole, user_data)
    return item


def checked_rows_data(table, col=0):
    """Ritorna la lista degli user_data (vedi make_checkbox_item) delle righe
    con la checkbox spuntata nella colonna indicata."""
    result = []
    for r in range(table.rowCount()):
        item = table.item(r, col)
        if item is not None and item.checkState() == Qt.CheckState.Checked:
            result.append(item.data(Qt.ItemDataRole.UserRole))
    return result


def uncheck_all(table, col=0):
    for r in range(table.rowCount()):
        item = table.item(r, col)
        if item is not None:
            item.setCheckState(Qt.CheckState.Unchecked)


def confirm_action(parent, title, message):
    reply = QMessageBox.warning(
        parent, title, message,
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.No,
    )
    return reply == QMessageBox.StandardButton.Yes


def build_file_action_row(include_remove_catalog=True, remove_label="Rimuovi dal catalogo"):
    """Crea la riga di pulsanti per selezionare ed elaborare più righe di una
    tabella in una volta sola: rimuovi dal catalogo (solo DB, i file restano),
    elimina dal disco, rinomina, sposta, copia. Ritorna (layout, dict di
    QPushButton per chiave), tutti disabilitati finché non c'è una selezione."""
    layout = QHBoxLayout()
    buttons = {}
    specs = []
    if include_remove_catalog:
        specs.append(("remove_catalog", remove_label))
    specs += [
        ("delete_disk", "Elimina dal disco…"),
        ("rename", "Rinomina…"),
        ("move", "Sposta…"),
        ("copy", "Copia…"),
    ]
    layout.addWidget(QLabel(tr("Selezionati:")))
    for key, label in specs:
        btn = QPushButton(tr(label))
        btn.setEnabled(False)
        layout.addWidget(btn)
        buttons[key] = btn
    layout.addStretch(1)
    return layout, buttons


class FlowLayout(QLayout):
    """Layout che dispone i widget (qui: i pulsanti del pannello dettaglio) uno
    dopo l'altro e li manda a capo automaticamente quando lo spazio orizzontale
    disponibile non basta più, invece di farli uscire dalla finestra o farli
    sovrapporre ad altri elementi. Così l'interfaccia resta utilizzabile a
    qualunque risoluzione/larghezza di schermo, senza bottoni tagliati o fuori
    vista (adattamento richiesto da un utente con schermo Full HD 1920x1080).
    Adattato dal classico esempio "Flow Layout" della documentazione Qt."""

    def __init__(self, parent=None, margin=0, h_spacing=6, v_spacing=6):
        super().__init__(parent)
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self._items = []
        self.setContentsMargins(margin, margin, margin, margin)

    def __del__(self):
        while self.count():
            self.takeAt(0)

    def addItem(self, item):
        self._items.append(item)

    def horizontalSpacing(self):
        return self._h_spacing

    def verticalSpacing(self):
        return self._v_spacing

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        left, top, right, bottom = self.getContentsMargins()
        effective_rect = rect.adjusted(left, top, -right, -bottom)
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0

        for item in self._items:
            widget = item.widget()
            space_x = self._h_spacing
            space_y = self._v_spacing
            next_x = x + item.sizeHint().width() + space_x
            if next_x - space_x > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + space_y
                next_x = x + item.sizeHint().width() + space_x
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = next_x
            line_height = max(line_height, item.sizeHint().height())

        return y + line_height - rect.y() + bottom


class ProportionalSplitter(QSplitter):
    """QSplitter che, quando è la FINESTRA (o il pannello che lo contiene) a
    cambiare dimensione - non quando l'utente trascina a mano una barra
    divisoria - mantiene le stesse proporzioni tra i pannelli invece di dare
    tutto lo spazio in più (o in meno) a un solo pannello. Qt di norma, in
    questo caso, tende a far crescere soprattutto il pannello con il
    contenuto più "elastico" (es. l'area informazioni), lasciando per esempio
    la foto piccola anche se la finestra diventa molto più grande: così
    invece ogni sezione si adatta nella stessa proporzione, e si può comunque
    sempre regolarla a mano trascinando la barra (segnalato da Nuccio dopo
    aver notato che allargando la finestra lo spazio extra andava quasi tutto
    al pannello informazioni)."""

    def resizeEvent(self, event):
        old_size = event.oldSize()
        new_size = event.size()
        if old_size.width() >= 0 and old_size.height() >= 0:
            if self.orientation() == Qt.Orientation.Vertical:
                old_total, new_total = old_size.height(), new_size.height()
            else:
                old_total, new_total = old_size.width(), new_size.width()

            sizes = self.sizes()
            current_total = sum(sizes)
            if old_total > 0 and new_total > 0 and current_total > 0 and new_total != old_total:
                new_sizes = [max(1, round(s * new_total / current_total)) for s in sizes]
                # Corregge l'arrotondamento sull'ultimo pannello, per non
                # sforare/mancare il totale di qualche pixel.
                new_sizes[-1] = max(1, new_sizes[-1] + (new_total - sum(new_sizes)))
                self.setSizes(new_sizes)

        super().resizeEvent(event)


class ScaledPixmapLabel(QLabel):
    """QLabel per le anteprime foto che si ri-scala da sola ogni volta che la
    sua area disponibile cambia (trascinando la barra di uno splitter, o
    ridimensionando la finestra), non solo quando viene caricata una nuova
    immagine. Senza questo, l'immagine restava "congelata" alla dimensione di
    quando era stata mostrata l'ultima volta: se poi il riquadro della foto
    si restringeva (es. allargando il riquadro informazioni sotto), l'ultima
    immagine mostrata appariva tagliata invece di rimpicciolirsi per
    adattarsi (segnalato da Nuccio con screenshot). Si usa come una QLabel
    normale: setPixmap(pixmap) con l'immagine alla sua risoluzione originale
    (non già scalata a mano) fa il resto da sola."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._source_pixmap = None

    def setPixmap(self, pixmap):
        self._source_pixmap = pixmap if (pixmap is not None and not pixmap.isNull()) else None
        self._apply_scaled()

    def _apply_scaled(self):
        if self._source_pixmap is None:
            super().setPixmap(QPixmap())
            return
        w, h = max(1, self.width()), max(1, self.height())
        scaled = self._source_pixmap.scaled(
            w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        super().setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._source_pixmap is not None:
            self._apply_scaled()


class NumericItem(QTableWidgetItem):
    """QTableWidgetItem che ordina numericamente invece che alfabeticamente."""

    def __init__(self, value, display=None):
        super().__init__(display if display is not None else str(value))
        self.value = value if value is not None else float("-inf")

    def __lt__(self, other):
        if isinstance(other, NumericItem):
            return self.value < other.value
        return super().__lt__(other)


class ScanWorker(QThread):
    progress = pyqtSignal(int, int, str)
    log_line = pyqtSignal(str)
    finished_ok = pyqtSignal(object)

    def __init__(self, db_path, thumb_dir, root_path, dry_run, remove_orphans):
        super().__init__()
        self.db_path = db_path
        self.thumb_dir = thumb_dir
        self.root_path = root_path
        self.dry_run = dry_run
        self.remove_orphans = remove_orphans
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        # Rete di sicurezza: vedi la stessa nota in AstrometryWorker.run().
        try:
            db = CatalogDB(self.db_path)
            stats = scan_root(
                self.root_path,
                db,
                self.thumb_dir,
                dry_run=self.dry_run,
                remove_orphans=self.remove_orphans,
                progress_cb=lambda c, t, m: self.progress.emit(c, t, m),
                log_cb=lambda m: self.log_line.emit(m),
                should_stop=lambda: self._stop,
            )
            db.close()
        except Exception as exc:
            logger.exception("Errore imprevisto nel thread di scansione")
            stats = ScanStats()
            stats.errors += 1
            self.log_line.emit(tr("ERRORE imprevisto durante la scansione: {exc}").format(exc=exc))
        self.finished_ok.emit(stats)


class QualityWorker(QThread):
    """Analizza in background (astropy/photutils) i raw FITS di una sessione:
    stelle rilevate, FWHM medio, sfondo. Non tocca il database (lo fa il
    chiamante alla fine, sul thread GUI) per restare semplice e sicuro."""
    progress = pyqtSignal(int, int, str)
    finished_ok = pyqtSignal(dict)

    def __init__(self, file_paths):
        super().__init__()
        self.file_paths = file_paths
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        # Rete di sicurezza: vedi la stessa nota in AstrometryWorker.run().
        from astro_extra import analyze_raw_quality
        results = {}
        try:
            total = len(self.file_paths)
            for i, path in enumerate(self.file_paths, 1):
                if self._stop:
                    break
                info, _err = analyze_raw_quality(path)
                if info:
                    results[path] = info
                self.progress.emit(i, total, os.path.basename(path))
        except Exception:
            logger.exception("Errore imprevisto nel thread di analisi qualità raw")
        self.finished_ok.emit(results)


class ObjectLookupWorker(QThread):
    """Identifica l'oggetto su SIMBAD e calcola le condizioni osservative al
    momento della ripresa, in background (richiede una connessione Internet
    per l'interrogazione SIMBAD)."""
    finished_ok = pyqtSignal(object, object)  # (info_dict_o_None, errore_o_None)

    def __init__(self, target_name, session_datetime, lat, lon, elevation):
        super().__init__()
        self.target_name = target_name
        self.session_datetime = session_datetime
        self.lat = lat
        self.lon = lon
        self.elevation = elevation

    def run(self):
        # Rete di sicurezza: vedi la stessa nota in AstrometryWorker.run().
        try:
            from astro_extra import resolve_object, compute_observation_conditions
            info, err = resolve_object(self.target_name)
            if err:
                self.finished_ok.emit(None, err)
                return
            cond, _cond_err = compute_observation_conditions(
                info.get("ra_deg"), info.get("dec_deg"), self.session_datetime,
                self.lat, self.lon, self.elevation,
            )
            if cond:
                info.update(cond)
            self.finished_ok.emit(info, None)
        except Exception as exc:
            logger.exception("Errore imprevisto nel thread di identificazione oggetto")
            self.finished_ok.emit(
                None, tr("Errore imprevisto durante l'identificazione: {exc}").format(exc=exc))


class AstrometryWorker(QThread):
    """Risolve astrometricamente l'immagine stacked ed etichetta gli
    oggetti presenti nel campo inquadrato, con una delle due metodologie
    scelte dall'utente (parametro 'method'):

    - 'simbad': risoluzione con Siril (headless, catalogo Gaia locale,
      offline) e ricerca degli oggetti via SIMBAD - oggetti notevoli
      (galassie/nebulose/ammassi) e, se richiesto, le stelle più luminose
      del campo che hanno un nome leggibile (non più tramite l'archivio
      Gaia: quest'ultimo etichettava le stelle solo con un ID numerico
      Gaia DR3, senza alcun significato per chi guarda la foto). Le
      etichette vengono disegnate da questo programma.
    - 'astrometry_net': risoluzione ED etichettatura con Astrometry.net
      installato in locale dentro WSL (comando solve-field) - è
      Astrometry.net stesso a produrre l'immagine annotata, non viene
      interrogato SIMBAD.

    Il tutto in background, poiché ogni passaggio può richiedere da
    qualche secondo a un paio di minuti."""
    finished_ok = pyqtSignal(object, object)  # (risultato_dict_o_None, errore_o_None)
    progress = pyqtSignal(str)

    def __init__(self, solve_source_path, display_source_path, display_use_fits, siril_cli_path,
                 include_field_stars, target_name=None, ra_hint=None, dec_hint=None,
                 method="simbad"):
        super().__init__()
        self.solve_source_path = solve_source_path
        self.display_source_path = display_source_path
        self.display_use_fits = display_use_fits
        self.siril_cli_path = siril_cli_path
        self.include_field_stars = include_field_stars
        self.target_name = target_name
        self.ra_hint = ra_hint
        self.dec_hint = dec_hint
        self.method = method

    def run(self):
        # Rete di sicurezza: qualunque eccezione non prevista qui dentro (in
        # un thread separato) non deve mai far terminare l'intero programma
        # in silenzio - viene loggata su file (utile per capire cosa è
        # successo su un eseguibile compilato, dove non c'è una console) e
        # mostrata come normale messaggio di errore invece che come crash.
        try:
            self._run_impl()
        except Exception as exc:
            logger.exception("Errore imprevisto nel thread di astrometria")
            self.finished_ok.emit(
                None, tr("Errore imprevisto durante l'astrometria: {exc}").format(exc=exc))

    def _run_impl(self):
        ra_hint, dec_hint = self.ra_hint, self.dec_hint
        if (ra_hint is None or dec_hint is None) and self.target_name:
            # Nessuna posizione nota per il target: proviamo a risolverla al
            # volo (richiede Internet), così sia Siril che Astrometry.net
            # hanno comunque un punto di partenza anche su un file senza
            # header di puntamento (es. un jpg semplice). Se fallisce, si
            # prosegue senza: Siril funzionerà comunque se il file ha già
            # una posizione nell'header, e Astrometry.net risolve "alla
            # cieca" anche senza alcun suggerimento (solo più lentamente).
            self.progress.emit(tr("Astrometria: ricerca posizione approssimativa del target…"))
            try:
                from astro_extra import resolve_object
                info, _err = resolve_object(self.target_name)
                if info:
                    ra_hint = info.get("ra_deg")
                    dec_hint = info.get("dec_deg")
            except Exception:
                pass

        if self.method == "astrometry_net":
            self._run_astrometry_net(ra_hint, dec_hint)
        else:
            self._run_simbad(ra_hint, dec_hint)

    def _run_astrometry_net(self, ra_hint, dec_hint):
        from dwarf_astrometry import solve_and_annotate_astrometry_net

        self.progress.emit(tr(
            "Astrometria (Astrometry.net locale via WSL): risoluzione ed "
            "etichettatura dell'immagine in corso…"))
        result, err = solve_and_annotate_astrometry_net(
            self.display_source_path, ra_hint=ra_hint, dec_hint=dec_hint,
            progress_cb=self.progress.emit)
        if err:
            self.finished_ok.emit(None, err)
            return

        n_objects = result.get("n_field_objects", 0)
        self.finished_ok.emit({
            "annotated_path": result["annotated_path"],
            "n_notable": n_objects,
            "n_stars": 0,
            "n_labeled": n_objects,
            "warnings": [],
            "used_fits": self.display_use_fits,
            "method": "astrometry_net",
        }, None)

    def _run_simbad(self, ra_hint, dec_hint):
        import tempfile
        from dwarf_astrometry import (
            plate_solve_image, field_footprint, find_notable_objects,
            find_bright_named_stars, project_objects_to_pixels, annotate_image,
            render_fits_preview,
        )

        self.progress.emit(tr("Astrometria: risoluzione dell'immagine con Siril in corso…"))
        wcs, w, h, err = plate_solve_image(
            self.solve_source_path, self.siril_cli_path, ra_deg=ra_hint, dec_deg=dec_hint)
        if err:
            self.finished_ok.emit(None, err)
            return
        center, radius = field_footprint(wcs, w, h)

        annotate_temp_base = None
        if self.display_use_fits:
            # Il FITS non è disegnabile direttamente: generiamo un jpg a
            # piena risoluzione con lo stesso stretch dell'anteprima "Apri
            # sessione", e disegniamo le etichette su quello.
            self.progress.emit(tr("Astrometria: preparazione immagine dal FITS…"))
            fd, annotate_temp_base = tempfile.mkstemp(suffix="_base.jpg")
            os.close(fd)
            ok_base, base_err = render_fits_preview(self.display_source_path, annotate_temp_base)
            if not ok_base:
                try:
                    os.remove(annotate_temp_base)
                except OSError:
                    pass
                self.finished_ok.emit(None, base_err)
                return
            annotate_source = annotate_temp_base
        else:
            annotate_source = self.display_source_path

        self.progress.emit(tr("Astrometria: ricerca oggetti del campo su SIMBAD…"))
        notable, notable_err = find_notable_objects(
            center, radius, target_name=self.target_name,
            target_ra=ra_hint, target_dec=dec_hint)
        notable_failed = notable is None
        if notable_failed:
            notable = []

        stars = []
        star_err = None
        stars_failed = False
        if self.include_field_stars:
            self.progress.emit(tr("Astrometria: ricerca stelle luminose con nome su SIMBAD…"))
            stars, star_err = find_bright_named_stars(center, radius)
            stars_failed = stars is None
            if stars_failed:
                stars = []

        if notable_failed and (not self.include_field_stars or stars_failed):
            if annotate_temp_base:
                try:
                    os.remove(annotate_temp_base)
                except OSError:
                    pass
            self.finished_ok.emit(None, notable_err or star_err or
                                   tr("Impossibile ottenere gli oggetti del campo inquadrato."))
            return

        self.progress.emit(tr("Astrometria: disegno delle etichette…"))
        projected = project_objects_to_pixels(wcs, w, h, notable + stars)

        fd, temp_path = tempfile.mkstemp(suffix="_annotated.jpg")
        os.close(fd)
        ok, annotate_err = annotate_image(annotate_source, w, h, projected, temp_path)

        if annotate_temp_base:
            try:
                os.remove(annotate_temp_base)
            except OSError:
                pass

        if not ok:
            self.finished_ok.emit(None, annotate_err)
            return

        warnings = []
        if notable_failed:
            warnings.append(tr("Oggetti SIMBAD non disponibili: {err}").format(err=notable_err))
        if self.include_field_stars and stars_failed:
            warnings.append(tr("Stelle luminose non disponibili: {err}").format(err=star_err))

        self.finished_ok.emit({
            "annotated_path": temp_path,
            "n_notable": len(notable),
            "n_stars": len(stars),
            "n_labeled": len(projected),
            "warnings": warnings,
            "used_fits": self.display_use_fits,
            "method": "simbad",
        }, None)


(COL_SEL, COL_DATETIME, COL_TARGET, COL_TELESCOPE, COL_MODE, COL_FILTER, COL_EXP, COL_GAIN,
 COL_OK, COL_FAILED, COL_STACK) = range(11)

(CAL_SEL, CAL_TELESCOPE, CAL_SOURCE, CAL_TYPE, CAL_CAMERA, CAL_GAIN, CAL_BIN, CAL_EXP,
 CAL_TEMP, CAL_EXTRA, CAL_PATH) = range(11)

(SF_SEL, SF_NAME, SF_TYPE, SF_SIZE, SF_STARS, SF_FWHM, SF_NOISE) = range(7)


class SessionFilesDialog(QDialog):
    """Finestra 'Apri sessione': elenco dei file nella cartella sessione
    (esclusi eventuali sottocartelle Thumbnail e i file .txt/.json), con
    anteprima immagine e, per i file FITS (OK o falliti), anche l'header.

    Permette anche di: selezionare più file per eliminarli/rinominarli/
    spostarli/copiarli fisicamente (con conferma prima di ogni operazione),
    e di analizzarne la qualità (stelle rilevate, FWHM, rumore di fondo) per
    selezionare rapidamente gli scarti da escludere da un eventuale stacking.

    Con show_quality_tools=False (usato per i frame di calibrazione, dove
    l'analisi qualità stelle/FWHM non ha senso) i controlli e le colonne di
    qualità restano semplicemente nascosti: resta tutto il resto (anteprima,
    header FITS, operazioni sui file). settings_prefix tiene separate le
    impostazioni salvate (geometria, larghezza colonne...) da quelle della
    finestra 'Apri sessione' normale, dato che il contenuto è diverso."""

    def __init__(self, session_path, session_label, db, thumb_dir, parent=None, on_change=None,
                 show_quality_tools=True, settings_prefix="sessionfiles", window_title=None):
        super().__init__(parent)
        self.session_path = session_path
        self.db = db
        self.thumb_dir = thumb_dir
        self.on_change = on_change
        self.quality_worker = None
        self._current_preview_path = None
        self._show_quality_tools = show_quality_tools
        self._settings_prefix = settings_prefix
        self.settings = make_settings()
        self.setWindowTitle(window_title or tr("Sessione: {label}").format(label=session_label))
        self.resize(1500, 900)

        layout = QVBoxLayout(self)

        self.splitter = ProportionalSplitter(Qt.Orientation.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.files_table = QTableWidget(0, 7)
        self.files_table.setHorizontalHeaderLabels(
            [tr(h) for h in ["", "Nome file", "Tipo", "Dimensione", "Stelle", "FWHM(px)", "Rumore fondo"]]
        )
        self.files_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.files_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.files_table.setSortingEnabled(True)
        self.files_table.itemSelectionChanged.connect(self._on_file_selected)
        self.files_table.itemChanged.connect(self._on_item_changed)
        if not self._show_quality_tools:
            # Niente analisi qualità sui frame di calibrazione (bias/dark/
            # flat): "stelle rilevate"/FWHM non hanno senso su un frame senza
            # stelle, quindi le colonne restano nascoste (richiesto da Nuccio).
            for col in (SF_STARS, SF_FWHM, SF_NOISE):
                self.files_table.setColumnHidden(col, True)
        left_layout.addWidget(self.files_table, 1)

        action_layout, self.file_action_buttons = build_file_action_row(include_remove_catalog=False)
        self.file_action_buttons["delete_disk"].clicked.connect(self.action_delete_disk)
        self.file_action_buttons["rename"].clicked.connect(self.action_rename)
        self.file_action_buttons["move"].clicked.connect(self.action_move)
        self.file_action_buttons["copy"].clicked.connect(self.action_copy)
        left_layout.addLayout(action_layout)

        if self._show_quality_tools:
            # Avvertenza sul significato dei valori di qualità: sono utili per
            # confrontare i file TRA LORO all'interno della stessa sessione
            # (per scartare i peggiori), ma il valore assoluto e la classifica
            # dei singoli file possono differire leggermente da quelli di
            # altri programmi (DeepSkyStacker, Siril, ecc.), che usano
            # algoritmi di misura diversi (richiesto da Nuccio dopo i
            # confronti con Fusion Lab/DSS/Siril).
            quality_caveat_text = (
                "I valori di stelle/FWHM sono calcolati con un algoritmo proprio dell'app: "
                "utili per confrontare i file tra loro nella stessa sessione e scartare i peggiori, "
                "ma il valore assoluto e l'ordine dei singoli file possono differire leggermente da "
                "quelli di altri programmi (DeepSkyStacker, Siril, ecc.), che misurano con algoritmi diversi."
            )

            quality_layout = QHBoxLayout()
            self.analyze_btn = QPushButton(tr("Analizza qualità raw"))
            self.analyze_btn.setToolTip(tr(quality_caveat_text))
            self.analyze_btn.clicked.connect(self.analyze_quality)
            quality_layout.addWidget(self.analyze_btn)
            self.quality_progress = QProgressBar()
            self.quality_progress.setMaximumWidth(140)
            quality_layout.addWidget(self.quality_progress)
            quality_layout.addWidget(QLabel(tr("Scarta se stelle <")))
            self.min_stars_edit = QLineEdit("3")
            self.min_stars_edit.setFixedWidth(36)
            quality_layout.addWidget(self.min_stars_edit)
            quality_layout.addWidget(QLabel(tr("o FWHM >")))
            self.max_fwhm_edit = QLineEdit("6.0")
            self.max_fwhm_edit.setFixedWidth(44)
            quality_layout.addWidget(self.max_fwhm_edit)
            quality_layout.addWidget(QLabel(tr("o rumore >")))
            self.max_noise_edit = QLineEdit("50")
            self.max_noise_edit.setFixedWidth(44)
            quality_layout.addWidget(self.max_noise_edit)
            select_bad_btn = QPushButton(tr("Seleziona scarti"))
            select_bad_btn.clicked.connect(self.select_low_quality)
            quality_layout.addWidget(select_bad_btn)
            deselect_btn = QPushButton(tr("Deseleziona tutto"))
            deselect_btn.clicked.connect(self.deselect_all_files)
            quality_layout.addWidget(deselect_btn)
            quality_layout.addStretch(1)
            left_layout.addLayout(quality_layout)

            quality_caveat_label = QLabel("ℹ️ " + tr(quality_caveat_text))
            quality_caveat_label.setWordWrap(True)
            quality_caveat_label.setStyleSheet("color: gray; font-style: italic; font-size: 9pt;")
            left_layout.addWidget(quality_caveat_label)

        self.splitter.addWidget(left_widget)

        # Foto e header FITS in uno splitter verticale dedicato (stesso
        # principio del pannello dettaglio della finestra principale): così
        # si può ridimensionare liberamente lo spazio tra le due parti invece
        # di avere un'altezza fissa per la foto (qui c'è un solo pulsante,
        # "Ingrandisci…", che resta semplicemente ancorato sotto la foto).
        self.preview_splitter = ProportionalSplitter(Qt.Orientation.Vertical)

        photo_widget = QWidget()
        photo_layout = QVBoxLayout(photo_widget)
        photo_layout.setContentsMargins(0, 0, 0, 0)
        self.preview_label = ScaledPixmapLabel(tr("Seleziona un file per l'anteprima"))
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(120)
        self.preview_label.setFrameShape(QFrame.Shape.StyledPanel)
        photo_layout.addWidget(self.preview_label, 1)

        zoom_row = QHBoxLayout()
        self.zoom_btn = QPushButton(tr("Ingrandisci…"))
        self.zoom_btn.setEnabled(False)
        self.zoom_btn.setToolTip(tr(
            "Apre il file selezionato in una finestra grande, con zoom, per vederne i particolari."))
        self.zoom_btn.clicked.connect(self.open_zoom_dialog)
        zoom_row.addWidget(self.zoom_btn)
        zoom_row.addStretch(1)
        photo_layout.addLayout(zoom_row)
        self.preview_splitter.addWidget(photo_widget)

        header_widget = QWidget()
        header_layout = QVBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(QLabel(f"<b>{tr('Header FITS:')}</b>"))
        self.header_view = QPlainTextEdit()
        self.header_view.setReadOnly(True)
        self.header_view.setPlaceholderText(tr("(nessun header — seleziona un file FITS)"))
        self.header_view.setMinimumHeight(80)
        header_layout.addWidget(self.header_view, 1)
        self.preview_splitter.addWidget(header_widget)

        self.preview_splitter.setStretchFactor(0, 2)
        self.preview_splitter.setStretchFactor(1, 1)

        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)
        preview_layout.addWidget(self.preview_splitter)

        self.splitter.addWidget(preview_widget)
        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 3)
        layout.addWidget(self.splitter, 1)

        btn_row = QHBoxLayout()
        self.count_label = QLabel("")
        btn_row.addWidget(self.count_label)
        btn_row.addStretch(1)
        close_btn = QPushButton(tr("Chiudi"))
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._load_files()
        self._restore_state()
        if not self._preview_splitter_restored:
            QTimer.singleShot(0, self._set_default_preview_splitter_sizes)

    def _restore_state(self):
        geometry = self.settings.value(f"{self._settings_prefix}/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        header_state = self.settings.value(f"{self._settings_prefix}/header")
        if header_state is not None:
            self.files_table.horizontalHeader().restoreState(header_state)
            if not self._show_quality_tools:
                # Per sicurezza, indipendentemente da cosa c'era salvato:
                # queste colonne non vanno mai mostrate in modalità
                # calibrazione (vedi __init__).
                for col in (SF_STARS, SF_FWHM, SF_NOISE):
                    self.files_table.setColumnHidden(col, True)
        else:
            self.files_table.resizeColumnsToContents()
        splitter_state = self.settings.value(f"{self._settings_prefix}/splitter")
        if splitter_state is not None:
            self.splitter.restoreState(splitter_state)

        preview_splitter_state = self.settings.value(f"{self._settings_prefix}/preview_splitter")
        if preview_splitter_state is not None:
            self.preview_splitter.restoreState(preview_splitter_state)
            self._preview_splitter_restored = True
        else:
            self._preview_splitter_restored = False

    def _set_default_preview_splitter_sizes(self):
        """Proporzioni di default (foto ~60%, header FITS ~40%) al primo
        avvio, quando non c'è ancora uno stato salvato: resta comunque
        ridimensionabile trascinando la barra divisoria."""
        total = self.preview_splitter.height()
        if total > 0:
            photo_h = max(120, int(total * 0.6))
            self.preview_splitter.setSizes([photo_h, max(80, total - photo_h)])

    def closeEvent(self, event):
        self.settings.setValue(f"{self._settings_prefix}/geometry", self.saveGeometry())
        self.settings.setValue(f"{self._settings_prefix}/header", self.files_table.horizontalHeader().saveState())
        self.settings.setValue(f"{self._settings_prefix}/splitter", self.splitter.saveState())
        self.settings.setValue(f"{self._settings_prefix}/preview_splitter", self.preview_splitter.saveState())
        super().closeEvent(event)

    def _load_files(self):
        self.files_table.setSortingEnabled(False)
        self.files_table.blockSignals(True)
        self.files_table.setRowCount(0)
        try:
            paths = list_session_files(self.session_path)
        except OSError as exc:
            QMessageBox.warning(self, tr("Errore"), tr("Impossibile leggere la cartella:\n{exc}").format(exc=exc))
            paths = []

        for path in paths:
            r = self.files_table.rowCount()
            self.files_table.insertRow(r)
            self.files_table.setItem(r, SF_SEL, make_checkbox_item(path))

            name_item = QTableWidgetItem(os.path.basename(path))
            name_item.setData(Qt.ItemDataRole.UserRole, path)
            self.files_table.setItem(r, SF_NAME, name_item)

            kind = classify_file_kind(path)
            if kind == "fits":
                type_label = tr("FITS fallito") if os.path.basename(path).lower().startswith("failed_") else "FITS"
            elif kind == "image":
                type_label = tr("Immagine")
            else:
                type_label = tr("Altro")
            self.files_table.setItem(r, SF_TYPE, QTableWidgetItem(type_label))

            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            self.files_table.setItem(r, SF_SIZE, NumericItem(size, human_size(size)))
            self.files_table.setItem(r, SF_STARS, QTableWidgetItem("—"))
            self.files_table.setItem(r, SF_FWHM, QTableWidgetItem("—"))
            self.files_table.setItem(r, SF_NOISE, QTableWidgetItem("—"))

        self.files_table.blockSignals(False)
        self.files_table.setSortingEnabled(True)
        self.count_label.setText(tr("{n} file").format(n=len(paths)))
        self._update_file_action_buttons()
        self._populate_quality_columns()

    def _on_file_selected(self):
        items = self.files_table.selectedItems()
        if not items:
            return
        path = self.files_table.item(items[0].row(), SF_NAME).data(Qt.ItemDataRole.UserRole)
        self._current_preview_path = path
        if not path or not os.path.isfile(path):
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(tr("File non più presente sul disco"))
            self.header_view.setPlainText("")
            self.zoom_btn.setEnabled(False)
            return

        kind = classify_file_kind(path)
        self.zoom_btn.setEnabled(kind in ("fits", "image"))
        if kind == "fits":
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(tr("Lettura del file FITS in corso…"))
            QApplication.processEvents()
            pixmap, header_text, error = load_fits_preview(path)
            if pixmap is not None:
                self._show_pixmap(pixmap)
            else:
                self.preview_label.setPixmap(QPixmap())
                self.preview_label.setText(error or tr("Impossibile visualizzare l'immagine FITS"))
            self.header_view.setPlainText(header_text or tr("(header non disponibile)"))
        elif kind == "image":
            self.header_view.setPlainText("")
            pixmap = load_image_pixmap(path)
            if pixmap is not None:
                self._show_pixmap(pixmap)
            else:
                self.preview_label.setPixmap(QPixmap())
                self.preview_label.setText(tr("Impossibile aprire l'immagine"))
        else:
            self.header_view.setPlainText("")
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(tr("Nessuna anteprima disponibile per questo tipo di file"))

    def _show_pixmap(self, pixmap):
        # self.preview_label è una ScaledPixmapLabel: le basta l'immagine alla
        # sua risoluzione originale, si scala (e ri-scala da sola a ogni
        # ridimensionamento del riquadro) per conto suo.
        self.preview_label.setPixmap(pixmap)
        self.preview_label.setText("")

    def open_zoom_dialog(self):
        path = self._current_preview_path
        if not path or not os.path.isfile(path):
            return
        dlg = ImageZoomDialog(path, self)
        dlg.exec()

    # ------------------------------------------------------------------
    # Selezione ed elaborazione file (elimina/rinomina/sposta/copia)
    # ------------------------------------------------------------------
    def _on_item_changed(self, item):
        if item.column() == SF_SEL:
            self._update_file_action_buttons()

    def _update_file_action_buttons(self):
        n = len(self._checked_file_paths())
        self.file_action_buttons["delete_disk"].setEnabled(n >= 1)
        self.file_action_buttons["rename"].setEnabled(n == 1)
        self.file_action_buttons["move"].setEnabled(n >= 1)
        self.file_action_buttons["copy"].setEnabled(n >= 1)

    def _checked_file_paths(self):
        return [p for p in checked_rows_data(self.files_table, SF_SEL) if p]

    def _all_file_paths(self):
        paths = []
        for r in range(self.files_table.rowCount()):
            item = self.files_table.item(r, SF_SEL)
            if item is not None:
                paths.append(item.data(Qt.ItemDataRole.UserRole))
        return paths

    def deselect_all_files(self):
        uncheck_all(self.files_table, SF_SEL)
        self._update_file_action_buttons()

    def action_delete_disk(self):
        paths = self._checked_file_paths()
        if not paths:
            return
        names = "\n".join(f"- {os.path.basename(p)}" for p in paths[:20])
        more = "" if len(paths) <= 20 else tr("\n… e altri {n}").format(n=len(paths) - 20)
        if not confirm_action(self, tr("Elimina dal disco"),
                               tr("ATTENZIONE: eliminare DEFINITIVAMENTE {n} file dal disco?\n"
                                  "Questa operazione non è reversibile.\n\n{names}{more}").format(
                                   n=len(paths), names=names, more=more)):
            return
        errors = []
        for p in paths:
            try:
                file_ops.delete_path(p)
                self.db.delete_raw_quality_by_path(p)
            except Exception as exc:
                errors.append(f"{os.path.basename(p)}: {exc}")
        self.db.commit()
        if errors:
            QMessageBox.warning(self, tr("Alcuni errori"), tr("Errori durante l'eliminazione:\n") + "\n".join(errors))
        self._after_file_change()

    def action_rename(self):
        paths = self._checked_file_paths()
        if len(paths) != 1:
            return
        old_path = paths[0]
        old_name = os.path.basename(old_path)
        new_name, ok = QInputDialog.getText(self, tr("Rinomina file"), tr("Nuovo nome file:"), text=old_name)
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        if not confirm_action(self, tr("Rinomina file"),
                               tr("Rinominare '{old}' in '{new}'?").format(old=old_name, new=new_name.strip())):
            return
        try:
            new_path = file_ops.rename_path(old_path, new_name.strip())
            self.db.update_raw_quality_path(old_path, new_path)
            self.db.commit()
        except Exception as exc:
            QMessageBox.warning(self, tr("Errore"), tr("Rinomina non riuscita:\n{exc}").format(exc=exc))
            return
        self._after_file_change()

    def action_move(self):
        paths = self._checked_file_paths()
        if not paths:
            return
        dest = QFileDialog.getExistingDirectory(self, tr("Cartella di destinazione"))
        if not dest:
            return
        if not confirm_action(self, tr("Sposta file"), tr("Spostare {n} file in:\n{dest}?").format(n=len(paths), dest=dest)):
            return
        errors = []
        moved = 0
        for p in paths:
            try:
                new_path = file_ops.move_path(p, dest)
                self.db.update_raw_quality_path(p, new_path)
                moved += 1
            except Exception as exc:
                errors.append(f"{os.path.basename(p)}: {exc}")
        self.db.commit()
        if errors:
            QMessageBox.warning(self, tr("Alcuni errori"), tr("Errori durante lo spostamento:\n") + "\n".join(errors))
        self._after_file_change()
        self.count_label.setText(tr("Spostati {n} file in {dest}").format(n=moved, dest=dest))

    def action_copy(self):
        paths = self._checked_file_paths()
        if not paths:
            return
        dest = QFileDialog.getExistingDirectory(self, tr("Cartella di destinazione"))
        if not dest:
            return
        if not confirm_action(self, tr("Copia file"), tr("Copiare {n} file in:\n{dest}?").format(n=len(paths), dest=dest)):
            return
        errors = []
        copied = 0
        for p in paths:
            try:
                file_ops.copy_path(p, dest)
                copied += 1
            except Exception as exc:
                errors.append(f"{os.path.basename(p)}: {exc}")
        if errors:
            QMessageBox.warning(self, tr("Alcuni errori"), tr("Errori durante la copia:\n") + "\n".join(errors))
        self.count_label.setText(tr("Copiati {n} file in {dest}").format(n=copied, dest=dest))

    def _after_file_change(self):
        """Dopo elimina/rinomina/sposta: ricalcola il record della sessione
        (conteggi raw OK/falliti, stack, dimensione) senza dover rilanciare
        un'intera scansione, poi ricarica l'elenco file e avvisa la finestra
        principale (se presente) di aggiornare la propria tabella."""
        refresh_session_record(self.session_path, self.db, self.thumb_dir)
        self._load_files()
        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText(tr("Seleziona un file per l'anteprima"))
        self.header_view.setPlainText("")
        self._current_preview_path = None
        self.zoom_btn.setEnabled(False)
        if self.on_change:
            self.on_change()

    # ------------------------------------------------------------------
    # Controllo qualità raw (stelle rilevate, FWHM, sfondo)
    # ------------------------------------------------------------------
    def _populate_quality_columns(self):
        paths = self._all_file_paths()
        quality = self.db.get_raw_quality_for_paths(paths)
        self.files_table.setSortingEnabled(False)
        for r in range(self.files_table.rowCount()):
            path = self.files_table.item(r, SF_SEL).data(Qt.ItemDataRole.UserRole)
            q = quality.get(path)
            if q:
                stars = q["star_count"]
                self.files_table.setItem(r, SF_STARS, NumericItem(
                    stars if stars is not None else -1, str(stars) if stars is not None else "?"))
                fwhm = q["fwhm_px"]
                self.files_table.setItem(r, SF_FWHM, NumericItem(
                    fwhm if fwhm is not None else float("-inf"), f"{fwhm:.2f}" if fwhm is not None else "?"))
                noise = q["background_noise"]
                self.files_table.setItem(r, SF_NOISE, NumericItem(
                    noise if noise is not None else float("-inf"), f"{noise:.1f}" if noise is not None else "?"))
        self.files_table.setSortingEnabled(True)

    def analyze_quality(self):
        fits_paths = [p for p in self._all_file_paths() if classify_file_kind(p) == "fits"]
        if not fits_paths:
            QMessageBox.information(self, tr("Analisi qualità"), tr("Nessun file FITS in questa sessione."))
            return
        self.analyze_btn.setEnabled(False)
        self.quality_progress.setMaximum(len(fits_paths))
        self.quality_progress.setValue(0)
        self.quality_worker = QualityWorker(fits_paths)
        self.quality_worker.progress.connect(self._on_quality_progress)
        self.quality_worker.finished_ok.connect(self._on_quality_finished)
        self.quality_worker.start()

    def _on_quality_progress(self, current, total, name):
        self.quality_progress.setValue(current)
        self.count_label.setText(tr("Analisi qualità: {current}/{total} — {name}").format(
            current=current, total=total, name=name))

    def _on_quality_finished(self, results):
        self.analyze_btn.setEnabled(True)
        session_row = self.db.get_session_by_path(self.session_path)
        session_id = session_row["id"] if session_row else None
        if session_id is not None:
            for path, info in results.items():
                self.db.upsert_raw_quality(
                    session_id, path, os.path.basename(path),
                    info.get("star_count"), info.get("fwhm_px"),
                    info.get("background_mean"), info.get("background_noise"),
                )
            self.db.commit()
        self._populate_quality_columns()
        self.count_label.setText(tr("{n_files} file — analisi qualità completata su {n_raw} raw").format(
            n_files=self.files_table.rowCount(), n_raw=len(results)))

    def select_low_quality(self):
        quality = self.db.get_raw_quality_for_paths(self._all_file_paths())
        if not quality:
            QMessageBox.information(self, tr("Seleziona scarti"),
                                     tr("Nessun dato di qualità disponibile: esegui prima "
                                        "'Analizza qualità raw'."))
            return

        def parse_or_none(edit):
            try:
                return float(edit.text().replace(",", "."))
            except ValueError:
                return None

        min_stars = parse_or_none(self.min_stars_edit)
        max_fwhm = parse_or_none(self.max_fwhm_edit)
        max_noise = parse_or_none(self.max_noise_edit)

        self.files_table.blockSignals(True)
        n_selected = 0
        for r in range(self.files_table.rowCount()):
            item = self.files_table.item(r, SF_SEL)
            q = quality.get(item.data(Qt.ItemDataRole.UserRole))
            bad = False
            if q:
                if min_stars is not None and q["star_count"] is not None and q["star_count"] < min_stars:
                    bad = True
                if max_fwhm is not None and q["fwhm_px"] is not None and q["fwhm_px"] > max_fwhm:
                    bad = True
                if max_noise is not None and q["background_noise"] is not None \
                        and q["background_noise"] > max_noise:
                    bad = True
            item.setCheckState(Qt.CheckState.Checked if bad else Qt.CheckState.Unchecked)
            n_selected += 1 if bad else 0
        self.files_table.blockSignals(False)
        self._update_file_action_buttons()
        self.count_label.setText(tr("{n} file selezionati come scarti").format(n=n_selected))


class _PannableImageLabel(QLabel):
    """QLabel che permette di trascinare l'immagine con il tasto sinistro del
    mouse quando è più grande dell'area visibile (zoom), spostando le barre
    di scorrimento dello QScrollArea che lo contiene — comodo per esplorare i
    particolari di una foto ingrandita senza dover usare le barre laterali."""

    def __init__(self, scroll_area, parent=None):
        super().__init__(parent)
        self._scroll_area = scroll_area
        self._dragging = False
        self._drag_start_pos = None
        self._scroll_start = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_pos = event.position().toPoint()
            self._scroll_start = (
                self._scroll_area.horizontalScrollBar().value(),
                self._scroll_area.verticalScrollBar().value(),
            )
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._drag_start_pos is not None:
            delta = event.position().toPoint() - self._drag_start_pos
            self._scroll_area.horizontalScrollBar().setValue(self._scroll_start[0] - delta.x())
            self._scroll_area.verticalScrollBar().setValue(self._scroll_start[1] - delta.y())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._drag_start_pos = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)


class ImageZoomDialog(QDialog):
    """Finestra "Ingrandisci": mostra una foto di sessione (fits/jpg/png/tif)
    ingrandita in un'area scorrevole con zoom, per esaminarne i particolari
    meglio che nella piccola anteprima della finestra 'Apri sessione'. Con lo
    zoom attivo, l'immagine si può trascinare con il mouse (vedi
    _PannableImageLabel)."""

    MIN_ZOOM = 0.1
    MAX_ZOOM = 8.0

    def __init__(self, file_path, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.settings = make_settings()
        self.setWindowTitle(tr("Ingrandisci: {name}").format(name=os.path.basename(file_path)))
        # Finestra grande di default (richiesto da Nuccio), proporzionata allo
        # schermo disponibile quando possibile, con una dimensione fissa di
        # ripiego se lo schermo non è rilevabile (es. in ambiente di test).
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            self.resize(int(avail.width() * 0.9), int(avail.height() * 0.9))
        else:
            self.resize(1400, 950)
        self._base_pixmap = None
        self._fit_to_window = True
        self._zoom = 1.0

        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self.fit_btn = QPushButton(tr("Adatta alla finestra"))
        self.fit_btn.clicked.connect(self.fit_to_window)
        toolbar.addWidget(self.fit_btn)
        self.actual_btn = QPushButton(tr("Dimensione reale (100%)"))
        self.actual_btn.clicked.connect(self.actual_size)
        toolbar.addWidget(self.actual_btn)
        zoom_out_btn = QPushButton("−")
        zoom_out_btn.setFixedWidth(32)
        zoom_out_btn.clicked.connect(lambda: self.change_zoom(1 / 1.25))
        toolbar.addWidget(zoom_out_btn)
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedWidth(32)
        zoom_in_btn.clicked.connect(lambda: self.change_zoom(1.25))
        toolbar.addWidget(zoom_in_btn)
        self.zoom_label = QLabel("100%")
        toolbar.addWidget(self.zoom_label)
        toolbar.addStretch(1)
        self.print_btn = QPushButton(tr("Stampa"))
        self.print_btn.clicked.connect(self.print_image)
        toolbar.addWidget(self.print_btn)
        close_btn = QPushButton(tr("Chiudi"))
        close_btn.clicked.connect(self.close)
        toolbar.addWidget(close_btn)
        layout.addLayout(toolbar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidgetResizable(False)
        self.image_label = _PannableImageLabel(self.scroll_area)
        self.image_label.setText(tr("Caricamento…"))
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.image_label)
        layout.addWidget(self.scroll_area, 1)

        self._restore_state()
        self._load_image()

    def _restore_state(self):
        geometry = self.settings.value("imagezoom/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        self.settings.setValue("imagezoom/geometry", self.saveGeometry())
        super().closeEvent(event)

    def _load_image(self):
        # max_size grande a sufficienza da coprire le risoluzioni tipiche dei
        # sensori Dwarf: PIL/astropy riducono solo se l'immagine è più grande,
        # quindi le foto più piccole restano alla loro dimensione reale.
        kind = classify_file_kind(self.file_path)
        if kind == "fits":
            pixmap, _, error = load_fits_preview(self.file_path, max_size=(8000, 8000))
        elif kind == "image":
            pixmap = load_image_pixmap(self.file_path, max_size=(8000, 8000))
            error = None if pixmap is not None else tr("Impossibile aprire l'immagine")
        else:
            pixmap = None
            error = tr("Nessuna anteprima disponibile per questo tipo di file")

        if pixmap is None:
            self.image_label.setText(error or tr("Impossibile visualizzare l'immagine"))
            return
        self._base_pixmap = pixmap
        self.fit_to_window()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._fit_to_window and self._base_pixmap is not None:
            self._apply_zoom(fit=True)

    def fit_to_window(self):
        self._fit_to_window = True
        self._apply_zoom(fit=True)

    def actual_size(self):
        self._fit_to_window = False
        self._zoom = 1.0
        self._apply_zoom(fit=False)

    def change_zoom(self, factor):
        self._fit_to_window = False
        self._zoom = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self._zoom * factor))
        self._apply_zoom(fit=False)

    def _apply_zoom(self, fit):
        if self._base_pixmap is None:
            return
        if fit:
            avail = self.scroll_area.viewport().size()
            scaled = self._base_pixmap.scaled(
                max(1, avail.width() - 4), max(1, avail.height() - 4),
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            if self._base_pixmap.width() > 0:
                self._zoom = scaled.width() / self._base_pixmap.width()
        else:
            w = max(1, int(self._base_pixmap.width() * self._zoom))
            h = max(1, int(self._base_pixmap.height() * self._zoom))
            scaled = self._base_pixmap.scaled(
                w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.image_label.setPixmap(scaled)
        self.image_label.resize(scaled.size())
        self.zoom_label.setText(f"{self._zoom * 100:.0f}%")

    def print_image(self):
        # Stampa sempre l'immagine caricata a piena risoluzione
        # (self._base_pixmap), non la versione ridotta/ingrandita mostrata a
        # schermo in questo momento: lo zoom serve solo per l'esame a video.
        if self._base_pixmap is None or self._base_pixmap.isNull():
            QMessageBox.information(self, tr("Stampa"), tr("Nessuna immagine da stampare."))
            return

        from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
        from PyQt6.QtGui import QPainter
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        painter = QPainter(printer)
        rect = painter.viewport()
        size = self._base_pixmap.size()
        size.scale(rect.size(), Qt.AspectRatioMode.KeepAspectRatio)
        painter.setViewport(rect.x(), rect.y(), size.width(), size.height())
        painter.setWindow(self._base_pixmap.rect())
        painter.drawPixmap(0, 0, self._base_pixmap)
        painter.end()


class CalibrationDialog(QDialog):
    """Finestra separata con l'elenco dei frame di calibrazione (Bias/Dark/Flat
    da cali_frame, e le sessioni dark manuali da DWARF_DARK)."""

    def __init__(self, db, thumb_dir, parent=None):
        super().__init__(parent)
        self.db = db
        self.thumb_dir = thumb_dir
        self.settings = make_settings()
        self.setWindowTitle(tr("Frame di calibrazione (Bias / Dark / Flat)"))
        self.resize(1400, 560)

        layout = QVBoxLayout(self)

        # "Tutti/Tutte" sono tradotti con tr() (vedi sotto e in reload()): il
        # confronto nel codice di filtro usa a sua volta tr("Tutti")/
        # tr("Tutte"), quindi resta coerente in entrambe le lingue. I valori
        # sorgente/tipo (cali_frame, dwarf_dark, Bias, Dark, Flat) restano
        # invece non tradotti: sono termini tecnici standard e valori
        # effettivamente salvati nel database.
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel(tr("Telescopio:")))
        self.telescope_combo = QComboBox()
        self.telescope_combo.addItem(tr("Tutti"))
        self.telescope_combo.addItems(db.distinct_calibration_telescopes())
        self.telescope_combo.currentIndexChanged.connect(self.reload)
        filter_row.addWidget(self.telescope_combo)

        filter_row.addWidget(QLabel(tr("Sorgente:")))
        self.source_combo = QComboBox()
        self.source_combo.addItem(tr("Tutte"))
        self.source_combo.addItems(["cali_frame", "dwarf_dark"])
        self.source_combo.currentIndexChanged.connect(self.reload)
        filter_row.addWidget(self.source_combo)

        filter_row.addWidget(QLabel(tr("Tipo:")))
        self.type_combo = QComboBox()
        self.type_combo.addItem(tr("Tutti"))
        self.type_combo.addItems(["Bias", "Dark", "Flat"])
        self.type_combo.currentIndexChanged.connect(self.reload)
        filter_row.addWidget(self.type_combo)
        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(
            [tr(h) for h in ["", "Telescopio", "Sorgente", "Tipo", "Camera", "Gain", "Binning",
                              "Esp(s)", "Temp(°C)", "IR / stack / n.raw", "Percorso"]]
        )
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self._update_open_btn_state)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table, 1)

        action_layout, self.action_buttons = build_file_action_row()
        self.action_buttons["remove_catalog"].clicked.connect(self.action_remove_catalog)
        self.action_buttons["delete_disk"].clicked.connect(self.action_delete_disk)
        self.action_buttons["rename"].clicked.connect(self.action_rename)
        self.action_buttons["move"].clicked.connect(self.action_move)
        self.action_buttons["copy"].clicked.connect(self.action_copy)
        layout.addLayout(action_layout)

        btn_row = QHBoxLayout()
        self.count_label = QLabel("")
        btn_row.addWidget(self.count_label)
        btn_row.addStretch(1)
        self.open_folder_btn = QPushButton(tr("Apri cartella sessione"))
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.clicked.connect(self.open_selected_folder)
        btn_row.addWidget(self.open_folder_btn)
        # Visualizzatore FITS/header per i singoli file del frame selezionato,
        # per coerenza con le altre finestre (riusa la stessa finestra "Apri
        # sessione": funziona anche per una cartella di calibrazione, non solo
        # per una sessione vera e propria, richiesto da Nuccio).
        self.view_files_btn = QPushButton(tr("Visualizza file…"))
        self.view_files_btn.setEnabled(False)
        self.view_files_btn.setToolTip(tr(
            "Apre i file del frame selezionato in una finestra con anteprima immagine/FITS "
            "e header, come per le sessioni normali."))
        self.view_files_btn.clicked.connect(self.view_selected_files)
        btn_row.addWidget(self.view_files_btn)
        close_btn = QPushButton(tr("Chiudi"))
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self.reload()
        self._restore_state()

    def _restore_state(self):
        geometry = self.settings.value("calibration/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        header_state = self.settings.value("calibration/header")
        if header_state is not None:
            self.table.horizontalHeader().restoreState(header_state)
        else:
            self.table.resizeColumnsToContents()

    def closeEvent(self, event):
        self.settings.setValue("calibration/geometry", self.saveGeometry())
        self.settings.setValue("calibration/header", self.table.horizontalHeader().saveState())
        super().closeEvent(event)

    def _update_open_btn_state(self):
        has_selection = bool(self.table.selectedItems())
        self.open_folder_btn.setEnabled(has_selection)
        self.view_files_btn.setEnabled(has_selection)

    def _selected_record_folder(self):
        """Ritorna la cartella del frame selezionato (per cali_frame il
        percorso salvato è il file FITS master: la cartella è quella che lo
        contiene; per dwarf_dark il percorso è già la cartella della sessione
        dark), o None se non c'è selezione."""
        items = self.table.selectedItems()
        if not items:
            return None
        record_path = self.table.item(items[0].row(), CAL_PATH).text()
        if not record_path:
            return None
        return record_path if os.path.isdir(record_path) else os.path.dirname(record_path)

    def open_selected_folder(self):
        folder = self._selected_record_folder()
        if folder and os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        else:
            QMessageBox.warning(self, tr("Cartella non trovata"),
                                 tr("La cartella non è più presente sul disco:\n{folder}").format(folder=folder))

    def view_selected_files(self):
        items = self.table.selectedItems()
        if not items:
            return
        folder = self._selected_record_folder()
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, tr("Cartella non trovata"),
                                 tr("La cartella non è più presente sul disco:\n{folder}").format(folder=folder))
            return
        row_idx = items[0].row()
        telescope = self.table.item(row_idx, CAL_TELESCOPE).text()
        ftype = self.table.item(row_idx, CAL_TYPE).text()
        camera = self.table.item(row_idx, CAL_CAMERA).text()
        label = f"{telescope} · {ftype} · {camera}"
        # Riusa la stessa finestra "Apri sessione" (lista file + anteprima
        # FITS/immagine + header): funziona perfettamente anche per una
        # cartella di calibrazione, non solo per una sessione vera e propria,
        # perché lavora solo sui file su disco (refresh_session_record fa
        # da sé nulla se la cartella non è una sessione nota). Con
        # show_quality_tools=False restano nascosti i controlli e le colonne
        # di analisi qualità (stelle/FWHM/rumore), che per un frame di
        # calibrazione non hanno senso; settings_prefix diverso per non
        # mescolare geometria/colonne salvate con quelle della finestra "Apri
        # sessione" normale (richiesto da Nuccio).
        dlg = SessionFilesDialog(
            folder, label, self.db, self.thumb_dir, self, on_change=self.reload,
            show_quality_tools=False, settings_prefix="calibrationfiles",
            window_title=tr("Frame di calibrazione: {label}").format(label=label))
        dlg.exec()

    def reload(self):
        telescope = self.telescope_combo.currentText()
        source = self.source_combo.currentText()
        ftype = self.type_combo.currentText()
        rows = self.db.all_calibration(
            telescope_filter=telescope if telescope != tr("Tutti") else None,
            source_filter=source if source != tr("Tutte") else None,
            frame_type_filter=ftype if ftype != tr("Tutti") else None,
        )

        self.table.setSortingEnabled(False)
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for row in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, CAL_SEL, make_checkbox_item(row["id"]))
            self.table.setItem(r, CAL_TELESCOPE, QTableWidgetItem(row["telescope"] or "?"))
            self.table.setItem(r, CAL_SOURCE, QTableWidgetItem(row["source"] or "?"))
            self.table.setItem(r, CAL_TYPE, QTableWidgetItem(row["frame_type"] or "?"))
            self.table.setItem(r, CAL_CAMERA, QTableWidgetItem(row["camera"] or "?"))
            self.table.setItem(r, CAL_GAIN, NumericItem(
                row["gain"], str(row["gain"]) if row["gain"] is not None else "?"))
            self.table.setItem(r, CAL_BIN, NumericItem(
                row["bin"], str(row["bin"]) if row["bin"] is not None else "?"))
            self.table.setItem(r, CAL_EXP, NumericItem(
                row["exposure"], str(row["exposure"]) if row["exposure"] is not None else "?"))
            temp_val = row["temperature"] if row["temperature"] is not None else float("-inf")
            temp_display = f"{row['temperature']:.1f}" if row["temperature"] is not None else "?"
            self.table.setItem(r, CAL_TEMP, NumericItem(temp_val, temp_display))
            extra_bits = []
            if row["ir"] is not None:
                extra_bits.append(f"IR {row['ir']}")
            if row["stack_count"] is not None:
                extra_bits.append(f"stack {row['stack_count']}")
            if row["raw_count"] is not None:
                extra_bits.append(f"{row['raw_count']} raw")
            self.table.setItem(r, CAL_EXTRA, QTableWidgetItem(", ".join(extra_bits) or "—"))
            self.table.setItem(r, CAL_PATH, QTableWidgetItem(row["record_path"]))
        self.table.blockSignals(False)
        self.table.setSortingEnabled(True)
        self.count_label.setText(tr("{n} elementi").format(n=len(rows)))
        self._update_action_buttons()

    # ------------------------------------------------------------------
    # Selezione ed elaborazione (elimina/rinomina/sposta/copia)
    # ------------------------------------------------------------------
    def _on_item_changed(self, item):
        if item.column() == CAL_SEL:
            self._update_action_buttons()

    def _update_action_buttons(self):
        n = len(checked_rows_data(self.table, CAL_SEL))
        self.action_buttons["remove_catalog"].setEnabled(n >= 1)
        self.action_buttons["delete_disk"].setEnabled(n >= 1)
        self.action_buttons["rename"].setEnabled(n == 1)
        self.action_buttons["move"].setEnabled(n >= 1)
        self.action_buttons["copy"].setEnabled(n >= 1)

    def _checked_rows(self):
        ids = checked_rows_data(self.table, CAL_SEL)
        rows = [self.db.conn.execute("SELECT * FROM calibration WHERE id = ?", (i,)).fetchone()
                for i in ids]
        return [r for r in rows if r]

    def action_remove_catalog(self):
        rows = self._checked_rows()
        if not rows:
            return
        names = "\n".join(f"- {os.path.basename(r['record_path'])}" for r in rows[:20])
        more = "" if len(rows) <= 20 else tr("\n… e altri {n}").format(n=len(rows) - 20)
        if not confirm_action(self, tr("Rimuovi dal catalogo"),
                               tr("Rimuovere {n} elemento/i dal catalogo?\n"
                                  "(i file sul disco NON vengono toccati)\n\n{names}{more}").format(
                                   n=len(rows), names=names, more=more)):
            return
        for r in rows:
            self.db.delete_calibration_by_id(r["id"])
        self.db.commit()
        self.reload()

    def action_delete_disk(self):
        rows = self._checked_rows()
        if not rows:
            return
        names = "\n".join(f"- {r['record_path']}" for r in rows[:20])
        more = "" if len(rows) <= 20 else tr("\n… e altri {n}").format(n=len(rows) - 20)
        if not confirm_action(self, tr("Elimina dal disco"),
                               tr("ATTENZIONE: eliminare DEFINITIVAMENTE {n} elemento/i dal disco "
                                  "(file o intere cartelle) e dal catalogo?\nQuesta operazione non è "
                                  "reversibile.\n\n{names}{more}").format(n=len(rows), names=names, more=more)):
            return
        errors = []
        for r in rows:
            try:
                file_ops.delete_path(r["record_path"])
                self.db.delete_calibration_by_id(r["id"])
            except Exception as exc:
                errors.append(f"{r['record_path']}: {exc}")
        self.db.commit()
        if errors:
            QMessageBox.warning(self, tr("Alcuni errori"), tr("Errori durante l'eliminazione:\n") + "\n".join(errors))
        self.reload()

    def action_rename(self):
        rows = self._checked_rows()
        if len(rows) != 1:
            return
        row = rows[0]
        old_path = row["record_path"]
        old_name = os.path.basename(old_path.rstrip(os.sep))
        new_name, ok = QInputDialog.getText(self, tr("Rinomina"), tr("Nuovo nome:"), text=old_name)
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        if not confirm_action(self, tr("Rinomina"),
                               tr("Rinominare '{old}' in '{new}'?").format(old=old_name, new=new_name.strip())):
            return
        try:
            new_path = file_ops.rename_path(old_path, new_name.strip())
            self.db.update_calibration_record_path(row["id"], new_path)
            self.db.commit()
        except Exception as exc:
            QMessageBox.warning(self, tr("Errore"), tr("Rinomina non riuscita:\n{exc}").format(exc=exc))
            return
        self.reload()

    def action_move(self):
        rows = self._checked_rows()
        if not rows:
            return
        dest = QFileDialog.getExistingDirectory(self, tr("Cartella di destinazione"))
        if not dest:
            return
        if not confirm_action(self, tr("Sposta"), tr("Spostare {n} elemento/i in:\n{dest}?").format(n=len(rows), dest=dest)):
            return
        errors = []
        for r in rows:
            try:
                new_path = file_ops.move_path(r["record_path"], dest)
                self.db.update_calibration_record_path(r["id"], new_path)
            except Exception as exc:
                errors.append(f"{r['record_path']}: {exc}")
        self.db.commit()
        if errors:
            QMessageBox.warning(self, tr("Alcuni errori"), tr("Errori durante lo spostamento:\n") + "\n".join(errors))
        self.reload()

    def action_copy(self):
        rows = self._checked_rows()
        if not rows:
            return
        dest = QFileDialog.getExistingDirectory(self, tr("Cartella di destinazione"))
        if not dest:
            return
        if not confirm_action(self, tr("Copia"), tr("Copiare {n} elemento/i in:\n{dest}?").format(n=len(rows), dest=dest)):
            return
        errors = []
        copied = 0
        for r in rows:
            try:
                file_ops.copy_path(r["record_path"], dest)
                copied += 1
            except Exception as exc:
                errors.append(f"{r['record_path']}: {exc}")
        if errors:
            QMessageBox.warning(self, tr("Alcuni errori"), tr("Errori durante la copia:\n") + "\n".join(errors))
        self.count_label.setText(tr("Copiati {n} elementi in {dest}").format(n=copied, dest=dest))


class ObserverLocationDialog(QDialog):
    """Piccola finestra per impostare la posizione dell'osservatore (usata
    per calcolare altezza, azimut e condizioni lunari al momento della
    ripresa). Salvata una volta sola in settings.ini, riusata per tutte le
    sessioni successive finché non viene cambiata da qui."""

    def __init__(self, lat, lon, elevation, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Posizione osservativa"))

        layout = QVBoxLayout(self)
        form = QGridLayout()
        form.addWidget(QLabel(tr("Latitudine (°, positiva a Nord):")), 0, 0)
        self.lat_edit = QLineEdit("" if lat is None else str(lat))
        form.addWidget(self.lat_edit, 0, 1)
        form.addWidget(QLabel(tr("Longitudine (°, positiva a Est):")), 1, 0)
        self.lon_edit = QLineEdit("" if lon is None else str(lon))
        form.addWidget(self.lon_edit, 1, 1)
        form.addWidget(QLabel(tr("Altitudine (m, opzionale):")), 2, 0)
        self.elev_edit = QLineEdit("0" if elevation is None else str(elevation))
        form.addWidget(self.elev_edit, 2, 1)
        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)
        cancel_btn = QPushButton(tr("Annulla"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def values(self):
        try:
            lat = float(self.lat_edit.text().strip().replace(",", "."))
            lon = float(self.lon_edit.text().strip().replace(",", "."))
            elev_text = self.elev_edit.text().strip()
            elev = float(elev_text.replace(",", ".")) if elev_text else 0.0
            if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
                return None
            return lat, lon, elev
        except ValueError:
            return None


class AstrometryOptionsDialog(QDialog):
    """Piccola finestra per scegliere, ogni volta: su quale immagine
    risolvere/etichettare (quando la sessione ha sia il jpg che il FITS-16
    dello stack), quale metodologia usare (SIMBAD via Siril, oppure
    Astrometry.net locale dentro WSL), e - solo per SIMBAD - se includere
    anche le stelle di campo oltre agli oggetti notevoli.

    Con la metodologia SIMBAD la risoluzione vera e propria viene sempre
    fatta sul FITS quando c'è (Siril richiede la dimensione pixel/focale
    che porta con sé, un jpg semplice no): la scelta FITS/jpg riguarda lì
    solo su quale immagine disegnare le etichette. Con Astrometry.net
    invece la scelta FITS/jpg determina anche il file da risolvere: risolve
    "alla cieca" dal contenuto dell'immagine, senza bisogno di quei
    metadati, ed è lui stesso a produrre l'immagine annotata."""

    def __init__(self, parent=None, offer_source_choice=False, fits_label="", jpg_label=""):
        super().__init__(parent)
        self.setWindowTitle(tr("Opzioni astrometria"))

        layout = QVBoxLayout(self)

        self.fits_radio = None
        self.jpg_radio = None
        if offer_source_choice:
            src_label = QLabel(tr(
                "Questa sessione ha sia il FITS-16 che il jpg dello stack. Su quale "
                "immagine risolvere ed etichettare?"))
            src_label.setWordWrap(True)
            layout.addWidget(src_label)
            self.fits_radio = QRadioButton(tr("FITS ({label}) — qualità migliore").format(label=fits_label))
            self.fits_radio.setChecked(True)
            layout.addWidget(self.fits_radio)
            self.jpg_radio = QRadioButton(tr("JPG ({label})").format(label=jpg_label))
            layout.addWidget(self.jpg_radio)
            # Gruppo esplicito: senza, tutti i QRadioButton figli di questo
            # dialogo (compresi quelli della metodologia sotto) finirebbero
            # nello stesso gruppo di mutua esclusione implicito di Qt
            # (per genitore), interferendo tra loro.
            self._source_group = QButtonGroup(self)
            self._source_group.addButton(self.fits_radio)
            self._source_group.addButton(self.jpg_radio)

        method_label = QLabel(f"<b>{tr('Metodologia:')}</b>")
        layout.addWidget(method_label)
        self.simbad_radio = QRadioButton(tr("SIMBAD (risoluzione con Siril, locale)"))
        self.simbad_radio.setChecked(True)
        self.simbad_radio.setToolTip(tr(
            "Risolve con Siril (catalogo Gaia locale, offline) e cerca su SIMBAD "
            "(richiede Internet) gli oggetti notevoli Messier/NGC/IC del campo, "
            "disegnando le etichette con questo programma."))
        layout.addWidget(self.simbad_radio)
        self.astrometry_net_radio = QRadioButton(tr("Astrometry.net (locale, dentro WSL)"))
        self.astrometry_net_radio.setToolTip(tr(
            "Risolve ed etichetta con Astrometry.net installato dentro WSL (comando "
            "solve-field): funziona offline (richiede gli indici stellari installati "
            "in WSL). È Astrometry.net stesso a produrre l'immagine annotata con i "
            "propri cataloghi - non viene interrogato SIMBAD."))
        layout.addWidget(self.astrometry_net_radio)
        self._method_group = QButtonGroup(self)
        self._method_group.addButton(self.simbad_radio)
        self._method_group.addButton(self.astrometry_net_radio)

        info = QLabel(tr(
            "Con SIMBAD, gli oggetti notevoli presenti nel campo (altre galassie, "
            "nebulose, ammassi...) vengono sempre cercati su SIMBAD."))
        info.setWordWrap(True)
        layout.addWidget(info)

        self.stars_check = QCheckBox(tr(
            "Includi anche le stelle luminose con un nome noto (es. Polaris, alf And...)"))
        self.stars_check.setToolTip(tr(
            "Cerca su SIMBAD le stelle del campo che hanno un nome proprio, una "
            "designazione di Bayer/Flamsteed o una sigla HD - non stelle qualunque "
            "identificate solo da un codice numerico. Si applica solo con la "
            "metodologia SIMBAD: Astrometry.net include già di suo, nella propria "
            "annotazione, le stelle con nome che riconosce."))
        layout.addWidget(self.stars_check)

        self.simbad_radio.toggled.connect(self._update_stars_check_enabled)
        self._update_stars_check_enabled()

        note = QLabel(tr("Entrambe le metodologie risolvono l'immagine offline (Siril / "
                          "Astrometry.net locale in WSL); la ricerca SIMBAD (oggetti e "
                          "stelle) richiede invece una connessione Internet."))
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_stars_check_enabled(self):
        self.stars_check.setEnabled(self.simbad_radio.isChecked())

    def use_fits(self):
        """Ritorna True se è stato scelto il FITS, False per il jpg, None
        se non era stata offerta alcuna scelta (un solo file disponibile)."""
        if self.fits_radio is None:
            return None
        return self.fits_radio.isChecked()

    def method(self):
        """Ritorna 'astrometry_net' o 'simbad' secondo la metodologia
        scelta."""
        return "astrometry_net" if self.astrometry_net_radio.isChecked() else "simbad"


class MainWindow(QMainWindow):
    def __init__(self, db_path, thumb_dir):
        super().__init__()
        app_instance = QApplication.instance()
        if app_instance is not None:
            app_instance.setStyleSheet(APP_STYLESHEET)

        self.settings = make_settings()
        # La lingua si applica una sola volta all'avvio (vedi i18n.py): un
        # cambio dal menu "Lingua" diventa effettivo al riavvio del programma.
        set_language(self.settings.value("language", "it", type=str))

        self.setWindowTitle(tr("Catalogo Sessioni Astronomiche DWARF"))
        # Dimensione iniziale proporzionale allo schermo disponibile (invece di
        # un valore fisso pensato per un solo monitor), così al primissimo
        # avvio - prima che ci sia una geometria salvata da ripristinare - la
        # finestra si apre già a una dimensione comoda su qualunque risoluzione,
        # Full HD compreso. Un minimo assoluto comunque utilizzabile anche su
        # schermi piccoli.
        self.setMinimumSize(900, 600)
        screen = self.screen() or QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            self.resize(max(900, int(avail.width() * 0.85)), max(600, int(avail.height() * 0.85)))
        else:
            self.resize(1250, 780)

        self.db_path = db_path
        self.thumb_dir = thumb_dir
        self.db = CatalogDB(db_path)
        self.worker = None

        self._build_ui()
        self._load_settings()
        self.reload_telescope_combo()
        self.reload_target_combo()
        self.reload_sessions_table()
        self.update_status_bar()

        if not self._sessions_header_restored:
            self.sessions_table.resizeColumnsToContents()
        if (not self._splitter_restored or not self._left_splitter_restored
                or not self._detail_splitter_restored):
            QTimer.singleShot(0, self._set_default_splitter_sizes)

    # ------------------------------------------------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)

        # --- Riga cartella radice + azioni ---
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel(tr("Cartella radice:")))
        self.root_edit = QLineEdit()
        top_row.addWidget(self.root_edit, 1)
        browse_btn = QPushButton(tr("Sfoglia…"))
        browse_btn.clicked.connect(self.browse_root)
        top_row.addWidget(browse_btn)

        self.dry_run_chk = QCheckBox(tr("Dry-run (simula)"))
        top_row.addWidget(self.dry_run_chk)
        self.remove_orphans_chk = QCheckBox(tr("Rimuovi sessioni eliminate"))
        self.remove_orphans_chk.setChecked(True)
        top_row.addWidget(self.remove_orphans_chk)

        self.scan_btn = QPushButton(tr("Scansiona ora"))
        self.scan_btn.clicked.connect(self.start_scan)
        top_row.addWidget(self.scan_btn)
        self.stop_btn = QPushButton(tr("Interrompi"))
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_scan)
        top_row.addWidget(self.stop_btn)

        self.calibration_btn = QPushButton(tr("Frame di calibrazione…"))
        self.calibration_btn.clicked.connect(self.open_calibration_dialog)
        top_row.addWidget(self.calibration_btn)
        main_layout.addLayout(top_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        main_layout.addWidget(self.progress_bar)

        # --- Filtri ---
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel(tr("Telescopio:")))
        self.telescope_combo = QComboBox()
        # "Tutti"/"Tutte" sono tradotti con tr() sia qui che ovunque vengano
        # confrontati nel codice di filtro (vedi reload_sessions_table): così
        # il testo mostrato è tradotto ma il confronto resta coerente, perché
        # tr() ritorna sempre lo stesso valore per tutta la sessione (la
        # lingua cambia solo al riavvio del programma).
        self.telescope_combo.addItem(tr("Tutti"))
        self.telescope_combo.currentIndexChanged.connect(self.reload_sessions_table)
        filter_row.addWidget(self.telescope_combo)

        filter_row.addWidget(QLabel(tr("Modalità:")))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem(tr("Tutte"))
        self.mode_combo.addItems(["TELE", "WIDE", "STARTRAILS", "RESTACKED"])
        self.mode_combo.currentIndexChanged.connect(self.reload_sessions_table)
        filter_row.addWidget(self.mode_combo)

        filter_row.addWidget(QLabel(tr("Target:")))
        self.target_combo = QComboBox()
        self.target_combo.addItem(tr("Tutti"))
        self.target_combo.currentIndexChanged.connect(self.reload_sessions_table)
        filter_row.addWidget(self.target_combo, 1)

        filter_row.addWidget(QLabel(tr("Da:")))
        self.date_from = QDateEdit(calendarPopup=True)
        self.date_from.setDisplayFormat("yyyy-MM-dd")
        self.date_from.setMinimumDate(QDate(2000, 1, 1))
        self.date_from.setMaximumDate(QDate.currentDate())
        self.date_from.setDate(QDate(2024, 1, 1))
        self.date_from.dateChanged.connect(self.reload_sessions_table)
        filter_row.addWidget(self.date_from)

        filter_row.addWidget(QLabel(tr("A:")))
        self.date_to = QDateEdit(calendarPopup=True)
        self.date_to.setDisplayFormat("yyyy-MM-dd")
        self.date_to.setMinimumDate(QDate(2000, 1, 1))
        self.date_to.setMaximumDate(QDate.currentDate())
        self.date_to.setDate(QDate.currentDate())
        self.date_to.dateChanged.connect(self.reload_sessions_table)
        filter_row.addWidget(self.date_to)

        clear_btn = QPushButton(tr("Azzera filtri"))
        clear_btn.clicked.connect(self.clear_filters)
        filter_row.addWidget(clear_btn)
        main_layout.addLayout(filter_row)

        # --- Splitter centrale ---
        self.main_splitter = ProportionalSplitter(Qt.Orientation.Horizontal)

        # Pannello sinistro: tabella sessioni sopra e log sotto, in uno
        # splitter verticale dedicato (ridimensionabile, con barra di
        # scorrimento propria del log) - non più a tutta larghezza sotto
        # entrambi i pannelli, per lasciare tutta l'altezza della finestra
        # al pannello foto/dettagli a destra (richiesto da Nuccio).
        self.left_splitter = ProportionalSplitter(Qt.Orientation.Vertical)

        sessions_widget = QWidget()
        sessions_layout = QVBoxLayout(sessions_widget)
        sessions_layout.setContentsMargins(0, 0, 0, 0)

        self.sessions_table = QTableWidget(0, 11)
        self.sessions_table.setHorizontalHeaderLabels(
            [tr(h) for h in ["", "Data/Ora", "Target", "Telescopio", "Modo", "Filtro", "Esp(s)", "Gain",
                              "Raw OK", "Raw falliti", "Stack"]]
        )
        self.sessions_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sessions_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sessions_table.setSortingEnabled(True)
        self.sessions_table.itemSelectionChanged.connect(self.on_session_selected)
        self.sessions_table.itemChanged.connect(self._on_sessions_item_changed)
        sessions_layout.addWidget(self.sessions_table, 1)

        session_action_layout, self.session_action_buttons = build_file_action_row()
        self.session_action_buttons["remove_catalog"].clicked.connect(self.action_sessions_remove_catalog)
        self.session_action_buttons["delete_disk"].clicked.connect(self.action_sessions_delete_disk)
        self.session_action_buttons["rename"].clicked.connect(self.action_sessions_rename)
        self.session_action_buttons["move"].clicked.connect(self.action_sessions_move)
        self.session_action_buttons["copy"].clicked.connect(self.action_sessions_copy)
        sessions_layout.addLayout(session_action_layout)

        self.left_splitter.addWidget(sessions_widget)

        # --- Log, ancorato sotto la tabella (stesso pannello sinistro) ---
        log_widget = QWidget()
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(0, 4, 0, 0)
        log_layout.addWidget(QLabel(tr("Log:")))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000)
        log_layout.addWidget(self.log_view)
        self.left_splitter.addWidget(log_widget)
        self.left_splitter.setStretchFactor(0, 4)
        self.left_splitter.setStretchFactor(1, 1)

        self.main_splitter.addWidget(self.left_splitter)

        # --- Pannello dettaglio / anteprima ---
        # Diviso in tre sezioni ridimensionabili con uno splitter verticale
        # (foto sopra, informazioni al centro, pulsanti sotto): così ognuno può
        # adattare lo spazio dedicato a ciascuna parte allo schermo e alla
        # risoluzione che ha, invece di avere altezze fisse pensate per un solo
        # monitor (segnalato da un utente su schermo Full HD 1920x1080, dove i
        # pulsanti finivano fuori dalla finestra e foto/informazioni si
        # sovrapponevano).
        self.detail_splitter = ProportionalSplitter(Qt.Orientation.Vertical)

        self.preview_label = ScaledPixmapLabel(tr("Nessuna sessione selezionata"))
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Altezza minima ridotta (prima 360px fissi): resta solo una base di
        # partenza ragionevole, lo spazio reale lo decide l'utente trascinando
        # la barra dello splitter.
        self.preview_label.setMinimumHeight(120)
        self.preview_label.setFrameShape(QFrame.Shape.StyledPanel)
        self.detail_splitter.addWidget(self.preview_label)

        info_frame = QFrame()
        info_grid = QGridLayout(info_frame)
        info_grid.setContentsMargins(0, 4, 0, 4)
        self.info_labels = {}

        def _add_info_field(key, label, row, col):
            info_grid.addWidget(QLabel(f"<b>{tr(label)}</b>"), row, col)
            value_label = QLabel("—")
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            info_grid.addWidget(value_label, row, col + 1)
            self.info_labels[key] = value_label

        # I primi campi hanno valori brevi (poche cifre/parole): affiancarli
        # a due per riga evita che il pannello informazioni si allunghi
        # fino a invadere l'area della foto. Gli ultimi campi (percorso
        # cartella, identificazione SIMBAD, coordinate, condizioni) hanno
        # invece valori più lunghi e restano su una riga intera.
        compact_fields = [
            ("target", "Target:"), ("telescope", "Telescopio:"), ("mode", "Modalità:"),
            ("filter", "Filtro:"), ("datetime", "Data/ora:"), ("exposure", "Esposizione:"),
            ("gain", "Gain:"), ("temperature", "Temperatura:"), ("raw", "Raw OK / falliti:"),
            ("size", "Dimensione:"), ("shots_binning", "Binning:"), ("shots_count", "Scatti (fatti/stack/da fare):"),
        ]
        full_width_fields = [
            ("folder", "Cartella:"),
            ("object", "Oggetto (SIMBAD):"), ("coords", "Coordinate (RA/Dec):"),
            ("shots_coords", "RA/Dec richiesti (shotsInfo.json):"),
            ("conditions", "Condizioni allo scatto:"),
        ]

        row = 0
        for i in range(0, len(compact_fields), 2):
            for offset, (key, label) in enumerate(compact_fields[i:i + 2]):
                _add_info_field(key, label, row, offset * 2)
            row += 1
        for key, label in full_width_fields:
            info_grid.addWidget(QLabel(f"<b>{tr(label)}</b>"), row, 0)
            value_label = QLabel("—")
            value_label.setWordWrap(True)
            value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            info_grid.addWidget(value_label, row, 1, 1, 3)  # occupa le colonne restanti
            self.info_labels[key] = value_label
            row += 1

        info_grid.setColumnStretch(1, 1)
        info_grid.setColumnStretch(3, 1)

        # Il pannello informazioni va in una propria area con barra di
        # scorrimento: se un valore molto lungo (percorso cartella,
        # identificazione SIMBAD...) dovesse richiedere molte righe andate a
        # capo, scorre invece di "rubare" spazio a foto e pulsanti.
        info_scroll = QScrollArea()
        info_scroll.setWidgetResizable(True)
        info_scroll.setFrameShape(QFrame.Shape.NoFrame)
        info_scroll.setWidget(info_frame)
        self.detail_splitter.addWidget(info_scroll)

        # --- Pulsanti azione sessione ---
        # Un unico FlowLayout (invece di 3 righe fisse QHBoxLayout): i pulsanti
        # vanno a capo da soli quando lo spazio orizzontale non basta, così
        # non finiscono mai tagliati fuori dalla finestra su schermi stretti o
        # a bassa risoluzione.
        buttons_widget = QWidget()
        buttons_flow = FlowLayout(buttons_widget, margin=4, h_spacing=6, v_spacing=6)

        self.open_stack_btn = QPushButton(tr("Apri immagine stack"))
        self.open_stack_btn.setEnabled(False)
        self.open_stack_btn.setToolTip(tr(
            "Apre l'immagine stack principale della sessione (stacked.jpg o, su alcuni "
            "telescopi, altro formato) con l'app associata di Windows."))
        self.open_stack_btn.clicked.connect(self.open_stacked_jpg)
        buttons_flow.addWidget(self.open_stack_btn)
        self.open_annotated_btn = QPushButton(tr("Apri etichettata"))
        self.open_annotated_btn.setEnabled(False)
        self.open_annotated_btn.setToolTip(tr(
            "Apre l'immagine con le etichette astrometria nell'app Foto di Windows, per "
            "esaminarla con zoom e rotazione meglio che nell'anteprima del catalogo."))
        self.open_annotated_btn.clicked.connect(self.open_annotated_image)
        buttons_flow.addWidget(self.open_annotated_btn)
        self.open_folder_btn = QPushButton(tr("Apri cartella sessione in Esplora risorse"))
        self.open_folder_btn.setEnabled(False)
        self.open_folder_btn.clicked.connect(self.open_session_folder)
        buttons_flow.addWidget(self.open_folder_btn)
        self.open_session_btn = QPushButton(tr("Apri sessione"))
        self.open_session_btn.setEnabled(False)
        self.open_session_btn.clicked.connect(self.open_session_files_dialog)
        buttons_flow.addWidget(self.open_session_btn)

        self.identify_btn = QPushButton(tr("Identifica oggetto (SIMBAD)"))
        self.identify_btn.setEnabled(False)
        self.identify_btn.clicked.connect(self.identify_object)
        buttons_flow.addWidget(self.identify_btn)

        self.astrometry_btn = QPushButton(tr("Astrometria (etichetta oggetti)"))
        self.astrometry_btn.setEnabled(False)
        self.astrometry_btn.setToolTip(tr(
            "Risolve astrometricamente lo stack ed etichetta sulla foto gli oggetti presenti "
            "nel campo. Metodologia a scelta ogni volta: SIMBAD (via Siril, richiede "
            "siril-cli.exe e il catalogo Gaia locale) oppure Astrometry.net (locale, dentro "
            "WSL)."))
        self.astrometry_btn.clicked.connect(self.run_astrometry)
        buttons_flow.addWidget(self.astrometry_btn)
        self.print_btn = QPushButton(tr("Stampa"))
        self.print_btn.setEnabled(False)
        self.print_btn.clicked.connect(self.print_preview)
        buttons_flow.addWidget(self.print_btn)
        self.save_annotated_btn = QPushButton(tr("Salva"))
        self.save_annotated_btn.setEnabled(False)
        self.save_annotated_btn.setToolTip(tr(
            "Salva l'immagine con le etichette astrometria come nuovo file nella cartella "
            "sessione (l'originale non viene toccato)."))
        self.save_annotated_btn.clicked.connect(self.save_annotated)
        buttons_flow.addWidget(self.save_annotated_btn)
        self.toggle_original_btn = QPushButton(tr("Vedi originale"))
        self.toggle_original_btn.setEnabled(False)
        self.toggle_original_btn.setToolTip(tr(
            "Passa dall'immagine etichettata allo stack originale (e viceversa) "
            "senza rifare l'astrometria."))
        self.toggle_original_btn.clicked.connect(self.toggle_preview_original)
        buttons_flow.addWidget(self.toggle_original_btn)

        # Il widget dei pulsanti va aggiunto DIRETTAMENTE nello splitter (non
        # dentro una QScrollArea): lo splitter assegna al pannello la sua
        # larghezza reale esatta, e solo così il FlowLayout calcola
        # correttamente dove andare a capo. Con una QScrollArea di mezzo il
        # widget riceve invece la propria larghezza "preferita" (quella di
        # tutti i pulsanti in fila) e i pulsanti finirebbero comunque fuori
        # dalla vista. Se la sezione viene ridotta molto in altezza con la
        # barra dello splitter, alcuni pulsanti possono restare nascosti sotto
        # al bordo: in tal caso basta trascinare la barra per dare più spazio
        # a questa sezione (a scapito di foto o informazioni).
        buttons_widget.setMinimumHeight(60)
        buttons_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        self.detail_splitter.addWidget(buttons_widget)

        self._annotated_temp_path = None
        self._annotated_session_id = None
        self._annotated_used_fits = False
        self._annotated_method = "simbad"
        # Quando è disponibile un'immagine etichettata per la sessione
        # corrente, per default si mostra quella; True forza la vista sullo
        # stack originale finché non si cambia sessione o si rifà
        # l'astrometria (bottone "Vedi originale/etichettata").
        self._show_original = False
        self._astrometry_session_id = None

        self.main_splitter.addWidget(self.detail_splitter)
        self.main_splitter.setStretchFactor(0, 2)
        self.main_splitter.setStretchFactor(1, 3)
        main_layout.addWidget(self.main_splitter, 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        file_menu = self.menuBar().addMenu(tr("&File"))
        change_db_action = QAction(tr("Cambia percorso database…"), self)
        change_db_action.triggered.connect(self.change_db_path)
        file_menu.addAction(change_db_action)
        observer_action = QAction(tr("Imposta posizione osservativa…"), self)
        observer_action.triggered.connect(self.open_observer_location_dialog)
        file_menu.addAction(observer_action)
        siril_action = QAction(tr("Imposta percorso Siril (siril-cli.exe)…"), self)
        siril_action.triggered.connect(self.open_siril_path_dialog)
        file_menu.addAction(siril_action)

        # --- Sottomenu Lingua: applicata al prossimo avvio (vedi i18n.py) ---
        lingua_menu = file_menu.addMenu(tr("Lingua"))
        self._lingua_group = QActionGroup(self)
        self._lingua_group.setExclusive(True)
        current_lang = get_language()
        for code, label in LANGUAGES.items():
            lang_action = QAction(label, self)
            lang_action.setCheckable(True)
            lang_action.setChecked(code == current_lang)
            lang_action.triggered.connect(lambda checked, c=code: self._on_language_selected(c))
            self._lingua_group.addAction(lang_action)
            lingua_menu.addAction(lang_action)

        exit_action = QAction(tr("Esci"), self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        help_menu = self.menuBar().addMenu(tr("&Aiuto"))
        about_action = QAction(tr("Informazioni su…"), self)
        about_action.triggered.connect(self.open_about_dialog)
        help_menu.addAction(about_action)

        self.current_row_data = None

    def _on_language_selected(self, lang_code):
        if lang_code == self.settings.value("language", "it", type=str):
            return
        self.settings.setValue("language", lang_code)
        QMessageBox.information(
            self, tr("Lingua"),
            "La nuova lingua sarà attiva al prossimo avvio del programma: "
            "chiudi e riapri Catalogo Sessioni Astronomiche DWARF.\n\n"
            "The new language will take effect the next time you start the "
            "program: close and reopen DWARF Astronomical Session Catalog.")

    def open_about_dialog(self):
        QMessageBox.about(
            self, tr("Informazioni su Catalogo Sessioni Astronomiche DWARF"),
            f"<b>{tr('Catalogo Sessioni Astronomiche DWARF v. 1.1')}</b><br><br>"
            + tr("Creata da Nuccio Mandarà con l'aiuto fondamentale di Claude AI."))

    def _load_settings(self):
        last_root = self.settings.value("last_root", "")
        if last_root:
            self.root_edit.setText(last_root)

        geometry = self.settings.value("mainwindow/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
            # Una geometria salvata su un monitor (o con una configurazione di
            # monitor multipli) diversa da quella attuale può risultare troppo
            # grande o posizionata parzialmente/interamente fuori dallo
            # schermo visibile: qui la si corregge per farla rientrare sempre
            # nello schermo disponibile, qualunque sia la risoluzione.
            self._clamp_geometry_to_screen()
            self._geometry_restored = True
        else:
            self._geometry_restored = False

        header_state = self.settings.value("mainwindow/sessions_header")
        if header_state is not None:
            self.sessions_table.horizontalHeader().restoreState(header_state)
            self._sessions_header_restored = True
        else:
            self._sessions_header_restored = False

        splitter_state = self.settings.value("mainwindow/splitter")
        if splitter_state is not None:
            self.main_splitter.restoreState(splitter_state)
            self._splitter_restored = True
        else:
            self._splitter_restored = False

        left_splitter_state = self.settings.value("mainwindow/left_splitter")
        if left_splitter_state is not None:
            self.left_splitter.restoreState(left_splitter_state)
            self._left_splitter_restored = True
        else:
            self._left_splitter_restored = False

        detail_splitter_state = self.settings.value("mainwindow/detail_splitter")
        if detail_splitter_state is not None:
            self.detail_splitter.restoreState(detail_splitter_state)
            self._detail_splitter_restored = True
        else:
            self._detail_splitter_restored = False

    def _clamp_geometry_to_screen(self):
        """Se la finestra ripristinata (self.geometry(), posizione+dimensioni)
        non sta interamente dentro lo schermo attualmente disponibile (bordi
        utili, esclusa la barra delle applicazioni di Windows), la riduce e/o
        riposiziona per farcela rientrare. Risolve il caso di impostazioni
        salvate su un monitor diverso (più grande, o con disposizione
        multi-monitor diversa) da quello in uso ora."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        geo = self.geometry()

        width = min(geo.width(), avail.width())
        height = min(geo.height(), avail.height())

        x = geo.x()
        y = geo.y()
        if x < avail.x():
            x = avail.x()
        if y < avail.y():
            y = avail.y()
        if x + width > avail.x() + avail.width():
            x = avail.x() + avail.width() - width
        if y + height > avail.y() + avail.height():
            y = avail.y() + avail.height() - height

        if (width, height) != (geo.width(), geo.height()) or (x, y) != (geo.x(), geo.y()):
            self.setGeometry(x, y, width, height)

    def _set_default_splitter_sizes(self):
        """Proporzioni di default degli splitter al primo avvio (nessuno stato
        salvato): nello splitter centrale la tabella prende solo lo spazio
        necessario alle colonne (già ridotte al minimo), il resto va
        all'anteprima; nello splitter sinistro la tabella prende la maggior
        parte dell'altezza e il log una striscia inferiore (ridimensionabile,
        con barra di scorrimento propria)."""
        if not self._splitter_restored:
            total = self.main_splitter.width()
            if total > 0:
                table_w = (self.sessions_table.horizontalHeader().length()
                           + self.sessions_table.verticalHeader().width() + 30)
                table_w = max(250, min(table_w, int(total * 0.55)))
                self.main_splitter.setSizes([table_w, max(300, total - table_w)])

        if not self._left_splitter_restored:
            left_total = self.left_splitter.height()
            if left_total > 0:
                self.left_splitter.setSizes([max(200, int(left_total * 0.8)), max(100, int(left_total * 0.2))])

        if not self._detail_splitter_restored:
            detail_total = self.detail_splitter.height()
            if detail_total > 0:
                # Foto ~50%, informazioni ~35%, pulsanti ~15% - restano comunque
                # tutte e tre ridimensionabili trascinando le barre divisorie.
                photo_h = max(150, int(detail_total * 0.50))
                info_h = max(120, int(detail_total * 0.35))
                buttons_h = max(70, detail_total - photo_h - info_h)
                self.detail_splitter.setSizes([photo_h, info_h, buttons_h])

    # ------------------------------------------------------------------
    def browse_root(self):
        path = QFileDialog.getExistingDirectory(self, "Seleziona la cartella radice (es. Cartelle_RAW)")
        if path:
            self.root_edit.setText(path)

    def append_log(self, msg):
        # Oltre a mostrarlo nel pannello Log della finestra, ogni messaggio
        # viene scritto anche nel file logs/dwarf_catalog.log: così, se il
        # programma dovesse chiudersi inaspettatamente (es. un crash
        # nell'eseguibile compilato), resta comunque una traccia su disco di
        # cosa stava facendo fino a un attimo prima - il pannello a schermo
        # da solo non la conserva.
        logger.info(msg)
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{timestamp}] {msg}")
        # Forza lo scroll all'ultima riga: senza, se l'utente aveva scrollato
        # in alto, il messaggio finale (es. "Astrometria completata...") può
        # restare fuori vista e sembrare che l'elaborazione sia ancora in corso.
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def start_scan(self):
        root_path = self.root_edit.text().strip()
        if not root_path or not os.path.isdir(root_path):
            QMessageBox.warning(self, tr("Cartella non valida"),
                                 tr("Seleziona una cartella radice valida prima di scansionare."))
            return

        self.settings.setValue("last_root", root_path)
        self.scan_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.append_log(tr("Avvio scansione: {root}").format(root=root_path))

        self.worker = ScanWorker(
            self.db_path, self.thumb_dir, root_path,
            dry_run=self.dry_run_chk.isChecked(),
            remove_orphans=self.remove_orphans_chk.isChecked(),
        )
        self.worker.progress.connect(self.on_progress)
        self.worker.log_line.connect(self.append_log)
        self.worker.finished_ok.connect(self.on_scan_finished)
        self.worker.start()

    def stop_scan(self):
        if self.worker:
            self.worker.stop()
            self.stop_btn.setEnabled(False)

    def on_progress(self, current, total, message):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
        self.status_bar.showMessage(tr("Elaborazione: {message}").format(message=message))

    def on_scan_finished(self, stats):
        self.scan_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.append_log(tr(
            "Terminato. Sessioni trovate: {found}, nuove: {added}, "
            "aggiornate: {updated}, invariate: {unchanged}, "
            "rimosse: {removed}, non riconosciute: {unrecognized}, "
            "errori: {errors}"
        ).format(
            found=stats.sessions_found, added=stats.sessions_added,
            updated=stats.sessions_updated, unchanged=stats.sessions_unchanged,
            removed=stats.sessions_removed, unrecognized=stats.unrecognized_folders,
            errors=stats.errors,
        ))
        self.db.close()
        self.db = CatalogDB(self.db_path)
        self.reload_telescope_combo()
        self.reload_target_combo()
        self.reload_sessions_table()
        self.update_status_bar()

    def clear_filters(self):
        self.telescope_combo.setCurrentIndex(0)
        self.mode_combo.setCurrentIndex(0)
        self.target_combo.setCurrentIndex(0)
        self.date_from.setDate(QDate(2024, 1, 1))
        self.date_to.setDate(QDate.currentDate())

    def reload_telescope_combo(self):
        current = self.telescope_combo.currentText() or tr("Tutti")
        self.telescope_combo.blockSignals(True)
        self.telescope_combo.clear()
        self.telescope_combo.addItem(tr("Tutti"))
        self.telescope_combo.addItems(self.db.distinct_telescopes())
        idx = self.telescope_combo.findText(current)
        self.telescope_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.telescope_combo.blockSignals(False)

    def reload_target_combo(self):
        current = self.target_combo.currentText() or tr("Tutti")
        self.target_combo.blockSignals(True)
        self.target_combo.clear()
        self.target_combo.addItem(tr("Tutti"))
        self.target_combo.addItems(self.db.distinct_targets())
        idx = self.target_combo.findText(current)
        self.target_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.target_combo.blockSignals(False)

    def reload_sessions_table(self):
        telescope = self.telescope_combo.currentText()
        mode = self.mode_combo.currentText()
        target = self.target_combo.currentText()
        date_from = self.date_from.date().toString("yyyy-MM-dd")
        date_to = self.date_to.date().toString("yyyy-MM-dd")

        rows = self.db.all_sessions(
            telescope_filter=telescope if telescope != tr("Tutti") else None,
            mode_filter=mode if mode != tr("Tutte") else None,
            target_filter=target if target != tr("Tutti") else None,
            date_from=date_from,
            date_to=date_to,
        )

        self.sessions_table.setSortingEnabled(False)
        self.sessions_table.blockSignals(True)
        self.sessions_table.setRowCount(0)
        for row in rows:
            r = self.sessions_table.rowCount()
            self.sessions_table.insertRow(r)
            self.sessions_table.setItem(r, COL_SEL, make_checkbox_item(row["id"]))
            dt_display = (row["session_datetime"] or "?").replace("T", " ")[:19]
            self.sessions_table.setItem(r, COL_DATETIME, NumericItem(row["session_datetime"] or "", dt_display))
            target_item = QTableWidgetItem(row["target"] or "?")
            if row["thumbnail_path"] and os.path.isfile(row["thumbnail_path"]):
                target_item.setIcon(QIcon(QPixmap(row["thumbnail_path"])))
            self.sessions_table.setItem(r, COL_TARGET, target_item)
            self.sessions_table.setItem(r, COL_TELESCOPE, QTableWidgetItem(row["telescope"]))
            self.sessions_table.setItem(r, COL_MODE, QTableWidgetItem(row["mode"] or "—"))
            self.sessions_table.setItem(r, COL_FILTER, QTableWidgetItem(row["filter"] or "---"))
            self.sessions_table.setItem(r, COL_EXP, NumericItem(row["exposure"], str(row["exposure"])))
            self.sessions_table.setItem(r, COL_GAIN, NumericItem(row["gain"], str(row["gain"])))
            self.sessions_table.setItem(r, COL_OK, NumericItem(row["raw_ok_count"], str(row["raw_ok_count"])))
            self.sessions_table.setItem(r, COL_FAILED, NumericItem(row["raw_failed_count"], str(row["raw_failed_count"])))
            stack_label = tr("sì") if row["stacked_jpg_path"] else tr("no")
            self.sessions_table.setItem(r, COL_STACK, QTableWidgetItem(stack_label))
            self.sessions_table.item(r, COL_DATETIME).setData(Qt.ItemDataRole.UserRole, row["id"])
        self.sessions_table.blockSignals(False)
        self.sessions_table.setSortingEnabled(True)
        self.sessions_table.sortItems(COL_DATETIME, Qt.SortOrder.DescendingOrder)
        self._update_session_action_buttons()

    def on_session_selected(self):
        items = self.sessions_table.selectedItems()
        if not items:
            return
        row_idx = items[0].row()
        session_id = self.sessions_table.item(row_idx, COL_DATETIME).data(Qt.ItemDataRole.UserRole)
        row = self.db.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return
        self.current_row_data = row

        self.info_labels["target"].setText(row["target"] or "?")
        self.info_labels["telescope"].setText(row["telescope"] or "?")
        self.info_labels["mode"].setText(row["mode"] or "?")
        self.info_labels["filter"].setText(row["filter"] or "---")
        self.info_labels["datetime"].setText((row["session_datetime"] or "?").replace("T", " "))
        self.info_labels["exposure"].setText(f"{row['exposure']} s" if row["exposure"] is not None else "?")
        self.info_labels["gain"].setText(str(row["gain"]) if row["gain"] is not None else "?")
        temp_text = f"{row['temperature']:.1f} °C" if row["temperature"] is not None else "?"
        shots_temp_min = row["shots_temp_min"] if "shots_temp_min" in row.keys() else None
        shots_temp_max = row["shots_temp_max"] if "shots_temp_max" in row.keys() else None
        if shots_temp_min is not None or shots_temp_max is not None:
            lo = f"{shots_temp_min:.1f}" if shots_temp_min is not None else "?"
            hi = f"{shots_temp_max:.1f}" if shots_temp_max is not None else "?"
            temp_text += f" (min {lo} / max {hi} °C)"
        self.info_labels["temperature"].setText(temp_text)
        self.info_labels["raw"].setText(tr("{ok} OK / {failed} falliti").format(
            ok=row['raw_ok_count'], failed=row['raw_failed_count']))
        self.info_labels["size"].setText(human_size(row["total_size"]))
        self.info_labels["folder"].setText(row["folder_path"])

        # Dati opzionali letti da shotsInfo.json (quando la sessione lo aveva):
        # assenti nella maggior parte delle sessioni più vecchie.
        shots_binning = row["shots_binning"] if "shots_binning" in row.keys() else None
        self.info_labels["shots_binning"].setText(shots_binning or "—")
        shots_taken = row["shots_taken"] if "shots_taken" in row.keys() else None
        shots_stacked = row["shots_stacked"] if "shots_stacked" in row.keys() else None
        shots_to_take = row["shots_to_take"] if "shots_to_take" in row.keys() else None
        if shots_taken is not None or shots_stacked is not None or shots_to_take is not None:
            self.info_labels["shots_count"].setText(
                f"{shots_taken if shots_taken is not None else '?'} / "
                f"{shots_stacked if shots_stacked is not None else '?'} / "
                f"{shots_to_take if shots_to_take is not None else '?'}")
        else:
            self.info_labels["shots_count"].setText("—")
        shots_ra = row["shots_ra"] if "shots_ra" in row.keys() else None
        shots_dec = row["shots_dec"] if "shots_dec" in row.keys() else None
        if shots_ra or shots_dec:
            self.info_labels["shots_coords"].setText(f"RA {shots_ra or '?'} / Dec {shots_dec or '?'}")
        else:
            self.info_labels["shots_coords"].setText("—")

        stack_available = bool(row["stacked_jpg_path"] and os.path.isfile(row["stacked_jpg_path"]))
        self.open_stack_btn.setEnabled(stack_available)

        # Ogni nuova selezione riparte mostrando, per default, l'etichettata
        # se questa sessione ne ha già una (calcolata in questa sessione di
        # lavoro dell'app); l'utente può comunque tornare all'originale con
        # il bottone "Vedi originale".
        self._show_original = False
        annotated_available = self._refresh_preview()

        self.open_folder_btn.setEnabled(bool(row["folder_path"]))
        self.open_session_btn.setEnabled(bool(row["folder_path"]))
        self.identify_btn.setEnabled(bool(row["target"]))
        astrometry_source_available = bool(
            (row["stacked_fits_path"] and os.path.isfile(row["stacked_fits_path"]))
            or stack_available)
        self.astrometry_btn.setEnabled(astrometry_source_available)
        self.save_annotated_btn.setEnabled(annotated_available)
        self.open_annotated_btn.setEnabled(annotated_available)
        self._display_object_info(row)

    def _refresh_preview(self):
        """Aggiorna l'anteprima, il bottone Stampa e il bottone di
        alternanza originale/etichettata in base a self.current_row_data e
        self._show_original. Ritorna True se per questa sessione esiste
        un'immagine etichettata (indipendentemente da quale delle due sia
        mostrata al momento)."""
        row = self.current_row_data
        if not row:
            self.preview_label.setText(tr("Nessuna sessione selezionata"))
            self.preview_label.setPixmap(QPixmap())
            self.toggle_original_btn.setEnabled(False)
            self.print_btn.setEnabled(False)
            return False

        stack_available = bool(row["stacked_jpg_path"] and os.path.isfile(row["stacked_jpg_path"]))
        annotated_available = bool(
            self._annotated_session_id == row["id"] and self._annotated_temp_path
            and os.path.isfile(self._annotated_temp_path))

        if annotated_available and not self._show_original:
            show_path = self._annotated_temp_path
        elif stack_available:
            show_path = row["stacked_jpg_path"]
        else:
            show_path = None

        if show_path:
            pixmap = QPixmap(show_path)
            if not pixmap.isNull():
                # self.preview_label è una ScaledPixmapLabel: le basta
                # l'immagine alla risoluzione originale, si scala (e ri-scala
                # da sola a ogni ridimensionamento del riquadro) per conto suo.
                self.preview_label.setPixmap(pixmap)
            else:
                self.preview_label.setText(tr("Impossibile visualizzare l'immagine"))
                self.preview_label.setPixmap(QPixmap())
        else:
            self.preview_label.setText(tr("Nessuno stack disponibile per questa sessione"))
            self.preview_label.setPixmap(QPixmap())

        self.toggle_original_btn.setEnabled(annotated_available)
        self.toggle_original_btn.setText(
            tr("Vedi etichettata") if (annotated_available and self._show_original) else tr("Vedi originale"))
        self.print_btn.setEnabled(show_path is not None)
        return annotated_available

    def toggle_preview_original(self):
        self._show_original = not self._show_original
        self._refresh_preview()

    def open_stacked_jpg(self):
        if self.current_row_data and self.current_row_data["stacked_jpg_path"]:
            self._open_path(self.current_row_data["stacked_jpg_path"])

    def open_annotated_image(self):
        # Apre con l'app associata di Windows (di norma Foto), che offre
        # zoom e rotazione a differenza dell'anteprima nel catalogo.
        row = self.current_row_data
        if (row and self._annotated_session_id == row["id"] and self._annotated_temp_path
                and os.path.isfile(self._annotated_temp_path)):
            self._open_path(self._annotated_temp_path)

    def open_session_folder(self):
        if self.current_row_data and self.current_row_data["folder_path"]:
            self._open_path(self.current_row_data["folder_path"])

    def open_session_files_dialog(self):
        if not self.current_row_data or not self.current_row_data["folder_path"]:
            return
        folder = self.current_row_data["folder_path"]
        if not os.path.isdir(folder):
            QMessageBox.warning(self, tr("Cartella non trovata"),
                                 tr("La cartella della sessione non è più presente sul disco:\n{folder}").format(folder=folder))
            return
        label = self.current_row_data["target"] or os.path.basename(folder)
        dlg = SessionFilesDialog(folder, label, self.db, self.thumb_dir, self,
                                  on_change=self._on_session_files_changed)
        dlg.exec()

    def _on_session_files_changed(self):
        self.reload_sessions_table()
        self.update_status_bar()
        if self.current_row_data:
            fresh = self.db.get_session_by_id(self.current_row_data["id"])
            if fresh:
                self.current_row_data = fresh
                self.info_labels["raw"].setText(
                    f"{fresh['raw_ok_count']} OK / {fresh['raw_failed_count']} falliti")
                self.info_labels["size"].setText(human_size(fresh["total_size"]))

    # ------------------------------------------------------------------
    # Selezione ed elaborazione sessioni (elimina/rinomina/sposta/copia)
    # ------------------------------------------------------------------
    def _on_sessions_item_changed(self, item):
        if item.column() == COL_SEL:
            self._update_session_action_buttons()

    def _update_session_action_buttons(self):
        n = len(checked_rows_data(self.sessions_table, COL_SEL))
        self.session_action_buttons["remove_catalog"].setEnabled(n >= 1)
        self.session_action_buttons["delete_disk"].setEnabled(n >= 1)
        self.session_action_buttons["rename"].setEnabled(n == 1)
        self.session_action_buttons["move"].setEnabled(n >= 1)
        self.session_action_buttons["copy"].setEnabled(n >= 1)

    def _checked_session_rows_data(self):
        ids = checked_rows_data(self.sessions_table, COL_SEL)
        rows = [self.db.get_session_by_id(i) for i in ids]
        return [r for r in rows if r]

    def action_sessions_remove_catalog(self):
        rows = self._checked_session_rows_data()
        if not rows:
            return
        names = "\n".join(f"- {r['target'] or '?'} ({os.path.basename(r['folder_path'])})" for r in rows[:20])
        more = "" if len(rows) <= 20 else tr("\n… e altre {n}").format(n=len(rows) - 20)
        if not confirm_action(self, tr("Rimuovi dal catalogo"),
                               tr("Rimuovere {n} sessione/i dal catalogo?\n"
                                  "(i file sul disco NON vengono toccati)\n\n{names}{more}").format(
                                   n=len(rows), names=names, more=more)):
            return
        for r in rows:
            self.db.delete_session_by_id(r["id"])
        self.db.commit()
        self.reload_sessions_table()
        self.reload_target_combo()
        self.update_status_bar()
        self.append_log(tr("Rimosse {n} sessioni dal catalogo (file su disco non toccati).").format(n=len(rows)))

    def action_sessions_delete_disk(self):
        rows = self._checked_session_rows_data()
        if not rows:
            return
        names = "\n".join(f"- {r['folder_path']}" for r in rows[:20])
        more = "" if len(rows) <= 20 else tr("\n… e altre {n}").format(n=len(rows) - 20)
        if not confirm_action(self, tr("Elimina dal disco"),
                               tr("ATTENZIONE: eliminare DEFINITIVAMENTE {n} cartella/e di sessione "
                                  "dal disco (con tutti i raw e gli stacked contenuti) e dal catalogo?\n"
                                  "Questa operazione non è reversibile.\n\n{names}{more}").format(
                                   n=len(rows), names=names, more=more)):
            return
        errors = []
        for r in rows:
            try:
                file_ops.delete_path(r["folder_path"])
                self.db.delete_session_by_id(r["id"])
            except Exception as exc:
                errors.append(f"{r['folder_path']}: {exc}")
        self.db.commit()
        self.reload_sessions_table()
        self.reload_target_combo()
        self.update_status_bar()
        if errors:
            QMessageBox.warning(self, tr("Alcuni errori"), tr("Errori durante l'eliminazione:\n") + "\n".join(errors))
        self.append_log(tr("Eliminate dal disco {n} sessioni.").format(n=len(rows) - len(errors)))

    def action_sessions_rename(self):
        rows = self._checked_session_rows_data()
        if len(rows) != 1:
            return
        row = rows[0]
        old_path = row["folder_path"]
        old_name = os.path.basename(old_path.rstrip(os.sep))
        new_name, ok = QInputDialog.getText(self, tr("Rinomina sessione"), tr("Nuovo nome cartella:"), text=old_name)
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        if not confirm_action(self, tr("Rinomina sessione"),
                               tr("Rinominare la cartella:\n{old_path}\nin '{new}'?").format(
                                   old_path=old_path, new=new_name.strip())):
            return
        try:
            new_path = file_ops.rename_path(old_path, new_name.strip())
            self.db.update_session_folder_path(row["id"], old_path, new_path)
            self.db.commit()
        except Exception as exc:
            QMessageBox.warning(self, tr("Errore"), tr("Rinomina non riuscita:\n{exc}").format(exc=exc))
            return
        self.reload_sessions_table()
        self.append_log(tr("Sessione rinominata: {old} -> {new}").format(old=old_path, new=new_path))

    def action_sessions_move(self):
        rows = self._checked_session_rows_data()
        if not rows:
            return
        dest = QFileDialog.getExistingDirectory(self, tr("Cartella di destinazione"))
        if not dest:
            return
        if not confirm_action(self, tr("Sposta sessioni"),
                               tr("Spostare {n} cartella/e di sessione in:\n{dest}?").format(n=len(rows), dest=dest)):
            return
        errors = []
        moved = 0
        for r in rows:
            try:
                new_path = file_ops.move_path(r["folder_path"], dest)
                self.db.update_session_folder_path(r["id"], r["folder_path"], new_path)
                moved += 1
            except Exception as exc:
                errors.append(f"{r['folder_path']}: {exc}")
        self.db.commit()
        self.reload_sessions_table()
        if errors:
            QMessageBox.warning(self, tr("Alcuni errori"), tr("Errori durante lo spostamento:\n") + "\n".join(errors))
        self.append_log(tr("Spostate {n} sessioni in {dest}.").format(n=moved, dest=dest))

    def action_sessions_copy(self):
        rows = self._checked_session_rows_data()
        if not rows:
            return
        dest = QFileDialog.getExistingDirectory(self, tr("Cartella di destinazione"))
        if not dest:
            return
        if not confirm_action(self, tr("Copia sessioni"),
                               tr("Copiare {n} cartella/e di sessione in:\n{dest}?\n"
                                  "(la copia non viene aggiunta al catalogo: esegui una scansione di "
                                  "quella cartella se vuoi catalogarla)").format(n=len(rows), dest=dest)):
            return
        errors = []
        copied = 0
        for r in rows:
            try:
                file_ops.copy_path(r["folder_path"], dest)
                copied += 1
            except Exception as exc:
                errors.append(f"{r['folder_path']}: {exc}")
        if errors:
            QMessageBox.warning(self, tr("Alcuni errori"), tr("Errori durante la copia:\n") + "\n".join(errors))
        self.append_log(tr("Copiate {n} sessioni in {dest}.").format(n=copied, dest=dest))

    # ------------------------------------------------------------------
    # Identificazione oggetto (SIMBAD) e condizioni osservative (astropy)
    # ------------------------------------------------------------------
    def _display_object_info(self, row):
        # Il nome dell'oggetto (es. "NGC 281") va sempre mostrato per primo:
        # senza, se la ricerca del tipo su SIMBAD non trova nulla, restava
        # visibile solo la costellazione (es. "Cassiopea"), che sembrava
        # un'identificazione dell'oggetto mentre è solo il contesto — una
        # costellazione contiene innumerevoli oggetti diversi, non è
        # un'identificazione univoca.
        bits = []
        if row["object_name_resolved"]:
            bits.append(row["object_name_resolved"])
        if row["object_type"]:
            bits.append(row["object_type"])
        if row["object_constellation"]:
            bits.append(tr("cost. {c}").format(c=row['object_constellation']))
        if row["object_magnitude"] is not None:
            bits.append(tr("mag {m:.1f}").format(m=row['object_magnitude']))
        self.info_labels["object"].setText(" · ".join(bits) if bits else tr("non identificato"))

        if row["ra_deg"] is not None and row["dec_deg"] is not None:
            from astro_extra import format_ra_hms, format_dec_dms
            ra_txt = format_ra_hms(row["ra_deg"])
            dec_txt = format_dec_dms(row["dec_deg"])
            if ra_txt is not None and dec_txt is not None:
                self.info_labels["coords"].setText(f"RA {ra_txt}  Dec {dec_txt}")
            else:
                self.info_labels["coords"].setText(f"RA {row['ra_deg']:.4f}°  Dec {row['dec_deg']:+.4f}°")
        else:
            self.info_labels["coords"].setText("?")

        cond_bits = []
        if row["altitude_deg"] is not None:
            az_bit = tr(" (az {a:.0f}°)").format(a=row['azimuth_deg']) if row["azimuth_deg"] is not None else ""
            cond_bits.append(tr("altezza {h:.0f}°{az_bit}").format(h=row['altitude_deg'], az_bit=az_bit))
        if row["moon_phase_pct"] is not None and row["moon_separation_deg"] is not None:
            cond_bits.append(tr("Luna {pct:.0f}% a {sep:.0f}°").format(
                pct=row['moon_phase_pct'], sep=row['moon_separation_deg']))
        self.info_labels["conditions"].setText(" · ".join(cond_bits) if cond_bits else "?")

    def _get_observer_location(self):
        lat = self.settings.value("observer/lat", type=float)
        lon = self.settings.value("observer/lon", type=float)
        elev = self.settings.value("observer/elev", type=float)
        return lat, lon, elev

    def _ask_observer_location(self, current):
        lat, lon, elev = current
        dlg = ObserverLocationDialog(lat, lon, elev, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        values = dlg.values()
        if values is None:
            QMessageBox.warning(self, tr("Valori non validi"), tr("Inserisci coordinate numeriche valide."))
            return None
        lat, lon, elev = values
        self.settings.setValue("observer/lat", lat)
        self.settings.setValue("observer/lon", lon)
        self.settings.setValue("observer/elev", elev)
        return lat, lon, elev

    def open_observer_location_dialog(self):
        self._ask_observer_location(self._get_observer_location())

    def identify_object(self):
        if not self.current_row_data:
            return
        target = self.current_row_data["target"]
        if not target:
            QMessageBox.information(self, tr("Identifica oggetto"), tr("Questa sessione non ha un nome target."))
            return

        lat, lon, elev = self._get_observer_location()
        if lat is None or lon is None:
            result = self._ask_observer_location((lat, lon, elev))
            if result is None:
                return
            lat, lon, elev = result

        self._identify_session_id = self.current_row_data["id"]
        self.identify_btn.setEnabled(False)
        self.identify_btn.setText(tr("Ricerca in corso…"))
        self.object_worker = ObjectLookupWorker(
            target, self.current_row_data["session_datetime"], lat, lon, elev)
        self.object_worker.finished_ok.connect(self._on_identify_finished)
        self.object_worker.start()

    def _on_identify_finished(self, info, error):
        self.identify_btn.setEnabled(True)
        self.identify_btn.setText(tr("Identifica oggetto (SIMBAD)"))
        if error:
            QMessageBox.warning(self, tr("Identifica oggetto"), error)
            return
        self.db.update_session_object_info(
            self._identify_session_id,
            object_type=info.get("object_type"),
            object_constellation=info.get("constellation"),
            object_magnitude=info.get("magnitude"),
            object_name_resolved=info.get("object_name_resolved"),
            ra_deg=info.get("ra_deg"), dec_deg=info.get("dec_deg"),
            altitude_deg=info.get("altitude_deg"), azimuth_deg=info.get("azimuth_deg"),
            moon_phase_pct=info.get("moon_phase_pct"), moon_separation_deg=info.get("moon_separation_deg"),
        )
        self.db.commit()
        if self.current_row_data and self.current_row_data["id"] == self._identify_session_id:
            fresh = self.db.get_session_by_id(self._identify_session_id)
            self.current_row_data = fresh
            self._display_object_info(fresh)
        self.append_log(tr("Oggetto identificato: {name}").format(name=info.get('object_name_resolved') or '?'))

    def _get_siril_cli_path(self):
        """Ritorna il percorso salvato di siril-cli.exe se è ancora valido,
        altrimenti prova i percorsi tipici di installazione su Windows;
        se lo trova lì lo salva per le volte successive. Ritorna None se
        non è configurato né rintracciabile automaticamente."""
        from dwarf_astrometry import find_default_siril_cli
        path = self.settings.value("siril/cli_path", type=str)
        if path and os.path.isfile(path):
            return path
        default = find_default_siril_cli()
        if default:
            self.settings.setValue("siril/cli_path", default)
            return default
        return None

    def _ask_siril_cli_path(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Individua siril-cli.exe"), r"C:\Program Files\Siril\bin",
            tr("siril-cli.exe;;Tutti i file (*)"))
        if path:
            self.settings.setValue("siril/cli_path", path)
            return path
        return None

    def open_siril_path_dialog(self):
        self._ask_siril_cli_path()

    def run_astrometry(self):
        if not self.current_row_data:
            return
        row = self.current_row_data

        fits_path = row["stacked_fits_path"] if (
            row["stacked_fits_path"] and os.path.isfile(row["stacked_fits_path"])) else None
        jpg_path = row["stacked_jpg_path"] if (
            row["stacked_jpg_path"] and os.path.isfile(row["stacked_jpg_path"])) else None

        if not fits_path and not jpg_path:
            QMessageBox.information(self, tr("Astrometria"), tr("Nessuno stack disponibile per questa sessione."))
            return

        dlg = AstrometryOptionsDialog(
            self,
            offer_source_choice=bool(fits_path and jpg_path),
            fits_label=os.path.basename(fits_path) if fits_path else "",
            jpg_label=os.path.basename(jpg_path) if jpg_path else "",
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return  # annullato dall'utente

        method = dlg.method()  # "simbad" oppure "astrometry_net"
        include_stars = dlg.stars_check.isChecked()

        chosen_use_fits = dlg.use_fits()
        if chosen_use_fits is None:
            # un solo file disponibile: nessuna scelta da fare
            display_use_fits = fits_path is not None
        else:
            display_use_fits = chosen_use_fits
        display_source = fits_path if display_use_fits else jpg_path

        siril_path = None
        if method == "simbad":
            siril_path = self._get_siril_cli_path()
            if not siril_path:
                QMessageBox.information(
                    self, tr("Astrometria"),
                    tr("Non trovo siril-cli.exe. Indica il percorso dell'eseguibile."))
                siril_path = self._ask_siril_cli_path()
                if not siril_path:
                    return

        # Con SIMBAD il plate solving va sempre fatto sul FITS quando c'è:
        # porta con sé la posizione di puntamento E la dimensione del
        # pixel/focale del sensore, che Siril richiede e che un jpg
        # semplice non ha (la scelta dell'utente riguarda lì solo su quale
        # immagine disegnare le etichette). Con Astrometry.net, invece, la
        # risoluzione è "alla cieca" e produce essa stessa l'immagine
        # annotata: risolve esattamente il file scelto per la
        # visualizzazione.
        if method == "simbad":
            solve_source = fits_path or jpg_path
        else:
            solve_source = display_source

        method_label = "SIMBAD" if method == "simbad" else "Astrometry.net"
        self._astrometry_session_id = row["id"]
        self.astrometry_btn.setEnabled(False)
        self.astrometry_btn.setText(tr("Elaborazione…"))
        self.append_log(tr(
            "Astrometria ({method}): risoluzione su {solve_name}, "
            "etichette su {display_name}…").format(
                method=method_label, solve_name=os.path.basename(solve_source),
                display_name=os.path.basename(display_source)))
        self.astrometry_worker = AstrometryWorker(
            solve_source, display_source, display_use_fits, siril_path, include_stars,
            target_name=row["target"], ra_hint=row["ra_deg"], dec_hint=row["dec_deg"],
            method=method)
        self.astrometry_worker.progress.connect(self.append_log)
        self.astrometry_worker.finished_ok.connect(self._on_astrometry_finished)
        self.astrometry_worker.start()

    def _on_astrometry_finished(self, result, error):
        self.astrometry_btn.setEnabled(True)
        self.astrometry_btn.setText(tr("Astrometria (etichetta oggetti)"))
        if error:
            QMessageBox.warning(self, tr("Astrometria"), error)
            return

        if not self.current_row_data or self.current_row_data["id"] != self._astrometry_session_id:
            # la selezione è cambiata nel frattempo: scarta il risultato
            try:
                os.remove(result["annotated_path"])
            except OSError:
                pass
            return

        self._annotated_temp_path = result["annotated_path"]
        self._annotated_session_id = self._astrometry_session_id
        self._annotated_used_fits = bool(result.get("used_fits"))
        self._annotated_method = result.get("method", "simbad")
        # Un'astrometria appena calcolata si mostra sempre subito, anche se
        # in precedenza si era scelto di vedere l'originale per questa
        # sessione.
        self._show_original = False
        self._refresh_preview()
        self.save_annotated_btn.setEnabled(True)
        self.open_annotated_btn.setEnabled(True)

        if self._annotated_method == "astrometry_net":
            msg = tr("Astrometria (Astrometry.net) completata: campo risolto, "
                     "{n} oggetti nel campo.").format(n=result['n_labeled'])
        else:
            msg = tr("Astrometria (SIMBAD) completata: {n} oggetti "
                     "etichettati (notevoli: {n_notable}").format(
                         n=result['n_labeled'], n_notable=result['n_notable'])
            if result.get("n_stars"):
                msg += tr(", stelle luminose: {n_stars}").format(n_stars=result['n_stars'])
            msg += ")."
        self.append_log(msg)
        if result.get("warnings"):
            QMessageBox.information(
                self, tr("Astrometria"),
                tr("Etichettatura completata, con alcuni avvisi:\n\n") + "\n\n".join(result["warnings"]))

    def _current_preview_path(self):
        """Ritorna il percorso dell'immagine attualmente mostrata
        nell'anteprima (rispetta il bottone Vedi originale/etichettata),
        così "Stampa" stampa esattamente quello che si vede a schermo."""
        row = self.current_row_data
        if not row:
            return None
        annotated_available = bool(
            self._annotated_session_id == row["id"] and self._annotated_temp_path
            and os.path.isfile(self._annotated_temp_path))
        if annotated_available and not self._show_original:
            return self._annotated_temp_path
        if row["stacked_jpg_path"] and os.path.isfile(row["stacked_jpg_path"]):
            return row["stacked_jpg_path"]
        return None

    def print_preview(self):
        path = self._current_preview_path()
        if not path:
            QMessageBox.information(self, tr("Stampa"), tr("Nessuna immagine da stampare."))
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            QMessageBox.warning(self, tr("Stampa"), tr("Impossibile caricare l'immagine da stampare."))
            return

        from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
        from PyQt6.QtGui import QPainter
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        painter = QPainter(printer)
        rect = painter.viewport()
        size = pixmap.size()
        size.scale(rect.size(), Qt.AspectRatioMode.KeepAspectRatio)
        painter.setViewport(rect.x(), rect.y(), size.width(), size.height())
        painter.setWindow(pixmap.rect())
        painter.drawPixmap(0, 0, pixmap)
        painter.end()
        self.append_log(tr("Immagine inviata in stampa: {name}").format(name=os.path.basename(path)))

    def save_annotated(self):
        if not self.current_row_data:
            return
        if self._annotated_session_id != self.current_row_data["id"] or not self._annotated_temp_path:
            return
        folder = self.current_row_data["folder_path"]
        if not folder or not os.path.isdir(folder):
            QMessageBox.warning(self, tr("Salva"), tr("La cartella della sessione non è più presente sul disco."))
            return

        method_suffix = "astrometry" if self._annotated_method == "astrometry_net" else "simbad"
        _, src_ext = os.path.splitext(self._annotated_temp_path)
        src_ext = src_ext or ".jpg"
        size_tag = "stacked16" if self._annotated_used_fits else "stacked"
        base_name = f"{size_tag}_annotated_{method_suffix}{src_ext}"
        dest = os.path.join(folder, base_name)
        stem, ext = os.path.splitext(base_name)
        counter = 1
        while os.path.exists(dest):
            dest = os.path.join(folder, f"{stem}_{counter}{ext}")
            counter += 1

        try:
            shutil.copy2(self._annotated_temp_path, dest)
        except Exception as exc:
            QMessageBox.warning(self, tr("Salva"), tr("Impossibile salvare il file: {exc}").format(exc=exc))
            return
        QMessageBox.information(self, tr("Salva"), tr("Immagine salvata come:\n{dest}").format(dest=dest))
        self.append_log(tr("Immagine con etichette salvata: {dest}").format(dest=dest))

    def _open_path(self, path):
        if path and os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QMessageBox.warning(self, tr("Percorso non trovato"),
                                 tr("Il file o la cartella non è più presente sul disco:\n{path}").format(path=path))

    def change_db_path(self):
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Percorso database"), self.db_path, tr("Database SQLite (*.db)")
        )
        if path:
            self.db.close()
            self.db_path = path
            self.db = CatalogDB(path)
            self.settings.setValue("db_path", path)
            self.reload_telescope_combo()
            self.reload_target_combo()
            self.reload_sessions_table()
            self.update_status_bar()
            self.append_log(tr("Database cambiato: {path}").format(path=path))

    def update_status_bar(self):
        s = self.db.stats()
        c = self.db.calibration_stats()
        template = tr(
            "{n_sessions} sessioni · {n_stacked} con stack · "
            "{n_raw_ok} raw OK · {n_raw_failed} raw falliti · "
            "{total_size} totali · {n_cal} frame di calibrazione"
        )
        self.status_bar.showMessage(template.format(
            n_sessions=s['n_sessions'], n_stacked=s['n_stacked'],
            n_raw_ok=s['n_raw_ok'], n_raw_failed=s['n_raw_failed'],
            total_size=human_size(s['total_size']), n_cal=c['n'],
        ))

    def open_calibration_dialog(self):
        dlg = CalibrationDialog(self.db, self.thumb_dir, self)
        dlg.exec()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        self.settings.setValue("mainwindow/geometry", self.saveGeometry())
        self.settings.setValue("mainwindow/sessions_header", self.sessions_table.horizontalHeader().saveState())
        self.settings.setValue("mainwindow/splitter", self.main_splitter.saveState())
        self.settings.setValue("mainwindow/left_splitter", self.left_splitter.saveState())
        self.settings.setValue("mainwindow/detail_splitter", self.detail_splitter.saveState())
        self.db.close()
        event.accept()


def run_gui(db_path, thumb_dir):
    app = QApplication(sys.argv)
    win = MainWindow(db_path, thumb_dir)
    # Se non c'è una geometria salvata da un avvio precedente, la finestra
    # principale si apre a tutto schermo (massimizzata) come richiesto.
    if getattr(win, "_geometry_restored", False):
        win.show()
    else:
        win.showMaximized()
    sys.exit(app.exec())
