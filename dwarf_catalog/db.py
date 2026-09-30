"""
db.py - Gestione del database SQLite per il catalogo sessioni astronomiche
dei telescopi Dwarf II / Dwarf 3 / Dwarf Mini / Dwarf Draco.
"""

import sqlite3
import datetime
import threading

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_path         TEXT UNIQUE NOT NULL,
    category            TEXT NOT NULL DEFAULT 'astronomy',
    telescope           TEXT NOT NULL DEFAULT 'Sconosciuto',
    mode                TEXT,
    target              TEXT,
    filter              TEXT,
    exposure            REAL,
    gain                INTEGER,
    temperature         REAL,
    session_datetime    TEXT,
    session_date        TEXT,
    raw_ok_count        INTEGER NOT NULL DEFAULT 0,
    raw_failed_count    INTEGER NOT NULL DEFAULT 0,
    stacked_jpg_path    TEXT,
    stacked_png_path    TEXT,
    stacked_fits_path   TEXT,
    thumbnail_path      TEXT,
    total_size          INTEGER NOT NULL DEFAULT 0,
    unrecognized_count  INTEGER NOT NULL DEFAULT 0,
    dir_mtime           TEXT,
    file_count          INTEGER NOT NULL DEFAULT 0,
    first_scanned       TEXT,
    last_scanned        TEXT
);

CREATE TABLE IF NOT EXISTS calibration (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    telescope          TEXT,
    source             TEXT NOT NULL,      -- 'cali_frame' | 'dwarf_dark'
    frame_type         TEXT,               -- 'Bias' | 'Dark' | 'Flat'
    camera             TEXT,               -- 'TELE' | 'WIDE'
    gain               INTEGER,
    bin                INTEGER,
    exposure           REAL,
    ir                 INTEGER,
    temperature        REAL,
    stack_count        INTEGER,
    raw_count          INTEGER,
    session_datetime   TEXT,
    session_date       TEXT,
    record_path        TEXT UNIQUE NOT NULL,
    dir_mtime          TEXT,
    file_count         INTEGER,
    total_size         INTEGER NOT NULL DEFAULT 0,
    first_scanned      TEXT,
    last_scanned       TEXT
);

CREATE TABLE IF NOT EXISTS scan_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS raw_quality (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id         INTEGER NOT NULL,
    file_path          TEXT UNIQUE NOT NULL,
    file_name          TEXT,
    star_count         INTEGER,
    fwhm_px            REAL,
    background_mean    REAL,
    background_noise   REAL,
    analyzed_at        TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_target ON sessions(target);
CREATE INDEX IF NOT EXISTS idx_sessions_date ON sessions(session_date);
CREATE INDEX IF NOT EXISTS idx_sessions_telescope ON sessions(telescope);
CREATE INDEX IF NOT EXISTS idx_calibration_telescope ON calibration(telescope);
CREATE INDEX IF NOT EXISTS idx_calibration_type ON calibration(frame_type);
CREATE INDEX IF NOT EXISTS idx_raw_quality_session ON raw_quality(session_id);
"""

# Colonne aggiunte dopo la prima versione dello schema: su un database
# esistente vengono aggiunte al volo con ALTER TABLE, senza perdere i dati
# già catalogati.
MIGRATION_COLUMNS = [
    ("filter", "TEXT"),
    ("temperature", "REAL"),
    # Identificazione oggetto (SIMBAD) e condizioni osservative (astropy)
    ("object_type", "TEXT"),
    ("object_constellation", "TEXT"),
    ("object_magnitude", "REAL"),
    ("object_name_resolved", "TEXT"),
    ("ra_deg", "REAL"),
    ("dec_deg", "REAL"),
    ("object_lookup_time", "TEXT"),
    ("altitude_deg", "REAL"),
    ("azimuth_deg", "REAL"),
    ("moon_phase_pct", "REAL"),
    ("moon_separation_deg", "REAL"),
    # Stack ad alta risoluzione in formato TIFF (alcuni telescopi, es. Dwarf
    # Mini / Dwarf Draco, possono salvarlo al posto del PNG/FITS).
    ("stacked_tiff_path", "TEXT"),
    # Dati letti da shotsInfo.json (quando presente nella cartella sessione):
    # informazioni aggiuntive non ricavabili dal nome della cartella/dei file.
    ("shots_binning", "TEXT"),
    ("shots_ra", "TEXT"),
    ("shots_dec", "TEXT"),
    ("shots_taken", "INTEGER"),
    ("shots_stacked", "INTEGER"),
    ("shots_to_take", "INTEGER"),
    ("shots_temp_min", "REAL"),
    ("shots_temp_max", "REAL"),
]


class CatalogDB:
    """Wrapper thread-safe (una connessione per thread) attorno al database SQLite."""

    def __init__(self, db_path):
        self.db_path = db_path
        self._local = threading.local()
        conn = self._connect()
        conn.executescript(SCHEMA)
        conn.commit()
        self._migrate(conn)

    def _migrate(self, conn):
        existing_cols = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)")}
        changed = False
        for col, coltype in MIGRATION_COLUMNS:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} {coltype}")
                changed = True
        if changed:
            conn.commit()

    def _connect(self):
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return self._local.conn

    @property
    def conn(self):
        return self._connect()

    def close(self):
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            del self._local.conn

    # ------------------------------------------------------------------
    def get_session_by_path(self, folder_path):
        return self.conn.execute(
            "SELECT * FROM sessions WHERE folder_path = ?", (folder_path,)
        ).fetchone()

    def upsert_session(self, folder_path, telescope, mode, target, exposure, gain,
                        session_datetime, session_date, raw_ok_count, raw_failed_count,
                        stacked_jpg_path, stacked_png_path, stacked_fits_path,
                        thumbnail_path, total_size, unrecognized_count, dir_mtime,
                        file_count, filter_name=None, temperature=None, category="astronomy",
                        stacked_tiff_path=None, shots_binning=None, shots_ra=None, shots_dec=None,
                        shots_taken=None, shots_stacked=None, shots_to_take=None,
                        shots_temp_min=None, shots_temp_max=None):
        now = datetime.datetime.now().isoformat(timespec="seconds")
        existing = self.get_session_by_path(folder_path)
        if existing:
            self.conn.execute(
                """UPDATE sessions SET
                    category=?, telescope=?, mode=?, target=?, filter=?, exposure=?, gain=?,
                    temperature=?, session_datetime=?, session_date=?, raw_ok_count=?, raw_failed_count=?,
                    stacked_jpg_path=?, stacked_png_path=?, stacked_fits_path=?, stacked_tiff_path=?,
                    thumbnail_path=?, total_size=?, unrecognized_count=?, dir_mtime=?,
                    file_count=?, shots_binning=?, shots_ra=?, shots_dec=?, shots_taken=?,
                    shots_stacked=?, shots_to_take=?, shots_temp_min=?, shots_temp_max=?, last_scanned=?
                   WHERE id=?""",
                (category, telescope, mode, target, filter_name, exposure, gain, temperature,
                 session_datetime, session_date, raw_ok_count, raw_failed_count,
                 stacked_jpg_path, stacked_png_path, stacked_fits_path, stacked_tiff_path,
                 thumbnail_path, total_size, unrecognized_count, dir_mtime,
                 file_count, shots_binning, shots_ra, shots_dec, shots_taken,
                 shots_stacked, shots_to_take, shots_temp_min, shots_temp_max, now, existing["id"]),
            )
            return existing["id"], False
        else:
            cur = self.conn.execute(
                """INSERT INTO sessions
                   (folder_path, category, telescope, mode, target, filter, exposure, gain,
                    temperature, session_datetime, session_date, raw_ok_count, raw_failed_count,
                    stacked_jpg_path, stacked_png_path, stacked_fits_path, stacked_tiff_path,
                    thumbnail_path, total_size, unrecognized_count, dir_mtime,
                    file_count, shots_binning, shots_ra, shots_dec, shots_taken, shots_stacked,
                    shots_to_take, shots_temp_min, shots_temp_max, first_scanned, last_scanned)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (folder_path, category, telescope, mode, target, filter_name, exposure, gain,
                 temperature, session_datetime, session_date, raw_ok_count, raw_failed_count,
                 stacked_jpg_path, stacked_png_path, stacked_fits_path, stacked_tiff_path,
                 thumbnail_path, total_size, unrecognized_count, dir_mtime,
                 file_count, shots_binning, shots_ra, shots_dec, shots_taken, shots_stacked,
                 shots_to_take, shots_temp_min, shots_temp_max, now, now),
            )
            return cur.lastrowid, True

    def touch_session_last_scanned(self, session_id):
        now = datetime.datetime.now().isoformat(timespec="seconds")
        self.conn.execute("UPDATE sessions SET last_scanned = ? WHERE id = ?", (now, session_id))

    def get_session_by_id(self, session_id):
        return self.conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()

    def all_session_folder_paths(self):
        return {row["folder_path"] for row in self.conn.execute("SELECT folder_path FROM sessions")}

    def delete_sessions_by_paths(self, paths):
        for p in paths:
            self.conn.execute("DELETE FROM sessions WHERE folder_path = ?", (p,))

    def delete_session_by_id(self, session_id):
        self.conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        self.conn.execute("DELETE FROM raw_quality WHERE session_id = ?", (session_id,))

    def update_session_folder_path(self, session_id, old_folder_path, new_folder_path):
        """Aggiorna il percorso di una sessione dopo una rinomina/spostamento
        fisico sul disco. I percorsi degli stacked (che iniziano con il
        vecchio percorso della cartella) vengono aggiornati di conseguenza;
        thumbnail_path resta invariato perché punta a un file nella cache
        miniature dell'app, non dentro la cartella sessione."""
        row = self.get_session_by_id(session_id)
        if not row:
            return

        def relocate(p):
            if p and p.startswith(old_folder_path):
                return new_folder_path + p[len(old_folder_path):]
            return p

        self.conn.execute(
            "UPDATE sessions SET folder_path=?, stacked_jpg_path=?, stacked_png_path=?, "
            "stacked_fits_path=?, stacked_tiff_path=? WHERE id=?",
            (new_folder_path, relocate(row["stacked_jpg_path"]), relocate(row["stacked_png_path"]),
             relocate(row["stacked_fits_path"]), relocate(row["stacked_tiff_path"]), session_id),
        )

    def update_session_object_info(self, session_id, object_type=None, object_constellation=None,
                                    object_magnitude=None, object_name_resolved=None, ra_deg=None,
                                    dec_deg=None, altitude_deg=None, azimuth_deg=None,
                                    moon_phase_pct=None, moon_separation_deg=None):
        now = datetime.datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """UPDATE sessions SET
                object_type=?, object_constellation=?, object_magnitude=?, object_name_resolved=?,
                ra_deg=?, dec_deg=?, altitude_deg=?, azimuth_deg=?, moon_phase_pct=?,
                moon_separation_deg=?, object_lookup_time=?
               WHERE id=?""",
            (object_type, object_constellation, object_magnitude, object_name_resolved, ra_deg,
             dec_deg, altitude_deg, azimuth_deg, moon_phase_pct, moon_separation_deg, now,
             session_id),
        )

    def all_sessions(self, telescope_filter=None, target_filter=None,
                      date_from=None, date_to=None, mode_filter=None):
        query = "SELECT * FROM sessions WHERE 1=1"
        params = []
        if telescope_filter and telescope_filter != "Tutti":
            query += " AND telescope = ?"
            params.append(telescope_filter)
        if mode_filter and mode_filter != "Tutte":
            query += " AND mode = ?"
            params.append(mode_filter)
        if target_filter:
            query += " AND target = ?"
            params.append(target_filter)
        if date_from:
            query += " AND (session_date IS NOT NULL AND session_date >= ?)"
            params.append(date_from)
        if date_to:
            query += " AND (session_date IS NOT NULL AND session_date <= ?)"
            params.append(date_to)
        query += " ORDER BY session_datetime DESC"
        return self.conn.execute(query, params).fetchall()

    def distinct_targets(self):
        return [r["target"] for r in self.conn.execute(
            "SELECT DISTINCT target FROM sessions WHERE target IS NOT NULL ORDER BY target COLLATE NOCASE"
        )]

    def distinct_telescopes(self):
        return [r["telescope"] for r in self.conn.execute(
            "SELECT DISTINCT telescope FROM sessions WHERE telescope IS NOT NULL ORDER BY telescope"
        )]

    def stats(self):
        return self.conn.execute(
            "SELECT COUNT(*) AS n_sessions, "
            "COALESCE(SUM(raw_ok_count),0) AS n_raw_ok, "
            "COALESCE(SUM(raw_failed_count),0) AS n_raw_failed, "
            "COALESCE(SUM(total_size),0) AS total_size, "
            "SUM(CASE WHEN stacked_jpg_path IS NOT NULL THEN 1 ELSE 0 END) AS n_stacked "
            "FROM sessions"
        ).fetchone()

    # ------------------------------------------------------------------
    # Frame di calibrazione (cali_frame + DWARF_DARK)
    # ------------------------------------------------------------------
    def get_calibration_by_path(self, record_path):
        return self.conn.execute(
            "SELECT * FROM calibration WHERE record_path = ?", (record_path,)
        ).fetchone()

    def touch_calibration_last_scanned(self, cal_id):
        now = datetime.datetime.now().isoformat(timespec="seconds")
        self.conn.execute("UPDATE calibration SET last_scanned = ? WHERE id = ?", (now, cal_id))

    def upsert_calibration(self, telescope, source, frame_type, camera, gain, bin_, exposure, ir,
                            temperature, stack_count, raw_count, session_datetime, session_date,
                            record_path, dir_mtime, file_count, total_size):
        now = datetime.datetime.now().isoformat(timespec="seconds")
        existing = self.get_calibration_by_path(record_path)
        if existing:
            self.conn.execute(
                """UPDATE calibration SET
                    telescope=?, source=?, frame_type=?, camera=?, gain=?, bin=?, exposure=?, ir=?,
                    temperature=?, stack_count=?, raw_count=?, session_datetime=?, session_date=?,
                    dir_mtime=?, file_count=?, total_size=?, last_scanned=?
                   WHERE id=?""",
                (telescope, source, frame_type, camera, gain, bin_, exposure, ir, temperature,
                 stack_count, raw_count, session_datetime, session_date, dir_mtime, file_count,
                 total_size, now, existing["id"]),
            )
            return existing["id"], False
        else:
            cur = self.conn.execute(
                """INSERT INTO calibration
                   (telescope, source, frame_type, camera, gain, bin, exposure, ir, temperature,
                    stack_count, raw_count, session_datetime, session_date, record_path, dir_mtime,
                    file_count, total_size, first_scanned, last_scanned)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (telescope, source, frame_type, camera, gain, bin_, exposure, ir, temperature,
                 stack_count, raw_count, session_datetime, session_date, record_path, dir_mtime,
                 file_count, total_size, now, now),
            )
            return cur.lastrowid, True

    def all_calibration_record_paths(self):
        return {r["record_path"] for r in self.conn.execute("SELECT record_path FROM calibration")}

    def delete_calibration_by_paths(self, paths):
        for p in paths:
            self.conn.execute("DELETE FROM calibration WHERE record_path = ?", (p,))

    def delete_calibration_by_id(self, cal_id):
        self.conn.execute("DELETE FROM calibration WHERE id = ?", (cal_id,))

    def update_calibration_record_path(self, cal_id, new_record_path):
        self.conn.execute("UPDATE calibration SET record_path = ? WHERE id = ?", (new_record_path, cal_id))

    def all_calibration(self, telescope_filter=None, source_filter=None, frame_type_filter=None):
        query = "SELECT * FROM calibration WHERE 1=1"
        params = []
        if telescope_filter and telescope_filter != "Tutti":
            query += " AND telescope = ?"
            params.append(telescope_filter)
        if source_filter and source_filter != "Tutte":
            query += " AND source = ?"
            params.append(source_filter)
        if frame_type_filter and frame_type_filter != "Tutti":
            query += " AND frame_type = ?"
            params.append(frame_type_filter)
        query += " ORDER BY frame_type, camera, gain, exposure"
        return self.conn.execute(query, params).fetchall()

    def distinct_calibration_telescopes(self):
        return [r["telescope"] for r in self.conn.execute(
            "SELECT DISTINCT telescope FROM calibration WHERE telescope IS NOT NULL ORDER BY telescope"
        )]

    def calibration_stats(self):
        return self.conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(total_size),0) AS total_size FROM calibration"
        ).fetchone()

    # ------------------------------------------------------------------
    # Qualità dei raw (analisi su richiesta: stelle rilevate, FWHM, sfondo)
    # ------------------------------------------------------------------
    def upsert_raw_quality(self, session_id, file_path, file_name, star_count, fwhm_px,
                            background_mean, background_noise):
        now = datetime.datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """INSERT INTO raw_quality
               (session_id, file_path, file_name, star_count, fwhm_px, background_mean,
                background_noise, analyzed_at)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(file_path) DO UPDATE SET
                 session_id=excluded.session_id, file_name=excluded.file_name,
                 star_count=excluded.star_count, fwhm_px=excluded.fwhm_px,
                 background_mean=excluded.background_mean, background_noise=excluded.background_noise,
                 analyzed_at=excluded.analyzed_at""",
            (session_id, file_path, file_name, star_count, fwhm_px, background_mean,
             background_noise, now),
        )

    def get_raw_quality_for_paths(self, paths):
        """Ritorna {file_path: row} per i percorsi indicati che hanno già
        un'analisi di qualità salvata."""
        if not paths:
            return {}
        placeholders = ",".join("?" for _ in paths)
        rows = self.conn.execute(
            f"SELECT * FROM raw_quality WHERE file_path IN ({placeholders})", list(paths)
        ).fetchall()
        return {r["file_path"]: r for r in rows}

    def delete_raw_quality_by_path(self, path):
        self.conn.execute("DELETE FROM raw_quality WHERE file_path = ?", (path,))

    def update_raw_quality_path(self, old_path, new_path):
        self.conn.execute("UPDATE raw_quality SET file_path=?, file_name=? WHERE file_path=?",
                           (new_path, new_path.split("/")[-1].split("\\")[-1], old_path))

    def set_meta(self, key, value):
        self.conn.execute(
            "INSERT INTO scan_meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def get_meta(self, key, default=None):
        row = self.conn.execute("SELECT value FROM scan_meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def commit(self):
        self.conn.commit()
