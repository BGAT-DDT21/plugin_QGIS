# -*- coding: utf-8 -*-
# lib/process_rne_geo.py
# Testé et validé le 24/11/2025

import os
import geopandas as gpd
import pandas as pd
from qgis.PyQt.QtWidgets import (
    QProgressDialog, QFileDialog, QDialog, QVBoxLayout,
    QCheckBox, QDialogButtonBox, QLabel, QMessageBox, QComboBox
)
from qgis.PyQt.QtCore import QSettings, QVariant
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsField,
    QgsProject
)
try:
    from .utils import info, warning
except:
    info = lambda p, t, m: QMessageBox.information(p, t, m)
    warning = lambda p, t, m: QMessageBox.warning(p, t, m)

# ===================== LOG =====================
import tempfile
log_path = os.path.join(tempfile.gettempdir(), "debug_meselus_geo.log")
log_file = open(log_path, "a", encoding="utf-8")

def log(msg):
    print("[MesElus GEO] " + msg)
    log_file.write(msg + "\n")
    log_file.flush()

log("\n" + "="*70)
log("NOUVELLE SESSION – " + pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"))
log("="*70)

# ------------------------------------------------------------------
# Agrégation intelligente avec ordre de fonction (maire → adjoint → conseiller)
# ------------------------------------------------------------------
def aggregate_elus(df, group_var, geo_cols, elus_cols):
    log(f"   Agrégation intelligente sur {group_var} → {len(df)} lignes avant")

    # 1. On crée une colonne temporaire d'ordre de priorité
    def priorite_fonction(row):
        fonc = str(row.get('Libellé de la fonction', '')).lower()
        if 'maire' in fonc:
            return 0
        elif 'adjoint' in fonc:
            return 1
        elif 'conseiller' in fonc or 'délégué' in fonc:
            return 2
        else:
            return 99  # autres (président EPCI, etc.)

    df['__prio'] = df.apply(priorite_fonction, axis=1)
    df['__nom_complet'] = df['Nom de l\'élu'].fillna('') + ' ' + df['Prénom de l\'élu'].fillna('')

    # 2. Tri par priorité + nom
    df = df.sort_values(['__prio', '__nom_complet'])

    # 3. Agrégation en conservant l'ordre
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

    # Créer un DataFrame à partir du résultat agrégé
    grouped_df = pd.DataFrame(grouped_dict.values())

    # Créer un GeoDataFrame avec la colonne de géométrie
    grouped_gdf = gpd.GeoDataFrame(grouped_df, geometry=list(geometries.values()), crs=df.crs)

    log(f"   → {len(grouped_gdf)} entités après agrégation intelligente")
    return grouped_gdf


# ------------------------------------------------------------------
def select_types_to_process(csv_files, parent=None):
    types = {f: f.replace("filtered_", "").replace(".csv", "").replace("-", " ").title() for f in csv_files}
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
    log(f"Mandats sélectionnés : {selected}")
    return selected

# ------------------------------------------------------------------
def load_fond(layer_type, id_name, parent=None):
    settings = QSettings("MesElusPlugin", "Fonds")
    path = settings.value(layer_type + "_path", None)
    field = settings.value(layer_type + "_field", None)
    if path and os.path.exists(path) and field:
        try:
            gdf = gpd.read_file(path)
            gdf = gdf.rename(columns={field: id_name})
            log(f"Chargement mémorisé {layer_type} → {len(gdf)} entités")
            return gdf[[id_name, 'geometry']]
        except Exception as e:
            log(f"Échec fond mémorisé {layer_type} : {e}")
    path, _ = QFileDialog.getOpenFileName(parent, f"Couche {layer_type}", "", "Fichiers géo (*.gpkg *.shp *.geojson)")
    if not path:
        return None
    try:
        gdf = gpd.read_file(path)
    except Exception as e:
        QMessageBox.critical(parent, "Erreur", f"Impossible de lire {path}\n{e}")
        return None
    dialog = QDialog(parent)
    dialog.setWindowTitle(f"Champ ID pour {layer_type}")
    layout = QVBoxLayout()
    combo = QComboBox()
    combo.addItems(list(gdf.columns))
    layout.addWidget(QLabel(f"Champ contenant le code {id_name} :"))
    layout.addWidget(combo)
    btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    btns.accepted.connect(dialog.accept)
    btns.rejected.connect(dialog.reject)
    layout.addWidget(btns)
    dialog.setLayout(layout)
    if dialog.exec_() != QDialog.Accepted:
        return None
    field = combo.currentText()
    settings.setValue(layer_type + "_path", path)
    settings.setValue(layer_type + "_field", field)
    gdf = gdf.rename(columns={field: id_name})
    log(f"Fond {layer_type} mémorisé → champ = {field}")
    return gdf[[id_name, 'geometry']]

# ------------------------------------------------------------------
def process_geo(filtered_data_dir, parent=None):
    csv_files = [f for f in os.listdir(filtered_data_dir) if f.endswith(".csv")]
    if not csv_files:
        warning(parent, "Aucun fichier", "Aucun CSV filtré trouvé.")
        return False
    selected_csv = select_types_to_process(csv_files, parent)
    if not selected_csv:
        return False
    progress = QProgressDialog("Création des couches...", "Annuler", 0, len(selected_csv), parent)
    progress.setWindowTitle("Mes Élus")
    needs_communes = any("maires" in f or "conseillers-municipaux" in f for f in selected_csv)
    needs_epci     = any("conseillers-communautaires" in f for f in selected_csv)
    needs_cantons  = any("conseillers-departementaux" in f for f in selected_csv)
    needs_circo    = any("deputes" in f for f in selected_csv)
    needs_depts    = any(x in " ".join(selected_csv) for x in ["senateurs", "conseillers-departementaux"])
    needs_regions  = "conseillers-regionaux" in " ".join(selected_csv)
    communes_gdf = load_fond("communes", "DEPCOM", parent) if needs_communes else None
    epci_gdf     = load_fond("epci", "SIREN_EPCI", parent) if needs_epci else None
    cantons_gdf  = load_fond("cantons", "CODE_CANTON", parent) if needs_cantons else None
    circo_gdf    = load_fond("circonscriptions", "CODE_CIRCO", parent) if needs_circo else None
    depts_gdf    = load_fond("departements", "DEP", parent) if needs_depts else None
    regions_gdf  = load_fond("regions", "REG", parent) if needs_regions else None
    layers_added = []
    for i, csv_file in enumerate(selected_csv):
        progress.setValue(i)
        progress.setLabelText(csv_file)
        if progress.wasCanceled():
            break
        path = os.path.join(filtered_data_dir, csv_file)
        log(f"\nTraitement : {csv_file}")
        # Lecture intelligente du séparateur
        try:
            with open(path, 'r', encoding='utf-8') as f:
                snippet = f.read(2048)
            sep = ',' if snippet.count(',') > snippet.count(';') else ';'
            df = pd.read_csv(path, sep=sep, encoding="utf-8", low_memory=False, dtype=str)
            log(f"   CSV lu → séparateur '{sep}' | {len(df)} lignes")
        except Exception as e:
            log(f"   ERREUR lecture CSV : {e}")
            continue
        gdf = None
        layer_name = None
        group_var = None
        fn = csv_file.lower()
        # 1. CONSEILLERS COMMUNAUTAIRES
        if "conseillers-communautaires" in fn and epci_gdf is not None:
            if 'N° SIREN' in df.columns:
                df['SIREN_EPCI'] = df['N° SIREN'].str.zfill(9)
                gdf = gpd.GeoDataFrame(df.merge(epci_gdf, on='SIREN_EPCI', how='left'), crs=epci_gdf.crs)
                log(f"   Jointure EPCI → {gdf['geometry'].notna().sum()}/{len(df)}")
                layer_name = "Conseillers communautaires"
                group_var = "SIREN_EPCI"
                geo_cols = ["Code du département", "Libellé du département", "N° SIREN", "Libellé de l'EPCI","SIREN_EPCI", "Libellé.EPCI"]
                elus_cols = [c for c in df.columns if c not in geo_cols + ["geometry"]]
            # === Couche spéciale : Présidents des EPCI (couche unique avec plusieurs features) ===
            if epci_gdf is not None:
                pres_rows = df[df['Libellé de la fonction'].str.contains("Président du conseil communautaire", case=True, na=False)]
                if not pres_rows.empty:
                    vl = QgsVectorLayer("Polygon?crs=epsg:2154", "Président EPCI", "memory")
                    pr = vl.dataProvider()
                    pr.addAttributes([QgsField(n, QVariant.String) for n in pres_rows.columns if n != 'geometry'])
                    vl.updateFields()
                    feats = []
                    for _, pres in pres_rows.iterrows():
                        siren_epci = str(pres['N° SIREN']).zfill(9)
                        epci_geom_row = epci_gdf[epci_gdf['SIREN_EPCI'] == siren_epci]
                        if not epci_geom_row.empty:
                            geom = epci_geom_row.iloc[0].geometry
                            f = QgsFeature(vl.fields())
                            for field in pres_rows.columns:
                                if field != 'geometry':
                                    f.setAttribute(field, str(pres[field]) if pd.notna(pres[field]) else "")
                            f.setGeometry(QgsGeometry.fromWkt(geom.wkt))
                            feats.append(f)
                    if feats:
                        pr.addFeatures(feats)
                        vl.updateExtents()
                        QgsProject.instance().addMapLayer(vl)
                        layers_added.append("Président EPCI")
                        log(f"COUCHE CRÉÉE : Président EPCI → {len(feats)} entités")
                        info(parent, "Succès", f"Présidents EPCI : {len(feats)} entités ajoutées")
            
        # 2. MAIRES & CONSEILLERS MUNICIPAUX
        elif ("maires" in fn or "conseillers-municipaux" in fn) and communes_gdf is not None:
            if 'Code de la commune' in df.columns:
                df['DEPCOM'] = df['Code de la commune'].str.zfill(5)
                gdf = gpd.GeoDataFrame(df.merge(communes_gdf, on='DEPCOM', how='left'), crs=communes_gdf.crs)
                log(f"   Jointure COMMUNES → {gdf['geometry'].notna().sum()}/{len(df)}")
                layer_name = "Maires" if "maires" in fn else "Conseillers municipaux"
                group_var = "DEPCOM"
                geo_cols = ["DEPCOM", "Code du département", "Libellé du département", "Code de la commune", "Libellé de la commune"]
                elus_cols = [c for c in df.columns if c not in geo_cols + ["geometry"]]
        # 3. CONSEILLERS DÉPARTEMENTAUX + PRÉSIDENT (double traitement)
        elif "conseillers-departementaux" in fn:
            # === 1. Couche normale : tous les conseillers départementaux (cantons) ===
            if cantons_gdf is not None and 'Code du canton' in df.columns:
                df_temp = df.copy()
                df_temp['merge_key'] = df_temp['Code du canton'].str.zfill(4)
                key_col = next((c for c in cantons_gdf.columns if c.upper() in ["CODE_CANTON", "CODE_NS", "ID", "CODE"]), None)
                if key_col:
                    cantons_gdf['merge_key'] = cantons_gdf[key_col].astype(str).str.zfill(4)
                    gdf = gpd.GeoDataFrame(df_temp.merge(cantons_gdf[['merge_key', 'geometry']], on='merge_key', how='left'), crs=cantons_gdf.crs)
                    log(f"   Jointure conseillers départementaux → {gdf['geometry'].notna().sum()}/{len(df_temp)}")
                    layer_name = "Conseillers départementaux"
                    group_var = "merge_key"
                    geo_cols = ["merge_key", "Code du département", "Libellé du département", "Code du canton","Libellé du canton"]
                    elus_cols = [c for c in df.columns if c not in geo_cols + ["geometry"]]
            # === 2. Couche spéciale : Présidents des conseils départementaux de la région ===
            if depts_gdf is not None and regions_gdf is not None:
                # Filtrer les présidents de conseils départementaux
                presidents_dept = df[
                    df['Libellé de la fonction'].str.contains('Président du conseil départemental', case=True, na=False)
                ]
                if not presidents_dept.empty:
                    vl = QgsVectorLayer("Polygon?crs=epsg:2154", "Présidents des conseils départementaux", "memory")
                    pr = vl.dataProvider()
                    # Ajouter les champs nécessaires
                    fields_to_add = [c for c in presidents_dept.columns if c != 'geometry']
                    pr.addAttributes([QgsField(n, QVariant.String) for n in fields_to_add])
                    vl.updateFields()
                    feats = []
                    for _, pres in presidents_dept.iterrows():
                        dep_code = str(pres['Code du département']).zfill(2)
                        dept_geom = depts_gdf[depts_gdf['DEP'] == dep_code]
                        if not dept_geom.empty:
                            f = QgsFeature(vl.fields())
                            for field in fields_to_add:
                                f.setAttribute(field, str(pres[field]) if pd.notna(pres[field]) else "")
                            f.setGeometry(QgsGeometry.fromWkt(dept_geom.iloc[0].geometry.wkt))
                            feats.append(f)
                    if feats:
                        pr.addFeatures(feats)
                        vl.updateExtents()
                        QgsProject.instance().addMapLayer(vl)
                        layers_added.append("Président du conseil départemental")
                        log(f"COUCHE CRÉÉE : Président du conseil départemental → {len(feats)} entités")
                        info(parent, "Succès", f"Présidents de départements : {len(feats)} entités ajoutées")

        # 4. DÉPUTÉS
        elif "deputes" in fn and circo_gdf is not None:
            col = next((c for c in df.columns if "circonscription législative" in c.lower()), None)
            if col:
                df['merge_key'] = df[col].astype(str).str.zfill(6).str[-4:]
                key_col = next((c for c in circo_gdf.columns if c.upper() in ["CODE_CIRCO", "CIRCO", "CODE", "ID"]), None)
                if key_col:
                    circo_gdf['merge_key'] = circo_gdf[key_col].astype(str).str.zfill(6).str[-4:]
                    gdf = gpd.GeoDataFrame(df.merge(circo_gdf[['merge_key', 'geometry']], on='merge_key', how='left'), crs=circo_gdf.crs)
                    log(f"   Jointure députés → {gdf['geometry'].notna().sum()}/{len(df)}")
                    layer_name = "Députés"
                    group_var = "merge_key"
                    geo_cols = ["merge_key", "Code du département", "Libellé du département"]
                    elus_cols = [c for c in df.columns if c not in geo_cols + ["geometry"]]
        # 5. SÉNATEURS
        elif "senateurs" in fn and depts_gdf is not None:
            col = next((c for c in df.columns if "départ" in c.lower() and "code" in c.lower()), None)
            if col:
                df['DEP'] = df[col].str.zfill(2)
                key_col = next((c for c in depts_gdf.columns if c.lower() in ["code", "dep", "insee", "code_ns"]), None)
                if key_col:
                    depts_gdf['DEP'] = depts_gdf[key_col].str.zfill(2)
                    gdf = gpd.GeoDataFrame(df.merge(depts_gdf[['DEP', 'geometry']], on='DEP', how='left'), crs=depts_gdf.crs)
                    log(f"   Jointure sénateurs → {gdf['geometry'].notna().sum()}/{len(df)}")
                    layer_name = "Sénateurs"
                    group_var = "DEP"
                    geo_cols = ["DEP", "Code du département","Libellé du département"]
                    elus_cols = [c for c in df.columns if c not in geo_cols + ["geometry"]]
        # 6. CONSEILLERS RÉGIONAUX + PRÉSIDENT (double traitement)
        elif "conseillers-regionaux" in fn:
            # === 1. Couche principale : conseillers régionaux par section départementale ===
            if depts_gdf is not None and 'Code de la section départementale' in df.columns:
                df_temp = df.copy()
                df_temp['merge_key'] = df_temp['Code de la section départementale'].str.zfill(2)
                key_col = next((c for c in depts_gdf.columns if c.lower() in ["code", "dep", "insee", "code_ns"]), None)
                if key_col:
                    depts_gdf['merge_key'] = depts_gdf[key_col].astype(str).str.zfill(2)
                    gdf = gpd.GeoDataFrame(df_temp.merge(depts_gdf[['merge_key', 'geometry']], on='merge_key', how='left'), crs=depts_gdf.crs)
                    log(f" Jointure conseillers régionaux (départements) → {gdf['geometry'].notna().sum()}/{len(df_temp)}")
                    layer_name = "Conseillers régionaux"
                    group_var = "merge_key"
                    geo_cols = ["merge_key", "Code de la région", "Libellé de la région",
                               "Code de la section départementale", "Libellé du département"]
                    elus_cols = [c for c in df.columns if c not in geo_cols + ["geometry"]]

            # === 2. Couche spéciale : Président(e) du conseil régional ===
            # 2. Couche spéciale : Président(e) du conseil régional
            if regions_gdf is not None:
                president_row = df[df['Libellé de la fonction'].str.contains('Président', case=True, na=False) &
                                  df['Libellé de la fonction'].str.contains('conseil régional', case=False, na=False)]
                if not president_row.empty:
                    pres = president_row.iloc[0]
                    reg_code = str(pres['Code de la région']).zfill(2)
                    reg_geom = regions_gdf[regions_gdf['REG'] == reg_code]
                    if not reg_geom.empty:
                        vl = QgsVectorLayer("Polygon?crs=epsg:2154", "Président du Conseil régional", "memory")
                        pr = vl.dataProvider()
                        pr.addAttributes([QgsField(n, QVariant.String) for n in pres.index])
                        vl.updateFields()
                        f = QgsFeature(vl.fields())
                        for field in pres.index:
                            f.setAttribute(field, str(pres[field]) if pd.notna(pres[field]) else "")
                        f.setGeometry(QgsGeometry.fromWkt(reg_geom.iloc[0].geometry.wkt))
                        pr.addFeature(f)
                        vl.updateExtents()
                        QgsProject.instance().addMapLayer(vl)
                        layers_added.append("Président du Conseil régional")
                        log("COUCHE CRÉÉE : Président du Conseil régional")
                        info(parent, "Succès", f"Président de région : {pres['Nom de l\'élu']} {pres['Prénom de l\'élu']}")
                        
        # CRÉATION DE LA COUCHE
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
            log(f"COUCHE CRÉÉE : {layer_name} → {len(feats)} entités")
            info(parent, "Succès", f"{layer_name} → {len(feats)} entités")
        else:
            log(f"ÉCHEC pour {csv_file}")
    progress.setValue(len(selected_csv))
    info(parent, "Terminé !", f"{len(layers_added)} couche(s) créée(s)\nLog → {log_path}")
    return True
