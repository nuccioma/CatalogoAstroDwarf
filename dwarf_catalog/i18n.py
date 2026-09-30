"""
i18n.py - Supporto minimo italiano/inglese per l'interfaccia.

L'app parte sempre in italiano; la lingua si sceglie dal menu File > Lingua
e diventa effettiva al riavvio del programma (per semplicità e
affidabilità, invece di ritradurre "al volo" tutti i widget già creati).

tr(testo) ritorna la traduzione inglese se la lingua corrente è "en" ed
esiste una traduzione per quel testo esatto, altrimenti ritorna il testo
italiano originale invariato: è quindi sempre sicuro chiamarla, anche su
stringhe non ancora presenti nel dizionario (mancata traduzione = resta in
italiano, non un errore).

NOTA SULLO STATO DELLA TRADUZIONE: la traduzione copre l'intera interfaccia
utente: finestra principale (menu, barra degli strumenti, filtri, tabella
sessioni, pannello dettaglio/foto e relativi pulsanti), tutte le finestre
secondarie (Apri sessione, Ingrandisci, Frame di calibrazione, Posizione
osservativa, Opzioni astrometria, Informazioni su...) e i messaggi di log
prodotti durante la scansione delle cartelle. Sono lasciate volutamente in
italiano solo le voci "Tutti"/"Tutte" nei filtri e i valori tecnici salvati
nel database (es. "cali_frame", "Bias", "Dark", "Flat"), perché il codice li
confronta direttamente come testo: tradurli romperebbe il filtro.
"""

LANGUAGES = {"it": "Italiano", "en": "English"}

_current_lang = "it"


def set_language(lang):
    global _current_lang
    _current_lang = lang if lang in LANGUAGES else "it"


def get_language():
    return _current_lang


def tr(text):
    """Ritorna la traduzione di 'text' nella lingua corrente, oppure 'text'
    stesso se la lingua è italiano o se non esiste (ancora) una traduzione."""
    if _current_lang == "en":
        return _EN.get(text, text)
    return text


# Dizionario italiano -> inglese. Le chiavi sono le stringhe italiane
# esattamente come compaiono nel codice (compresi eventuali "…", accenti,
# punteggiatura): tr() cerca una corrispondenza esatta.
_EN = {
    # --- Finestra principale: titolo, menu ---
    "Catalogo Sessioni Astronomiche DWARF": "DWARF Astronomical Session Catalog",
    "&File": "&File",
    "Cambia percorso database…": "Change database path…",
    "Imposta posizione osservativa…": "Set observer location…",
    "Imposta percorso Siril (siril-cli.exe)…": "Set Siril path (siril-cli.exe)…",
    "Lingua": "Language",
    "Esci": "Exit",

    # --- Barra di stato ---
    "{n_sessions} sessioni · {n_stacked} con stack · "
    "{n_raw_ok} raw OK · {n_raw_failed} raw falliti · "
    "{total_size} totali · {n_cal} frame di calibrazione":
        "{n_sessions} sessions · {n_stacked} with stack · "
        "{n_raw_ok} raw OK · {n_raw_failed} raw failed · "
        "{total_size} total · {n_cal} calibration frames",
    "&Aiuto": "&Help",
    "Informazioni su…": "About…",

    # --- Riga cartella radice + azioni di scansione ---
    "Cartella radice:": "Root folder:",
    "Sfoglia…": "Browse…",
    "Dry-run (simula)": "Dry-run (simulate)",
    "Rimuovi sessioni eliminate": "Remove deleted sessions",
    "Scansiona ora": "Scan now",
    "Interrompi": "Stop",

    # --- Riga filtri ---
    "Da:": "From:",
    "A:": "To:",
    "Azzera filtri": "Clear filters",

    # --- Tabella sessioni ---
    "Data/Ora": "Date/Time",
    "Target": "Target",
    "Telescopio": "Telescope",
    "Modo": "Mode",
    "Filtro": "Filter",
    "Esp(s)": "Exp(s)",
    "Gain": "Gain",
    "Raw OK": "Raw OK",
    "Raw falliti": "Raw failed",
    "Stack": "Stack",
    "Modalità": "Mode",
    "Log:": "Log:",

    # --- Riga azioni selezione (condivisa: tabella sessioni e file di sessione) ---
    "Selezionati:": "Selected:",
    "Rimuovi dal catalogo": "Remove from catalog",
    "Elimina dal disco…": "Delete from disk…",
    "Rinomina…": "Rename…",
    "Sposta…": "Move…",
    "Copia…": "Copy…",

    # --- Pannello dettaglio sessione: etichette campi ---
    "Nessuna sessione selezionata": "No session selected",
    "Target:": "Target:",
    "Telescopio:": "Telescope:",
    "Modalità:": "Mode:",
    "Filtro:": "Filter:",
    "Data/ora:": "Date/time:",
    "Esposizione:": "Exposure:",
    "Gain:": "Gain:",
    "Temperatura:": "Temperature:",
    "Raw OK / falliti:": "Raw OK / failed:",
    "Dimensione:": "Size:",
    "Binning:": "Binning:",
    "Scatti (fatti/stack/da fare):": "Shots (taken/stacked/to take):",
    "Cartella:": "Folder:",
    "Oggetto (SIMBAD):": "Object (SIMBAD):",
    "Coordinate (RA/Dec):": "Coordinates (RA/Dec):",
    "RA/Dec richiesti (shotsInfo.json):": "RA/Dec requested (shotsInfo.json):",
    "Condizioni allo scatto:": "Conditions at shot time:",

    # --- Pannello dettaglio sessione: pulsanti ---
    "Apri immagine stack": "Open stack image",
    "Apri etichettata": "Open labeled image",
    "Apri cartella sessione in Esplora risorse": "Open session folder in File Explorer",
    "Apri sessione": "Open session",
    "Identifica oggetto (SIMBAD)": "Identify object (SIMBAD)",
    "Ricerca in corso…": "Searching…",
    "Astrometria (etichetta oggetti)": "Astrometry (label objects)",
    "Elaborazione…": "Processing…",
    "Stampa": "Print",
    "Salva": "Save",
    "Vedi originale": "View original",
    "Vedi etichettata": "View labeled",

    # --- Tooltip pulsanti pannello dettaglio ---
    "Apre l'immagine stack principale della sessione (stacked.jpg o, su alcuni "
    "telescopi, altro formato) con l'app associata di Windows.":
        "Opens the session's main stacked image (stacked.jpg or, on some "
        "telescopes, another format) with the associated Windows app.",
    "Apre l'immagine con le etichette astrometria nell'app Foto di Windows, per "
    "esaminarla con zoom e rotazione meglio che nell'anteprima del catalogo.":
        "Opens the image with astrometry labels in the Windows Photos app, to "
        "examine it with zoom and rotation better than in the catalog preview.",
    "Risolve astrometricamente lo stack ed etichetta sulla foto gli oggetti presenti "
    "nel campo. Metodologia a scelta ogni volta: SIMBAD (via Siril, richiede "
    "siril-cli.exe e il catalogo Gaia locale) oppure Astrometry.net (locale, dentro "
    "WSL).":
        "Astrometrically solves the stack and labels the objects present "
        "in the field on the photo. Methodology chosen each time: SIMBAD (via Siril, "
        "requires siril-cli.exe and the local Gaia catalog) or Astrometry.net (local, inside "
        "WSL).",
    "Salva l'immagine con le etichette astrometria come nuovo file nella cartella "
    "sessione (l'originale non viene toccato).":
        "Saves the image with astrometry labels as a new file in the session "
        "folder (the original is not touched).",
    "Passa dall'immagine etichettata allo stack originale (e viceversa) "
    "senza rifare l'astrometria.":
        "Switches from the labeled image to the original stack (and back) "
        "without redoing the astrometry.",

    # --- Finestra "Informazioni su..." ---
    "Informazioni su Catalogo Sessioni Astronomiche DWARF": "About DWARF Astronomical Session Catalog",
    "Catalogo Sessioni Astronomiche DWARF v. 1.0": "DWARF Astronomical Session Catalog v. 1.0",
    "Creata da Nuccio Mandarà con l'aiuto fondamentale di Claude AI.":
        "Created by Nuccio Mandarà with the essential help of Claude AI.",

    # =====================================================================
    # Finestra "Apri sessione" (SessionFilesDialog)
    # =====================================================================
    "Sessione: {label}": "Session: {label}",
    "Nome file": "File name",
    "Tipo": "Type",
    "Dimensione": "Size",
    "Stelle": "Stars",
    "FWHM(px)": "FWHM(px)",
    "Rumore fondo": "Background noise",
    "Scarta se stelle <": "Discard if stars <",
    "o FWHM >": "or FWHM >",
    "o rumore >": "or noise >",
    "Seleziona scarti": "Select rejects",
    "Deseleziona tutto": "Deselect all",
    "I valori di stelle/FWHM sono calcolati con un algoritmo proprio dell'app: "
    "utili per confrontare i file tra loro nella stessa sessione e scartare i peggiori, "
    "ma il valore assoluto e l'ordine dei singoli file possono differire leggermente da "
    "quelli di altri programmi (DeepSkyStacker, Siril, ecc.), che misurano con algoritmi diversi.":
        "Star count/FWHM values are computed with the app's own algorithm: "
        "useful to compare files against each other within the same session and discard the worst ones, "
        "but the absolute value and the ranking of individual files may differ slightly from "
        "other programs (DeepSkyStacker, Siril, etc.), which measure with different algorithms.",
    "Ingrandisci…": "Enlarge…",
    "Apre il file selezionato in una finestra grande, con zoom, per vederne i particolari.":
        "Opens the selected file in a large window, with zoom, to see its details.",
    "Header FITS:": "FITS header:",
    "(nessun header — seleziona un file FITS)": "(no header — select a FITS file)",
    "Chiudi": "Close",
    "Errore": "Error",
    "Impossibile leggere la cartella:\n{exc}": "Could not read the folder:\n{exc}",
    "FITS fallito": "Failed FITS",
    "Immagine": "Image",
    "Altro": "Other",
    "{n} file": "{n} files",
    "File non più presente sul disco": "File no longer present on disk",
    "Lettura del file FITS in corso…": "Reading FITS file…",
    "Impossibile visualizzare l'immagine FITS": "Could not display the FITS image",
    "(header non disponibile)": "(header not available)",
    "Impossibile aprire l'immagine": "Could not open the image",
    "Nessuna anteprima disponibile per questo tipo di file": "No preview available for this file type",
    "Elimina dal disco": "Delete from disk",
    "\n… e altri {n}": "\n… and {n} more",
    "ATTENZIONE: eliminare DEFINITIVAMENTE {n} file dal disco?\n"
    "Questa operazione non è reversibile.\n\n{names}{more}":
        "WARNING: PERMANENTLY delete {n} files from disk?\n"
        "This operation cannot be undone.\n\n{names}{more}",
    "Alcuni errori": "Some errors",
    "Errori durante l'eliminazione:\n": "Errors during deletion:\n",
    "Rinomina file": "Rename file",
    "Nuovo nome file:": "New file name:",
    "Rinominare '{old}' in '{new}'?": "Rename '{old}' to '{new}'?",
    "Rinomina non riuscita:\n{exc}": "Rename failed:\n{exc}",
    "Cartella di destinazione": "Destination folder",
    "Sposta file": "Move files",
    "Spostare {n} file in:\n{dest}?": "Move {n} files to:\n{dest}?",
    "Errori durante lo spostamento:\n": "Errors during move:\n",
    "Spostati {n} file in {dest}": "Moved {n} files to {dest}",
    "Copia file": "Copy files",
    "Copiare {n} file in:\n{dest}?": "Copy {n} files to:\n{dest}?",
    "Errori durante la copia:\n": "Errors during copy:\n",
    "Copiati {n} file in {dest}": "Copied {n} files to {dest}",
    "Analisi qualità": "Quality analysis",
    "Nessun file FITS in questa sessione.": "No FITS files in this session.",
    "Analisi qualità: {current}/{total} — {name}": "Quality analysis: {current}/{total} — {name}",
    "{n_files} file — analisi qualità completata su {n_raw} raw":
        "{n_files} files — quality analysis completed on {n_raw} raw files",
    "Nessun dato di qualità disponibile: esegui prima "
    "'Analizza qualità raw'.":
        "No quality data available: run "
        "'Analyze raw quality' first.",
    "{n} file selezionati come scarti": "{n} files selected as rejects",

    # =====================================================================
    # Finestra "Ingrandisci" (ImageZoomDialog)
    # =====================================================================
    "Ingrandisci: {name}": "Enlarge: {name}",
    "Adatta alla finestra": "Fit to window",
    "Dimensione reale (100%)": "Actual size (100%)",
    "Caricamento…": "Loading…",
    "Impossibile visualizzare l'immagine": "Could not display the image",

    # =====================================================================
    # Finestra "Frame di calibrazione" (CalibrationDialog)
    # =====================================================================
    "Frame di calibrazione (Bias / Dark / Flat)": "Calibration frames (Bias / Dark / Flat)",
    "Sorgente:": "Source:",
    "Sorgente": "Source",
    "Camera": "Camera",
    "Binning": "Binning",
    "Esp(s)": "Exp(s)",
    "Temp(°C)": "Temp(°C)",
    "IR / stack / n.raw": "IR / stack / raw count",
    "Percorso": "Path",
    "Apri cartella sessione": "Open session folder",
    "Cartella non trovata": "Folder not found",
    "La cartella non è più presente sul disco:\n{folder}": "The folder is no longer present on disk:\n{folder}",
    "{n} elementi": "{n} items",
    "Rimuovi dal catalogo": "Remove from catalog",
    "Rimuovere {n} elemento/i dal catalogo?\n"
    "(i file sul disco NON vengono toccati)\n\n{names}{more}":
        "Remove {n} item(s) from the catalog?\n"
        "(files on disk are NOT touched)\n\n{names}{more}",
    "ATTENZIONE: eliminare DEFINITIVAMENTE {n} elemento/i dal disco "
    "(file o intere cartelle) e dal catalogo?\nQuesta operazione non è "
    "reversibile.\n\n{names}{more}":
        "WARNING: PERMANENTLY delete {n} item(s) from disk "
        "(files or entire folders) and from the catalog?\nThis operation cannot be "
        "undone.\n\n{names}{more}",
    "Rinomina": "Rename",
    "Nuovo nome:": "New name:",
    "Sposta": "Move",
    "Spostare {n} elemento/i in:\n{dest}?": "Move {n} item(s) to:\n{dest}?",
    "Copia": "Copy",
    "Copiare {n} elemento/i in:\n{dest}?": "Copy {n} item(s) to:\n{dest}?",
    "Copiati {n} elementi in {dest}": "Copied {n} items to {dest}",

    # =====================================================================
    # Finestra "Posizione osservativa" (ObserverLocationDialog)
    # =====================================================================
    "Posizione osservativa": "Observer location",
    "Latitudine (°, positiva a Nord):": "Latitude (°, positive North):",
    "Longitudine (°, positiva a Est):": "Longitude (°, positive East):",
    "Altitudine (m, opzionale):": "Altitude (m, optional):",
    "Annulla": "Cancel",

    # =====================================================================
    # Finestra "Opzioni astrometria" (AstrometryOptionsDialog)
    # =====================================================================
    "Opzioni astrometria": "Astrometry options",
    "Questa sessione ha sia il FITS-16 che il jpg dello stack. Su quale "
    "immagine risolvere ed etichettare?":
        "This session has both the FITS-16 and the jpg of the stack. Which "
        "image should be solved and labeled?",
    "FITS ({label}) — qualità migliore": "FITS ({label}) — better quality",
    "JPG ({label})": "JPG ({label})",
    "Metodologia:": "Methodology:",
    "SIMBAD (risoluzione con Siril, locale)": "SIMBAD (solving with Siril, local)",
    "Risolve con Siril (catalogo Gaia locale, offline) e cerca su SIMBAD "
    "(richiede Internet) gli oggetti notevoli Messier/NGC/IC del campo, "
    "disegnando le etichette con questo programma.":
        "Solves with Siril (local Gaia catalog, offline) and searches SIMBAD "
        "(requires Internet) for notable Messier/NGC/IC objects in the field, "
        "drawing the labels with this program.",
    "Astrometry.net (locale, dentro WSL)": "Astrometry.net (local, inside WSL)",
    "Risolve ed etichetta con Astrometry.net installato dentro WSL (comando "
    "solve-field): funziona offline (richiede gli indici stellari installati "
    "in WSL). È Astrometry.net stesso a produrre l'immagine annotata con i "
    "propri cataloghi - non viene interrogato SIMBAD.":
        "Solves and labels with Astrometry.net installed inside WSL (solve-field "
        "command): works offline (requires the star index files installed "
        "in WSL). Astrometry.net itself produces the annotated image with its "
        "own catalogs - SIMBAD is not queried.",
    "Con SIMBAD, gli oggetti notevoli presenti nel campo (altre galassie, "
    "nebulose, ammassi...) vengono sempre cercati su SIMBAD.":
        "With SIMBAD, notable objects present in the field (other galaxies, "
        "nebulae, clusters...) are always searched on SIMBAD.",
    "Includi anche le stelle luminose con un nome noto (es. Polaris, alf And...)":
        "Also include bright stars with a known name (e.g. Polaris, alf And...)",
    "Cerca su SIMBAD le stelle del campo che hanno un nome proprio, una "
    "designazione di Bayer/Flamsteed o una sigla HD - non stelle qualunque "
    "identificate solo da un codice numerico. Si applica solo con la "
    "metodologia SIMBAD: Astrometry.net include già di suo, nella propria "
    "annotazione, le stelle con nome che riconosce.":
        "Searches SIMBAD for field stars that have a proper name, a "
        "Bayer/Flamsteed designation or an HD number - not ordinary stars "
        "identified only by a numeric code. Only applies with the "
        "SIMBAD methodology: Astrometry.net already includes, in its own "
        "annotation, the named stars it recognizes.",
    "Entrambe le metodologie risolvono l'immagine offline (Siril / "
    "Astrometry.net locale in WSL); la ricerca SIMBAD (oggetti e "
    "stelle) richiede invece una connessione Internet.":
        "Both methodologies solve the image offline (Siril / "
        "local Astrometry.net in WSL); the SIMBAD search (objects and "
        "stars) instead requires an Internet connection.",

    # =====================================================================
    # MainWindow: scansione, anteprima, azioni sulle sessioni
    # =====================================================================
    "Avvio scansione: {root}": "Starting scan: {root}",
    "Elaborazione: {message}": "Processing: {message}",
    "Terminato. Sessioni trovate: {found}, nuove: {added}, "
    "aggiornate: {updated}, invariate: {unchanged}, "
    "rimosse: {removed}, non riconosciute: {unrecognized}, "
    "errori: {errors}":
        "Done. Sessions found: {found}, new: {added}, "
        "updated: {updated}, unchanged: {unchanged}, "
        "removed: {removed}, unrecognized: {unrecognized}, "
        "errors: {errors}",
    "{ok} OK / {failed} falliti": "{ok} OK / {failed} failed",
    "La cartella della sessione non è più presente sul disco:\n{folder}":
        "The session folder is no longer present on disk:\n{folder}",
    "Rimuovere {n} sessione/i dal catalogo?\n"
    "(i file sul disco NON vengono toccati)\n\n{names}{more}":
        "Remove {n} session(s) from the catalog?\n"
        "(files on disk are NOT touched)\n\n{names}{more}",
    "Rimosse {n} sessioni dal catalogo (file su disco non toccati).":
        "Removed {n} sessions from the catalog (files on disk not touched).",
    "ATTENZIONE: eliminare DEFINITIVAMENTE {n} cartella/e di sessione "
    "dal disco (con tutti i raw e gli stacked contenuti) e dal catalogo?\n"
    "Questa operazione non è reversibile.\n\n{names}{more}":
        "WARNING: PERMANENTLY delete {n} session folder(s) "
        "from disk (with all raw and stacked files inside) and from the catalog?\n"
        "This operation cannot be undone.\n\n{names}{more}",
    "Eliminate dal disco {n} sessioni.": "Deleted {n} sessions from disk.",
    "Rinomina sessione": "Rename session",
    "Nuovo nome cartella:": "New folder name:",
    "Rinominare la cartella:\n{old_path}\nin '{new}'?": "Rename the folder:\n{old_path}\nto '{new}'?",
    "Sessione rinominata: {old} -> {new}": "Session renamed: {old} -> {new}",
    "Sposta sessioni": "Move sessions",
    "Spostare {n} cartella/e di sessione in:\n{dest}?": "Move {n} session folder(s) to:\n{dest}?",
    "Spostate {n} sessioni in {dest}.": "Moved {n} sessions to {dest}.",
    "Copia sessioni": "Copy sessions",
    "Copiare {n} cartella/e di sessione in:\n{dest}?\n"
    "(la copia non viene aggiunta al catalogo: esegui una scansione di "
    "quella cartella se vuoi catalogarla)":
        "Copy {n} session folder(s) to:\n{dest}?\n"
        "(the copy is not added to the catalog: run a scan of "
        "that folder if you want to catalog it)",
    "Copiate {n} sessioni in {dest}.": "Copied {n} sessions to {dest}.",

    "cost. {c}": "const. {c}",
    "mag {m:.1f}": "mag {m:.1f}",
    "non identificato": "not identified",
    " (az {a:.0f}°)": " (az {a:.0f}°)",
    "altezza {h:.0f}°{az_bit}": "altitude {h:.0f}°{az_bit}",
    "Luna {pct:.0f}% a {sep:.0f}°": "Moon {pct:.0f}% at {sep:.0f}°",
    "Valori non validi": "Invalid values",
    "Inserisci coordinate numeriche valide.": "Enter valid numeric coordinates.",
    "Identifica oggetto": "Identify object",
    "Questa sessione non ha un nome target.": "This session has no target name.",
    "Oggetto identificato: {name}": "Object identified: {name}",

    "Individua siril-cli.exe": "Locate siril-cli.exe",
    "siril-cli.exe;;Tutti i file (*)": "siril-cli.exe;;All files (*)",
    "Astrometria": "Astrometry",
    "Nessuno stack disponibile per questa sessione.": "No stack available for this session.",
    "Non trovo siril-cli.exe. Indica il percorso dell'eseguibile.":
        "Can't find siril-cli.exe. Please indicate the executable's path.",
    "Astrometria ({method}): risoluzione su {solve_name}, "
    "etichette su {display_name}…":
        "Astrometry ({method}): solving on {solve_name}, "
        "labels on {display_name}…",
    "Astrometria (Astrometry.net) completata: campo risolto, "
    "{n} oggetti nel campo.":
        "Astrometry (Astrometry.net) completed: field solved, "
        "{n} objects in the field.",
    "Astrometria (SIMBAD) completata: {n} oggetti "
    "etichettati (notevoli: {n_notable}":
        "Astrometry (SIMBAD) completed: {n} objects "
        "labeled (notable: {n_notable}",
    ", stelle luminose: {n_stars}": ", bright stars: {n_stars}",
    "Etichettatura completata, con alcuni avvisi:\n\n": "Labeling completed, with some warnings:\n\n",
    "Stampa": "Print",
    "Nessuna immagine da stampare.": "No image to print.",
    "Impossibile caricare l'immagine da stampare.": "Could not load the image to print.",
    "Immagine inviata in stampa: {name}": "Image sent to print: {name}",
    "Salva": "Save",
    "La cartella della sessione non è più presente sul disco.": "The session folder is no longer present on disk.",
    "Impossibile salvare il file: {exc}": "Could not save the file: {exc}",
    "Immagine salvata come:\n{dest}": "Image saved as:\n{dest}",
    "Immagine con etichette salvata: {dest}": "Image with labels saved: {dest}",
    "Percorso non trovato": "Path not found",
    "Il file o la cartella non è più presente sul disco:\n{path}":
        "The file or folder is no longer present on disk:\n{path}",
    "Percorso database": "Database path",
    "Database SQLite (*.db)": "SQLite database (*.db)",
    "Database cambiato: {path}": "Database changed: {path}",

    # =====================================================================
    # AstrometryWorker: messaggi di avanzamento (mostrati nel Log)
    # =====================================================================
    "Astrometria: ricerca posizione approssimativa del target…":
        "Astrometry: searching approximate target position…",
    "Astrometria (Astrometry.net locale via WSL): risoluzione ed "
    "etichettatura dell'immagine in corso…":
        "Astrometry (local Astrometry.net via WSL): solving and "
        "labeling the image…",
    "Astrometria: risoluzione dell'immagine con Siril in corso…":
        "Astrometry: solving the image with Siril…",
    "Astrometria: preparazione immagine dal FITS…": "Astrometry: preparing image from FITS…",
    "Astrometria: ricerca oggetti del campo su SIMBAD…": "Astrometry: searching field objects on SIMBAD…",
    "Astrometria: ricerca stelle luminose con nome su SIMBAD…":
        "Astrometry: searching named bright stars on SIMBAD…",
    "Astrometria: disegno delle etichette…": "Astrometry: drawing labels…",
    "Impossibile ottenere gli oggetti del campo inquadrato.": "Could not get the objects in the framed field.",
    "Oggetti SIMBAD non disponibili: {err}": "SIMBAD objects not available: {err}",
    "Stelle luminose non disponibili: {err}": "Bright stars not available: {err}",
    "sì": "yes",
    "no": "no",

    # =====================================================================
    # gui.py: voci mancanti aggiunte in fase di completamento traduzione
    # =====================================================================
    "Analizza qualità raw": "Analyze raw quality",
    "Seleziona un file per l'anteprima": "Select a file for the preview",
    "Tipo:": "Type:",
    "Frame di calibrazione…": "Calibration frame…",
    "Cartella non valida": "Invalid folder",
    "Seleziona una cartella radice valida prima di scansionare.":
        "Select a valid root folder before scanning.",
    "Nessuno stack disponibile per questa sessione": "No stack available for this session",
    "\n… e altre {n}": "\n… and {n} more",

    # =====================================================================
    # scanner.py: messaggi di log della scansione (mostrati nel Log)
    # =====================================================================
    "ERRORE nel leggere '{path}': {exc}": "ERROR reading '{path}': {exc}",
    "AVVISO: {n} file non riconosciuti in '{path}': {names}":
        "WARNING: {n} unrecognized files in '{path}': {names}",
    "nuova": "new",
    "aggiornata": "updated",
    "nuovo": "new",
    "aggiornato": "updated",
    "[DRY RUN] Sessione {action}: {name} | telescopio={telescope} | "
    "modo={mode} | target={target} | "
    "filtro={filter} | temp={temp} | raw OK={ok} | "
    "raw falliti={failed} | "
    "stack={stack}":
        "[DRY RUN] Session {action}: {name} | telescope={telescope} | "
        "mode={mode} | target={target} | "
        "filter={filter} | temp={temp} | raw OK={ok} | "
        "raw failed={failed} | "
        "stack={stack}",
    "AVVISO: cartella non riconosciuta in cali_frame, ignorata: {path}":
        "WARNING: unrecognized folder in cali_frame, ignored: {path}",
    "AVVISO: cartella camera non riconosciuta in cali_frame, ignorata: {path}":
        "WARNING: unrecognized camera folder in cali_frame, ignored: {path}",
    "AVVISO: file di calibrazione non riconosciuto, ignorato: {path}":
        "WARNING: unrecognized calibration file, ignored: {path}",
    "[DRY RUN] Calibrazione {action}: {frame_type}/{camera} {name}":
        "[DRY RUN] Calibration {action}: {frame_type}/{camera} {name}",
    "AVVISO: cartella non riconosciuta in DWARF_DARK, ignorata: {path}":
        "WARNING: unrecognized folder in DWARF_DARK, ignored: {path}",
    "[DRY RUN] Sessione dark {action}: {name} | camera={camera} | "
    "raw={raw} | temp media={temp}":
        "[DRY RUN] Dark session {action}: {name} | camera={camera} | "
        "raw={raw} | average temp={temp}",
    "Inizio scansione di: {root}": "Starting scan of: {root}",
    "ERRORE: la cartella '{path}' non esiste.": "ERROR: the folder '{path}' does not exist.",
    "Trovate {n} cartelle 'Astronomy' (telescopi: {list}).":
        "Found {n} 'Astronomy' folders (telescopes: {list}).",
    "nessuno": "none",
    "Scansione interrotta dall'utente.": "Scan stopped by user.",
    "AVVISO: cartella in Restacked non riconosciuta come sessione, ignorata: "
    "{path}":
        "WARNING: unrecognized folder in Restacked, not treated as a session, ignored: "
        "{path}",
    "AVVISO: cartella in STARTRAILS non riconosciuta come sessione, ignorata: "
    "{path}":
        "WARNING: unrecognized folder in STARTRAILS, not treated as a session, ignored: "
        "{path}",
    "AVVISO: cartella in Astronomy non riconosciuta come sessione, ignorata: "
    "{path}":
        "WARNING: unrecognized folder in Astronomy, not treated as a session, ignored: "
        "{path}",
    "Rimozione di {n} sessioni non più presenti sul disco.":
        "Removing {n} sessions no longer present on disk.",
    "Rimozione di {n} frame di calibrazione non più presenti sul disco.":
        "Removing {n} calibration frames no longer present on disk.",
    "Scansione completata. Sessioni trovate: {found}, "
    "nuove: {added}, aggiornate: {updated}, "
    "invariate: {unchanged}, rimosse: {removed}, "
    "cartelle non riconosciute: {unrecognized}, errori: {errors} | "
    "Calibrazione: nuovi={cali_added}, aggiornati={cali_updated}, "
    "invariati={cali_unchanged}, rimossi={cali_removed}, "
    "non riconosciuti={cali_unrecognized}":
        "Scan complete. Sessions found: {found}, "
        "new: {added}, updated: {updated}, "
        "unchanged: {unchanged}, removed: {removed}, "
        "unrecognized folders: {unrecognized}, errors: {errors} | "
        "Calibration: new={cali_added}, updated={cali_updated}, "
        "unchanged={cali_unchanged}, removed={cali_removed}, "
        "unrecognized={cali_unrecognized}",

    # =====================================================================
    # dwarf_astrometry.py: messaggi d'errore/avanzamento dell'astrometria
    # =====================================================================
    "nessuna risposta dal server entro {timeout_s} secondi":
        "no response from the server within {timeout_s} seconds",
    "Non trovo siril-cli.exe nel percorso configurato. Imposta il "
    "percorso corretto da File → Imposta percorso Siril…":
        "Can't find siril-cli.exe at the configured path. Set the "
        "correct path from File → Set Siril path…",
    "File immagine non trovato: {path}": "Image file not found: {path}",
    "Per l'astrometria serve la libreria 'astropy'.": "Astrometry requires the 'astropy' library.",
    "Siril non ha risposto entro il tempo massimo previsto ({timeout}s): "
    "risoluzione astrometrica interrotta.":
        "Siril did not respond within the maximum time allowed ({timeout}s): "
        "astrometric resolution stopped.",
    "Impossibile avviare Siril: {exc}": "Could not start Siril: {exc}",
    "Siril non ha una posizione approssimativa da cui partire (il file non "
    "ha un header con il puntamento, e non è stata trovata una posizione nota "
    "per il target). Prova a identificare prima l'oggetto con \"Identifica "
    "oggetto (SIMBAD)\", oppure usa il FITS.{detail_bit}":
        "Siril has no approximate starting position (the file has no "
        "pointing header, and no known position was found "
        "for the target). Try identifying the object first with \"Identify "
        "object (SIMBAD)\", or use the FITS.{detail_bit}",
    "Siril non conosce la dimensione del pixel del sensore e la focale usate "
    "per questa immagine: informazioni che un jpg semplice non porta con sé "
    "(un FITS della sessione di solito le ha). Usa il FITS, se disponibile.{detail_bit}":
        "Siril does not know the sensor pixel size and focal length used "
        "for this image: information a plain jpg doesn't carry "
        "(a FITS from the session usually has it). Use the FITS, if available.{detail_bit}",
    "Siril non è riuscito a risolvere l'immagine (nessuna corrispondenza "
    "trovata con il catalogo). Verifica che il catalogo Gaia locale sia "
    "installato in Siril e che l'immagine mostri un campo stellare leggibile.{detail_bit}":
        "Siril could not solve the image (no match "
        "found with the catalog). Check that the local Gaia catalog is "
        "installed in Siril and that the image shows a readable star field.{detail_bit}",
    "Il file risolto da Siril non contiene una soluzione WCS valida.":
        "The file solved by Siril does not contain a valid WCS solution.",
    "Il file risolto da Siril non riporta le dimensioni dell'immagine.":
        "The file solved by Siril does not report the image dimensions.",
    "Impossibile leggere la soluzione astrometrica: {exc}": "Could not read the astrometric solution: {exc}",
    "Per cercare gli oggetti nel campo serve la libreria 'astroquery'.":
        "Searching for objects in the field requires the 'astroquery' library.",
    "Il server SIMBAD non ha risposto entro il tempo massimo ({exc}); "
    "potrebbe essere molto carico. Riprova più tardi.":
        "The SIMBAD server did not respond within the maximum time ({exc}); "
        "it may be very busy. Try again later.",
    "Interrogazione SIMBAD non riuscita (verifica la connessione Internet): {exc}":
        "SIMBAD query failed (check your Internet connection): {exc}",
    "Per cercare le stelle nel campo serve la libreria 'astroquery'.":
        "Searching for stars in the field requires the 'astroquery' library.",
    "Per elaborare il FITS servono le librerie 'astropy' e 'Pillow'.":
        "Processing the FITS requires the 'astropy' and 'Pillow' libraries.",
    "Il file FITS non contiene dati immagine.": "The FITS file contains no image data.",
    "Formato dati FITS non supportato per l'anteprima.": "FITS data format not supported for the preview.",
    "Il file FITS non contiene valori validi.": "The FITS file contains no valid values.",
    "Impossibile generare l'immagine dal FITS: {exc}": "Could not generate the image from the FITS: {exc}",
    "Per disegnare le etichette serve la libreria 'Pillow'.": "Drawing the labels requires the 'Pillow' library.",
    "Impossibile generare l'immagine con le etichette: {exc}": "Could not generate the labeled image: {exc}",
    "Non trovo wsl.exe: il Sottosistema Windows per Linux (WSL) non "
    "risulta installato su questo PC.":
        "Can't find wsl.exe: the Windows Subsystem for Linux (WSL) does not "
        "appear to be installed on this PC.",
    "WSL non ha risposto in tempo utile.": "WSL did not respond in time.",
    "Impossibile avviare WSL: {exc}": "Could not start WSL: {exc}",
    "Impossibile tradurre il percorso WSL in percorso Windows.{detail_bit}":
        "Could not translate the WSL path to a Windows path.{detail_bit}",
    "Astrometria (Astrometry.net locale): avvio di solve-field dentro WSL…":
        "Astrometry (local Astrometry.net): starting solve-field inside WSL…",
    "Astrometria (Astrometry.net locale): recupero dei risultati da WSL…":
        "Astrometry (local Astrometry.net): retrieving results from WSL…",
    "Astrometry.net non ha risolto entro il tempo massimo previsto "
    "({timeout}s).":
        "Astrometry.net did not solve within the maximum time allowed "
        "({timeout}s).",
    "'solve-field' non è installato dentro WSL. Da terminale Ubuntu: "
    "sudo apt install astrometry.net astrometry-data-2mass-08-19 "
    "astrometry-data-tycho2":
        "'solve-field' is not installed inside WSL. From an Ubuntu terminal: "
        "sudo apt install astrometry.net astrometry-data-2mass-08-19 "
        "astrometry-data-tycho2",
    "Astrometry.net non è riuscito a risolvere l'immagine (nessuna "
    "corrispondenza trovata nei cataloghi installati in WSL). Verifica "
    "di avere installato indici sufficienti per il campo di questa foto "
    "(vedi 'astrometry-data-2mass-08-19'/'astrometry-data-tycho2').{detail_bit}":
        "Astrometry.net could not solve the image (no "
        "match found in the catalogs installed in WSL). Check "
        "that you have installed enough indexes for this photo's field "
        "(see 'astrometry-data-2mass-08-19'/'astrometry-data-tycho2').{detail_bit}",
    "Astrometry.net ha risolto l'immagine ma non ha generato il grafico "
    "annotato (-ngc.png). Verifica l'installazione di WSL.":
        "Astrometry.net solved the image but did not generate the "
        "annotated plot (-ngc.png). Check your WSL installation.",
    "Impossibile copiare l'immagine annotata da WSL: {exc}":
        "Could not copy the annotated image from WSL: {exc}",

    # =====================================================================
    # astro_extra.py: identificazione oggetto, condizioni osservative,
    # controllo qualità raw
    # =====================================================================
    "Nessun nome target per questa sessione.": "No target name for this session.",
    "Per identificare l'oggetto serve la libreria 'astropy'.":
        "Identifying the object requires the 'astropy' library.",
    "Per identificare l'oggetto serve la libreria 'astroquery' "
    "(pip install astroquery).":
        "Identifying the object requires the 'astroquery' library "
        "(pip install astroquery).",
    "Nessun oggetto trovato per '{name}'. Verifica il nome (es. "
    "'M 31' oppure 'M31') e la connessione Internet.{detail}":
        "No object found for '{name}'. Check the name (e.g. "
        "'M 31' or 'M31') and your Internet connection.{detail}",
    "Coordinate dell'oggetto non disponibili (identifica prima l'oggetto).":
        "Object coordinates not available (identify the object first).",
    "Posizione dell'osservatore non configurata.": "Observer position not configured.",
    "Data/ora della sessione non disponibile.": "Session date/time not available.",
    "Per le condizioni osservative serve la libreria 'astropy'.":
        "Observing conditions require the 'astropy' library.",
    "Impossibile calcolare le condizioni osservative: {exc}":
        "Could not compute observing conditions: {exc}",
    "Per il controllo di qualità serve la libreria 'astropy'.":
        "Quality check requires the 'astropy' library.",
    "Impossibile leggere il file FITS: {exc}": "Could not read the FITS file: {exc}",
    "Il file FITS non contiene dati immagine.": "The FITS file contains no image data.",
    "Impossibile elaborare i dati immagine: {exc}": "Could not process the image data: {exc}",
    "Impossibile calcolare le statistiche di sfondo: {exc}": "Could not compute background statistics: {exc}",

    # =====================================================================
    # file_ops.py: operazioni su file/cartelle (elimina/rinomina/sposta/copia)
    # =====================================================================
    "Percorso non trovato: {path}": "Path not found: {path}",
    "Il nuovo nome non può essere vuoto.": "The new name cannot be empty.",
    "Il nuovo nome non può contenere separatori di percorso.":
        "The new name cannot contain path separators.",
    "Esiste già un elemento chiamato '{name}' in quella cartella.":
        "An item named '{name}' already exists in that folder.",
    "La cartella di destinazione non esiste: {dest}": "The destination folder does not exist: {dest}",
    "Esiste già un elemento chiamato '{name}' nella destinazione.":
        "An item named '{name}' already exists at the destination.",

    # =====================================================================
    # fits_viewer.py: anteprima FITS nella finestra "Apri sessione"
    # =====================================================================
    "Per visualizzare i file FITS è necessario installare 'astropy' "
    "(pip install astropy).":
        "Viewing FITS files requires installing 'astropy' "
        "(pip install astropy).",
    "Il file FITS non contiene dati immagine (solo header).":
        "The FITS file contains no image data (header only).",
    "Impossibile generare un'anteprima dai dati immagine del FITS.":
        "Could not generate a preview from the FITS image data.",

    # =====================================================================
    # gui.py: rete di sicurezza contro eccezioni impreviste nei thread
    # =====================================================================
    "Errore imprevisto durante l'astrometria: {exc}": "Unexpected error during astrometry: {exc}",
    "ERRORE imprevisto durante la scansione: {exc}": "Unexpected ERROR during the scan: {exc}",
    "Errore imprevisto durante l'identificazione: {exc}": "Unexpected error during identification: {exc}",

    # =====================================================================
    # gui.py: voce "tutti/e" dei filtri a tendina (tradotta ma usata anche
    # come valore sentinella nel codice di filtro - vedi commento in
    # _build_ui e reload_sessions_table/CalibrationDialog.reload)
    # =====================================================================
    "Tutti": "All",
    "Tutte": "All",
}
