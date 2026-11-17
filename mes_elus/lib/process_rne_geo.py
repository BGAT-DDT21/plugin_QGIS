# -*- coding: utf-8 -*-
# lib/process_rne_geo.py
# Création de couches géographiques à partir des CSV filtrés du RNE
# Version stabilisée – jointures sans chargement préalable dans le projet
# 11/09/2026

import os
import geopandas as gpd
import pandas as pd
from qgis.PyQt.QtWidgets import (
    QProgressDialog, QDialog, QVBoxLayout,
    QCheckBox, QDialogButtonBox, QLabel, QMessageBox
)
from qgis.PyQt.QtCore import QVariant
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsField, QgsProject
)

# Import de la fonction de récupération des chemins
try:
    from .geom_paths import get_geom_paths
except ImportError:
    from geom_paths import get_geom_paths


# ---------------------------------------------------------------------------
# Gestion des messages utilisateur
# ---------------------------------------------------------------------------
try:
    from .utils import info, warning
except ImportError:
    def info(parent, title, message):
        QMessageBox.information(parent, title, message)

    def warning(parent, title, message):
        QMessageBox.warning(parent, title, message)


# ===========================================================================
# FONCTION D'AGRÉGATION INTELLIGENTE DES ÉLUS
# ===========================================================================
def aggregate_elus(df, group_var, geo_cols, elus_cols):
    """
    Agrège les élus par entité géographique en respectant un ordre de priorité
    des fonctions (maire > adjoint > conseiller > autres).
    """
    def priorite_fonction(row):
        fonc = str(row.get('Libellé de la fonction', '')).lower()
        if 'maire' in fonc:
            return 0
        elif 'adjoint' in fonc:
            return 1
        elif 'conseiller' in fonc or 'délégué' in fonc:
            return 2
        else:
            return 99

    df = df.copy()
    df['__prio'] = df.apply(priorite_fonction, axis=1)
    df['__nom_complet'] = (
        df['Nom de l\'élu'].fillna('') + ' ' + df['Prénom de l\'élu'].fillna('')
    )
    df = df.sort_values(['__prio', '__nom_complet'])

    grouped_dict = {}
    geometries = {}

    for name, group in df.groupby(group_var):
        row = {group_var: name}
        for col in df.columns:
            if col in geo_cols:
                row[col] = group[col].iloc[0]
            elif col in elus_cols:
                row[col] = '; '.join(group[col].dropna().astype(str))
        grouped_dict[name] = row
        geometries[name] = group['geometry'].iloc[0]

    grouped_df = pd.DataFrame(grouped_dict.values())
    grouped_gdf = gpd.GeoDataFrame(
        grouped_df,
        geometry=list(geometries.values()),
        crs=df.crs
    )
    return grouped_gdf


# ===========================================================================
# DIALOGUE DE SÉLECTION DES MANDATS À TRAITER
# ===========================================================================
def select_types_to_process(csv_files, parent=None):
    """
    Affiche une boîte de dialogue permettant de cocher les mandats à traiter.
    """
    types = {
        f: f.replace("filtered_", "").replace(".csv", "").replace("-", " ").title()
        for f in csv_files
    }

    dialog = QDialog(parent)
    dialog.setWindowTitle("Choisir les mandats à traiter")
    layout = QVBoxLayout()
    layout.addWidget(QLabel("Sélectionnez les mandats à ajouter au projet QGIS :"))

    checkboxes = {}
    for file, label in types.items():
        cb = QCheckBox(label)
        cb.setChecked(True)
        checkboxes[file] = cb
        layout.addWidget(cb)

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    dialog.setLayout(layout)
    dialog.resize(500, 400)

    if dialog.exec_() != QDialog.Accepted:
        return None

    selected = [f for f, cb in checkboxes.items() if cb.isChecked()]

    if not selected:
        warning(parent, "Aucun mandat", "Sélectionnez au moins un mandat.")
        return None

    return selected


# ===========================================================================
# FONCTION PRINCIPALE
# ===========================================================================
def process_geo(filtered_data_dir, parent=None):
    """
    Point d'entrée principal.
    Charge les fonds géographiques uniquement en mémoire (pas dans le projet)
    puis réalise les jointures.
    """
    # ------------------------------------------------------------------
    # 1. Récupération de la liste des CSV
    # ------------------------------------------------------------------
    csv_files = [f for f in os.listdir(filtered_data_dir) if f.endswith(".csv")]
    if not csv_files:
        warning(parent, "Aucun fichier", "Aucun CSV filtré trouvé.")
        return False

    selected_csv = select_types_to_process(csv_files, parent)
    if not selected_csv:
        return False

    # ------------------------------------------------------------------
    # 2. Barre de progression
    # ------------------------------------------------------------------
    progress = QProgressDialog(
        "Création des couches...", "Annuler", 0, len(selected_csv), parent
    )
    progress.setWindowTitle("Mes Élus")

    # ------------------------------------------------------------------
    # 3. Chargement des fonds géographiques UNIQUEMENT EN MÉMOIRE
    #    (ils ne sont PAS ajoutés au projet QGIS)
    # ------------------------------------------------------------------
    geom_paths = get_geom_paths()
    fonds_charges = {}

    if not geom_paths:
        warning(parent, "Aucun fond défini",
                "Aucun chemin de couche géométrique n'est enregistré.\n"
                "Va dans l'onglet de gestion des chemins et définis-les d'abord.")
        return False

    for layer_type, data in geom_paths.items():
        path = data["path"]
        field = data["field"]

        if not os.path.exists(path):
            warning(parent, f"Fichier introuvable – {layer_type}",
                    f"Le fichier suivant n'existe pas :\n{path}")
            continue

        try:
            gdf = gpd.read_file(path)

            # Standardisation du nom du champ identifiant
            id_name = {
                "communes": "DEPCOM",
                "epci": "SIREN_EPCI",
                "cantons": "CODE_CANTON",
                "circonscriptions": "CODE_CIRCO",
                "departements": "DEP",
                "regions": "REG"
            }.get(layer_type, field)

            gdf = gdf.rename(columns={field: id_name})
            gdf = gdf[[id_name, "geometry"]].copy()
            fonds_charges[layer_type] = gdf

        except Exception as e:
            warning(parent, f"Erreur de chargement – {layer_type}",
                    f"Impossible de lire le fichier :\n{path}\n\n{e}")

    # Affectation aux variables utilisées ensuite
    communes_gdf = fonds_charges.get("communes")
    epci_gdf     = fonds_charges.get("epci")
    cantons_gdf  = fonds_charges.get("cantons")
    circo_gdf    = fonds_charges.get("circonscriptions")
    depts_gdf    = fonds_charges.get("departements")
    regions_gdf  = fonds_charges.get("regions")

    layers_added = []

    # ------------------------------------------------------------------
    # 4. Traitement de chaque fichier CSV sélectionné
    # ------------------------------------------------------------------
    for i, csv_file in enumerate(selected_csv):
        progress.setValue(i)
        progress.setLabelText(csv_file)

        if progress.wasCanceled():
            break

        path = os.path.join(filtered_data_dir, csv_file)

        # Lecture intelligente du séparateur
        try:
            with open(path, 'r', encoding='utf-8') as f:
                snippet = f.read(2048)
            sep = ',' if snippet.count(',') > snippet.count(';') else ';'
            df = pd.read_csv(path, sep=sep, encoding="utf-8", low_memory=False, dtype=str)
        except Exception as e:
            warning(parent, "Erreur de lecture", f"Impossible de lire {csv_file}\n{e}")
            continue

        gdf = None
        layer_name = None
        group_var = None
        geo_cols = []
        elus_cols = []
        fn = csv_file.lower()

        # ==============================================================
        # 4.1 CONSEILLERS COMMUNAUTAIRES
        # ==============================================================
        if ("conseiller-communautaire" in fn or "conseillers-communautaires" in fn) and epci_gdf is not None:
            if 'N° SIREN' in df.columns:
                df['SIREN_EPCI'] = df['N° SIREN'].str.zfill(9)
                gdf = gpd.GeoDataFrame(
                    df.merge(epci_gdf, on='SIREN_EPCI', how='left'),
                    crs=epci_gdf.crs
                )
                layer_name = "Conseillers communautaires"
                group_var = "SIREN_EPCI"
                geo_cols = ["SIREN_EPCI", "Code du département", "Libellé du département",
                            "N° SIREN", "Libellé de l'EPCI"]
                elus_cols = [c for c in df.columns if c not in geo_cols]

        # ==============================================================
        # 4.2 MAIRES & CONSEILLERS MUNICIPAUX
        # ==============================================================
        elif ("maire" in fn or "conseiller-municipal" in fn or "conseillers-municipaux" in fn) and communes_gdf is not None:
            if 'Code de la commune' in df.columns:
                df['DEPCOM'] = df['Code de la commune'].str.zfill(5)
                gdf = gpd.GeoDataFrame(
                    df.merge(communes_gdf, on='DEPCOM', how='left'),
                    crs=communes_gdf.crs
                )
                layer_name = "Maires" if "maire" in fn else "Conseillers municipaux"
                group_var = "DEPCOM"
                geo_cols = ["DEPCOM", "Code du département", "Libellé du département",
                            "Code de la commune", "Libellé de la commune"]
                elus_cols = [c for c in df.columns if c not in geo_cols]

        # ==============================================================
        # 4.3 CONSEILLERS DÉPARTEMENTAUX
        # ==============================================================
        elif ("conseiller-departemental" in fn or "conseillers-departementaux" in fn) and cantons_gdf is not None:
            if 'Code du canton' in df.columns:
                df['CODE_CANTON'] = df['Code du canton'].str.zfill(4)
                gdf = gpd.GeoDataFrame(
                    df.merge(cantons_gdf, on='CODE_CANTON', how='left'),
                    crs=cantons_gdf.crs
                )
                layer_name = "Conseillers départementaux"
                group_var = "CODE_CANTON"
                geo_cols = ["CODE_CANTON", "Code du département", "Libellé du département",
                            "Code du canton", "Libellé du canton"]
                elus_cols = [c for c in df.columns if c not in geo_cols]

        # ==============================================================
        # 4.4 DÉPUTÉS
        # ==============================================================
        elif ("depute" in fn or "deputes" in fn) and circo_gdf is not None:

            # Recherche flexible de la colonne circonscription
            col_circo = None
            for c in df.columns:
                c_low = c.lower()
                if "circonscription" in c_low or "circo" in c_low or "legislativ" in c_low:
                    col_circo = c
                    break

            if col_circo is None:
                warning(parent, "Colonne manquante",
                        f"Aucune colonne de circonscription trouvée dans {csv_file}.")
            else:
                df = df.copy()
                df['merge_key'] = (
                    df[col_circo]
                    .astype(str)
                    .str.replace(r"\D", "", regex=True)
                    .str.zfill(4)
                    .str[-4:]
                )

                circo_temp = circo_gdf.copy()
                id_col = [c for c in circo_temp.columns if c != "geometry"][0]
                circo_temp['merge_key'] = (
                    circo_temp[id_col]
                    .astype(str)
                    .str.replace(r"\D", "", regex=True)
                    .str.zfill(4)
                    .str[-4:]
                )

                gdf = gpd.GeoDataFrame(
                    df.merge(circo_temp[['merge_key', 'geometry']], on='merge_key', how='left'),
                    crs=circo_temp.crs
                )

                if gdf['geometry'].notna().sum() > 0:
                    layer_name = "Députés"
                    group_var = "merge_key"
                    geo_cols = ["merge_key"]
                    elus_cols = [c for c in df.columns if c not in geo_cols]

        # ==============================================================
        # 4.5 SÉNATEURS
        # ==============================================================
        elif ("senateur" in fn or "senateurs" in fn) and depts_gdf is not None:
            col = next((c for c in df.columns if "départ" in c.lower() and "code" in c.lower()), None)
            if col:
                df['DEP'] = df[col].str.zfill(2)
                gdf = gpd.GeoDataFrame(
                    df.merge(depts_gdf, on='DEP', how='left'),
                    crs=depts_gdf.crs
                )
                layer_name = "Sénateurs"
                group_var = "DEP"
                geo_cols = ["DEP", "Code du département", "Libellé du département"]
                elus_cols = [c for c in df.columns if c not in geo_cols]

        # ==============================================================
        # 4.6 CONSEILLERS RÉGIONAUX
        # ==============================================================
        elif ("conseiller-regional" in fn or "conseillers-regionaux" in fn) and depts_gdf is not None:
            if 'Code de la section départementale' in df.columns:
                df['DEP'] = df['Code de la section départementale'].str.zfill(2)
                gdf = gpd.GeoDataFrame(
                    df.merge(depts_gdf, on='DEP', how='left'),
                    crs=depts_gdf.crs
                )
                layer_name = "Conseillers régionaux"
                group_var = "DEP"
                geo_cols = ["DEP", "Code de la région", "Libellé de la région"]
                elus_cols = [c for c in df.columns if c not in geo_cols]

        # ==============================================================
        # 5. CRÉATION DE LA COUCHE PRINCIPALE
        # ==============================================================
        if gdf is not None and gdf['geometry'].notna().any():
            gdf = gdf[gdf['geometry'].notna()].copy()

            if group_var:
                gdf = aggregate_elus(gdf, group_var, geo_cols, elus_cols)

            vl = QgsVectorLayer("Polygon?crs=epsg:2154", layer_name, "memory")
            pr = vl.dataProvider()

            fields = [QgsField(n, QVariant.String) for n in gdf.columns if n != 'geometry']
            pr.addAttributes(fields)
            vl.updateFields()

            feats = []
            for _, row in gdf.iterrows():
                f = QgsFeature(vl.fields())
                for field in gdf.columns:
                    if field != 'geometry':
                        val = str(row[field]) if pd.notna(row[field]) else ""
                        f.setAttribute(field, val)
                f.setGeometry(QgsGeometry.fromWkt(row.geometry.wkt))
                feats.append(f)

            pr.addFeatures(feats)
            vl.updateExtents()
            QgsProject.instance().addMapLayer(vl)
            layers_added.append(layer_name)
            info(parent, "Succès", f"{layer_name} → {len(feats)} entités")
        else:
            warning(parent, "Échec de jointure",
                    f"Aucune géométrie valide pour {csv_file}.")

    # ------------------------------------------------------------------
    # 6. Fin
    # ------------------------------------------------------------------
    progress.setValue(len(selected_csv))
    info(parent, "Terminé !", f"{len(layers_added)} couche(s) créée(s)")

    return True