"""
main.py - Punto di ingresso del Catalogo Sessioni Astronomiche
Dwarf II / Dwarf 3 / Dwarf Mini / Dwarf Draco.

Uso GUI (predefinito):
    python main.py

Uso da riga di comando (batch, senza GUI), utile per pianificare la
scansione automaticamente (es. Utilità di pianificazione di Windows):
    python main.py --scan "D:\\Cartelle_RAW" [--dry-run] [--no-remove-orphans]

Opzioni:
    --scan CARTELLA         Esegue la scansione della cartella indicata e termina
                            (punta a "Cartelle_RAW" o a una cartella superiore:
                            lo script cerca da solo le sottocartelle "Astronomy")
    --dry-run               Simula la scansione senza scrivere nel database
    --no-remove-orphans     Non rimuove le sessioni non più presenti sul disco
    --db PERCORSO           Percorso del file database SQLite (default: catalogo_dwarf.db
                            nella cartella dell'app)
"""

import argparse
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# Vedi la stessa nota in gui.py: con un eseguibile PyInstaller (specie
# --onefile) __file__ punta a una cartella temporanea ricreata a ogni
# avvio - la cartella dell'app è invece quella del file .exe in quel caso.
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(APP_DIR, "catalogo_dwarf.db")
THUMB_DIR = os.path.join(APP_DIR, "thumbnails")
LOG_DIR = os.path.join(APP_DIR, "logs")


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger("dwarf_catalog")
    logger.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, "dwarf_catalog.log"),
        maxBytes=2_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
    logger.addHandler(console_handler)
    return logger


def _install_crash_logging(logger):
    """Rete di sicurezza: logga anche qualunque eccezione non gestita nel
    thread principale (es. dentro uno slot Qt) prima che il programma si
    chiuda, così anche un crash nell'eseguibile compilato lascia una
    traccia in logs/dwarf_catalog.log invece di sparire senza alcun
    indizio (con --windowed non c'è una console dove leggerla altrimenti)."""
    import traceback

    def _hook(exc_type, exc_value, exc_tb):
        logger.error(
            "ECCEZIONE NON GESTITA nel thread principale:\n"
            + "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        )
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


def main():
    parser = argparse.ArgumentParser(
        description="Catalogo Sessioni Astronomiche Dwarf II / Dwarf 3 / Dwarf Mini / Dwarf Draco - "
                    "GUI e modalità batch"
    )
    parser.add_argument("--scan", metavar="CARTELLA",
                         help="Esegue la scansione da riga di comando (senza aprire la GUI)")
    parser.add_argument("--dry-run", action="store_true",
                         help="Simula la scansione senza scrivere nel database")
    parser.add_argument("--no-remove-orphans", action="store_true",
                         help="Non rimuovere le sessioni non più presenti sul disco")
    parser.add_argument("--db", metavar="PERCORSO", default=DEFAULT_DB_PATH,
                         help="Percorso del database SQLite")
    args = parser.parse_args()

    logger = setup_logging()
    _install_crash_logging(logger)
    os.makedirs(THUMB_DIR, exist_ok=True)

    if args.scan:
        # Modalità batch / riga di comando
        from db import CatalogDB
        from scanner import scan_root

        db = CatalogDB(args.db)
        stats = scan_root(
            args.scan,
            db,
            THUMB_DIR,
            dry_run=args.dry_run,
            remove_orphans=not args.no_remove_orphans,
            log_cb=None,  # già loggato internamente tramite il modulo logging
        )
        db.close()
        print(
            f"\nRiepilogo: sessioni trovate={stats.sessions_found} "
            f"nuove={stats.sessions_added} aggiornate={stats.sessions_updated} "
            f"invariate={stats.sessions_unchanged} rimosse={stats.sessions_removed} "
            f"non riconosciute={stats.unrecognized_folders} errori={stats.errors}"
        )
        sys.exit(0 if stats.errors == 0 else 1)
    else:
        # Modalità GUI
        from gui import run_gui
        run_gui(args.db, THUMB_DIR)


if __name__ == "__main__":
    main()
