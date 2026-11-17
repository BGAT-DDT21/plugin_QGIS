# -*- coding: utf-8 -*-
# mes_elus/lib/download_rne.py
# VERSION FINALE – URLs automatiques (plus jamais de 404) – filtrage intact
import json
import os
import tempfile
import requests
import pandas as pd
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QCheckBox, QDialogButtonBox,
    QLabel, QProgressDialog, QMessageBox, QLineEdit
)
from qgis.PyQt.QtCore import QSettings
try:
    from .utils import info, warning
except ImportError:
    info = lambda p, t, m: QMessageBox.information(p, t, m)
    warning = lambda p, t, m: QMessageBox.warning(p, t, m)

# ===================== LOG =====================
log_path = os.path.join(tempfile.gettempdir(), "debug_rne_filtrage.log")
log_file = open(log_path, "a", encoding="utf-8")
log_file.write("\n" + "="*60 + "\n")
log_file.write(f"NOUVELLE SESSION – {pd.Timestamp.now():%Y-%m-%d %H:%M:%S}\n")
log_file.write("="*60 + "\n")
log_file.flush()

def log(msg):
    print(msg)
    log_file.write(msg + "\n")
    log_file.flush()
log("=== DÉBUT SESSION RNE ===")

# ===================== RÉGIONS → DÉPARTEMENTS =====================
REGIONS_DEPARTEMENTS = {
    "01": ["971"], "02": ["972"], "03": ["973"], "04": ["974"], "06": ["976"],
    "11": ["75", "77", "78", "91", "92", "93", "94", "95"],
    "24": ["18", "28", "36", "37", "41", "45"],
    "27": ["21", "25", "39", "58", "70", "71", "89", "90"],
    "28": ["14", "27", "50", "61", "76"],
    "32": ["02", "59", "60", "62", "80"],
    "44": ["08", "10", "51", "52", "54", "55", "57", "67", "68", "88"],
    "52": ["44", "49", "53", "72", "85"],
    "53": ["22", "29", "35", "56"],
    "75": ["16", "17", "19", "23", "24", "33", "40", "47", "64", "79", "86", "87"],
    "76": ["09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82"],
    "84": ["01", "03", "07", "15", "26", "38", "42", "43", "63", "69", "73", "74"],
    "93": ["04", "05", "06", "13", "83", "84"],
    "94": ["2A", "2B"]
}
def get_deps_from_region(code_reg):
    deps = REGIONS_DEPARTEMENTS.get(code_reg.zfill(2), [])
    log(f"Région {code_reg} → {len(deps)} départements : {deps}")
    return deps
 
    
def ask_for_proxy(parent=None):
    proxy_dialog = QDialog(parent)
    proxy_dialog.setWindowTitle("Configuration du Proxy")

    layout = QVBoxLayout()
    layout.addWidget(QLabel("Veuillez entrer l'URL du proxy à utiliser (ex: http://monproxy:8080) :"))

    proxy_input = QLineEdit()
    proxy_input.setPlaceholderText("http://monproxy:8080")
    layout.addWidget(proxy_input)

    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    btns.accepted.connect(proxy_dialog.accept)
    btns.rejected.connect(proxy_dialog.reject)
    layout.addWidget(btns)

    proxy_dialog.setLayout(layout)

    if proxy_dialog.exec_() == QDialog.Accepted:
        proxy_url = proxy_input.text().strip()
        if proxy_url:
            return proxy_url
        else:
            warning(parent, "Proxy non valide", "Veuillez entrer une URL de proxy valide.")
            return None
    else:
        return None


def load_proxy_config():
    settings = QSettings("MesElusPlugin", "Proxy")
    use_proxy = settings.value("use_proxy", False, type=bool)
    proxy_url = settings.value("proxy_url", "")
    return proxy_url if use_proxy else None


# ===================== CHOIX DES MANDATS =====================
def select_types_to_download(parent=None):
    log("Ouverture dialogue sélection mandats")

    # Vérifiez si un proxy est déjà configuré
    proxy_url = load_proxy_config()
    if proxy_url is None:
        proxy_url = ask_for_proxy(parent)
        if proxy_url is not None:
            save_proxy_config(proxy_url)

    types = {
        "conseillers_darrondissements": "Conseillers d'arrondissements (Pas de géocodage disponible)",
        "conseillers_municipaux": "Conseillers municipaux",
        "conseillers_communautaires": "Conseillers communautaires (EPCI)",
        "conseillers_departementaux": "Conseillers départementaux",
        "conseillers_regionaux": "Conseillers régionaux",
        "membres_assemblee": "Membres d'une assemblée particulière (Pas de géocodage disponible)",
        "representants_parlement_europeen": "Représentants au Parlement européen",
        "senateurs": "Sénateurs",
        "deputes": "Députés",
        "maires": "Maires",
        "conseillers_francais_etranger": "Conseillers des Français de l'étranger (Pas de géocodage disponible)",
        "assemblee_francais_etranger": "Assemblée des Français de l'étranger (Pas de géocodage disponible)"
    }

    dialog = QDialog(parent)
    dialog.setWindowTitle("Sélection des mandats à télécharger")
    layout = QVBoxLayout()
    layout.addWidget(QLabel("Cochez les mandats à télécharger (décoché = test rapide)"))

    checkboxes = {}
    for key, label in types.items():
        cb = QCheckBox(label)
        cb.setChecked(False)
        checkboxes[key] = cb
        layout.addWidget(cb)

    layout.addWidget(QLabel(""))

    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    btns.accepted.connect(dialog.accept)
    btns.rejected.connect(dialog.reject)
    layout.addWidget(btns)

    dialog.setLayout(layout)
    dialog.resize(540, 480)

    if dialog.exec_() != QDialog.Accepted:
        return None

    selected = [k for k, v in checkboxes.items() if v.isChecked()]
    if not selected:
        warning(parent, "Aucun mandat", "Cochez au moins un mandat.")
        return None

    # Utiliser la configuration du proxy depuis QSettings
    settings = QSettings("MesElusPlugin", "Proxy")
    use_proxy = settings.value("use_proxy", False, type=bool)

    log(f"Types d'élus sélectionnés: {selected}")
    log(f"Proxy : {'activé' if use_proxy else 'désactivé'}")

    return selected, proxy_url if use_proxy else None


# ===================== RÉCUPÉRATION AUTOMATIQUE DES URLs =====================
def get_current_urls(proxy_url):
    api_url = "https://www.data.gouv.fr/api/1/datasets/repertoire-national-des-elus-1/"
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    
    try:
        r = requests.get(api_url, proxies=proxies, timeout=30)
        r.raise_for_status()
        data = r.json()
        mapping = {
            "elus-conseillers-darrondissements-ca.csv": "conseillers_darrondissements",
            "elus-conseillers-municipaux-cm.csv": "conseillers_municipaux",
            "elus-conseillers-communautaires-epci.csv": "conseillers_communautaires",
            "elus-conseillers-departementaux-cd.csv": "conseillers_departementaux",
            "elus-conseillers-regionaux-cr.csv": "conseillers_regionaux",
            "elus-membres-dune-assemblee-ma.csv": "membres_assemblee",
            "elus-representants-parlement-europeen-rpe.csv": "representants_parlement_europeen",
            "elus-senateurs-sen.csv": "senateurs",
            "elus-deputes-dep.csv": "deputes",
            "elus-maires-mai.csv": "maires",
            "elus-conseillers-des-francais-de-letranger-cons.csv": "conseillers_francais_etranger",
            "elus-assemblee-des-francais-de-letranger-afe.csv": "assemblee_francais_etranger"
        }
        urls_dict = {}
        for resource in data["resources"]:
            filename = resource["title"]
            if filename in mapping:
                urls_dict[mapping[filename]] = resource["url"]
        log(f"URLs automatiques récupérées ({len(urls_dict)} fichiers)")
        return urls_dict
    except Exception as e:
        log(f"ERREUR récupération URLs automatiques : {e}")
        return {}

# ===================== TÉLÉCHARGEMENT + FILTRAGE =====================
def download_and_filter(rne_data_dir, filtered_data_dir, territory_type, selected_code, parent=None):
    # Récupérer la configuration du proxy depuis QSettings
    settings = QSettings("MesElusPlugin", "Proxy")
    use_proxy = settings.value("use_proxy", False, type=bool)
    proxy_url = settings.value("proxy_url", "")
    
     # Créer les dossiers s'ils n'existent pas
    os.makedirs(rne_data_dir, exist_ok=True)
    os.makedirs(filtered_data_dir, exist_ok=True)  # Assurez-vous que ce dossier existe

    # Si le proxy est requis et non configuré, afficher un message d'erreur
    if not proxy_url and use_proxy:
        warning(parent, "Proxy requis", "Le téléchargement nécessite un proxy. Veuillez configurer le proxy dans l'onglet Configuration.")
        return False

    # Récupérer les types de mandats à télécharger
    result = select_types_to_download(parent)
    if result is None:
        return False

    selected_types, proxy_url = result
    if not selected_types:
        return False

    # Récupération des URLs fraîches
    urls_dict = get_current_urls(proxy_url)
    if not urls_dict:
        warning(parent, "Erreur URLs", "Impossible de récupérer les URLs actuelles du RNE.\nVérifiez votre connexion/proxy.")
        return False
    urls_to_download = [urls_dict[k] for k in selected_types if k in urls_dict]

    progress = QProgressDialog("Téléchargement et filtrage…", "Annuler", 0, len(urls_to_download), parent)
    progress.setWindowTitle("RNE")
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    log(f"Proxy utilisé : {'Oui' if proxy_url else 'Non (connexion directe)'}")

    total = 0
    for i, url in enumerate(urls_to_download):
        progress.setValue(i)
        progress.setLabelText(os.path.basename(url))
        if progress.wasCanceled():
            break
        filename = os.path.basename(url)
        dest = os.path.join(rne_data_dir, filename)
        try:
            r = requests.get(url, proxies=proxies, timeout=180)
            r.raise_for_status()
            with open(dest, "wb") as f:
                f.write(r.content)
            log(f"✓ {filename} téléchargé")
            df = pd.read_csv(dest, sep=";", encoding="utf-8", low_memory=False)
            log(f" {len(df):,} lignes | colonnes : {list(df.columns)[:10]}...")

            dep_cols = [c for c in df.columns if "départ" in c.lower() and "code" in c.lower()]
            reg_cols = [c for c in df.columns if "région" in c.lower() and "code" in c.lower()]
            dep_col = dep_cols[0] if dep_cols else None
            reg_col = reg_cols[0] if reg_cols else None
            log(f" → Colonne département : {dep_col}")
            log(f" → Colonne région : {reg_col}")

            # Ajout : Recherche de la colonne "Code de la commune"
            com_cols = [c for c in df.columns if "commune" in c.lower() and "code" in c.lower()]
            com_col = com_cols[0] if com_cols else None
            log(f" → Colonne commune : {com_col}")

            if territory_type.lower().startswith("dép"):
                if selected_code in ["2A", "2B"]:
                    codes = ["2A", "2B"]
                elif selected_code == "2B":
                    codes = ["2B", "2A"]
                else:
                    codes = [selected_code.zfill(2)]
                log(f"Département sélectionné : {selected_code} → codes à garder : {codes}")
            else:
                deps = get_deps_from_region(selected_code)
                codes = [d.zfill(2) for d in deps]
                log(f"Région {selected_code} → {len(deps)} départements : {codes}")

            filtered = df.copy()

            # Si on a une colonne "Code de la commune", on vérifie les premiers chiffres
            if com_col:
                # Extraire les 2 premiers chiffres du code commune (pour obtenir le code département)
                df["dep_from_com"] = df[com_col].astype(str).str[:2]
                log(f" → Codes département extraits des codes communes : {df['dep_from_com'].unique()}")

                # Si le code département ne correspond pas, on utilise les premiers chiffres du code commune
                if dep_col:
                    df[dep_col] = df[dep_col].astype(str).str.strip().str.zfill(2)
                    # Comparer les codes département et ceux extraits des codes communes
                    mask = df[dep_col].isin(codes)
                    mask_from_com = df["dep_from_com"].isin(codes)
                    # Si les codes département ne correspondent pas, utiliser ceux des codes communes
                    filtered = df[mask | mask_from_com]
                    log(f" → Filtrage département + codes communes : {len(filtered)} lignes conservées")
                elif reg_col and not territory_type.lower().startswith("dép"):
                    df[reg_col] = df[reg_col].astype(str).str.strip().str.zfill(2)
                    filtered = df[df[reg_col] == selected_code.zfill(2)]
                    log(f" → Filtrage par région ({reg_col}) : {len(filtered)} lignes")
                else:
                    log(" Aucune colonne de filtrage → fichier complet conservé")
            else:
                # Logique existante si pas de colonne "Code de la commune"
                if dep_col:
                    df[dep_col] = df[dep_col].astype(str).str.strip().str.zfill(2)
                    filtered = df[df[dep_col].isin(codes)]
                    log(f" → Filtrage département réussi : {len(filtered)} lignes conservées")
                elif reg_col and not territory_type.lower().startswith("dép"):
                    df[reg_col] = df[reg_col].astype(str).str.strip().str.zfill(2)
                    filtered = df[df[reg_col] == selected_code.zfill(2)]
                    log(f" → Filtrage par région ({reg_col}) : {len(filtered)} lignes")
                else:
                    log(" Aucune colonne de filtrage → fichier complet conservé")

            out = os.path.join(filtered_data_dir, f"filtered_{filename}")
            filtered.to_csv(out, index=False, encoding="utf-8")
            total += len(filtered)
            log(f" → {len(filtered):,} lignes conservées → {out}")
            info(parent, "OK", f"{filename}\n{len(filtered):,} lignes conservées")
        except Exception as e:
            log(f"ERREUR {filename} : {e}")
            warning(parent, "Erreur", str(e))

    progress.setValue(len(urls_to_download))
    log(f"=== FIN – {total:,} lignes conservées ===")
    QMessageBox.information(parent, "Terminé !",
        f"Tout est fait !\n\n"
        f"{total:,} lignes conservées au total\n\n"
        f"Log complet → {log_path}")
    return True

