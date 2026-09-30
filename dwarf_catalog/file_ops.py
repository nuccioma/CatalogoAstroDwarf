"""
file_ops.py - Operazioni fisiche sui file/cartelle (elimina/rinomina/sposta/
copia) usate dalla GUI per agire sulle righe selezionate delle tre tabelle
(sessioni, frame di calibrazione, singoli file di una sessione). Ogni
funzione qui dentro esegue l'operazione richiesta senza chiedere conferma:
la conferma con avviso all'utente va fatta PRIMA, nel chiamante (vedi
gui.confirm_action), così queste funzioni restano semplici da testare.
"""

import os
import shutil

from i18n import tr


def delete_path(path):
    """Elimina definitivamente un file o un'intera cartella (ricorsivamente)."""
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)
    else:
        raise FileNotFoundError(tr("Percorso non trovato: {path}").format(path=path))


def rename_path(path, new_name):
    """Rinomina un file o una cartella (resta nella stessa cartella padre).
    Ritorna il nuovo percorso completo."""
    new_name = new_name.strip()
    if not new_name:
        raise ValueError(tr("Il nuovo nome non può essere vuoto."))
    if os.sep in new_name or (os.altsep and os.altsep in new_name):
        raise ValueError(tr("Il nuovo nome non può contenere separatori di percorso."))
    parent = os.path.dirname(path.rstrip(os.sep))
    new_path = os.path.join(parent, new_name)
    if os.path.exists(new_path):
        raise FileExistsError(tr("Esiste già un elemento chiamato '{name}' in quella cartella.").format(name=new_name))
    os.rename(path, new_path)
    return new_path


def move_path(path, dest_dir):
    """Sposta un file o una cartella dentro dest_dir. Ritorna il nuovo percorso."""
    if not os.path.isdir(dest_dir):
        raise NotADirectoryError(tr("La cartella di destinazione non esiste: {dest}").format(dest=dest_dir))
    base_name = os.path.basename(path.rstrip(os.sep))
    new_path = os.path.join(dest_dir, base_name)
    if os.path.exists(new_path):
        raise FileExistsError(tr("Esiste già un elemento chiamato '{name}' nella destinazione.").format(name=base_name))
    shutil.move(path, new_path)
    return new_path


def copy_path(path, dest_dir):
    """Copia un file o una cartella (ricorsivamente) dentro dest_dir.
    Ritorna il nuovo percorso. L'originale non viene toccato."""
    if not os.path.isdir(dest_dir):
        raise NotADirectoryError(tr("La cartella di destinazione non esiste: {dest}").format(dest=dest_dir))
    base_name = os.path.basename(path.rstrip(os.sep))
    new_path = os.path.join(dest_dir, base_name)
    if os.path.exists(new_path):
        raise FileExistsError(tr("Esiste già un elemento chiamato '{name}' nella destinazione.").format(name=base_name))
    if os.path.isdir(path):
        shutil.copytree(path, new_path)
    else:
        shutil.copy2(path, new_path)
    return new_path
