# -*- coding: utf-8 -*-
"""
Mes_élus/lib/select_perimeter.py
Calcul du périmètre mitoyen (départements + régions)
Compatible ADMIN_EXPRESS (colonnes INSEE_DEP / INSEE_REG)
"""

import geopandas as gpd
from qgis.PyQt.QtWidgets import QDialog, QFormLayout, QComboBox, QDialogButtonBox
from qgis.core import QgsMessageLog, Qgis

# -------------------------------------------------
# 1. Listes des territoires (complètes)
# -------------------------------------------------
DEPARTEMENTS = {
    "01": "Ain", "02": "Aisne", "03": "Allier", "04": "Alpes-de-Haute-Provence", "05": "Hautes-Alpes",
    "06": "Alpes-Maritimes", "07": "Ardèche", "08": "Ardennes", "09": "Ariège", "10": "Aube",
    "11": "Aude", "12": "Aveyron", "13": "Bouches-du-Rhône", "14": "Calvados", "15": "Cantal",
    "16": "Charente", "17": "Charente-Maritime", "18": "Cher", "19": "Corrèze", "2A": "Corse-du-Sud",
    "2B": "Haute-Corse", "21": "Côte-d'Or", "22": "Côtes-d'Armor", "23": "Creuse", "24": "Dordogne",
    "25": "Doubs", "26": "Drôme", "27": "Eure", "28": "Eure-et-Loir", "29": "Finistère",
    "30": "Gard", "31": "Haute-Garonne", "32": "Gers", "33": "Gironde", "34": "Hérault",
    "35": "Ille-et-Vilaine", "36": "Indre", "37": "Indre-et-Loire", "38": "Isère", "39": "Jura",
    "40": "Landes", "41": "Loir-et-Cher", "42": "Loire", "43": "Haute-Loire", "44": "Loire-Atlantique",
    "45": "Loiret", "46": "Lot", "47": "Lot-et-Garonne", "48": "Lozère", "49": "Maine-et-Loire",
    "50": "Manche", "51": "Marne", "52": "Haute-Marne", "53": "Mayenne", "54": "Meurthe-et-Moselle",
    "55": "Meuse", "56": "Morbihan", "57": "Moselle", "58": "Nièvre", "59": "Nord",
    "60": "Oise", "61": "Orne", "62": "Pas-de-Calais", "63": "Puy-de-Dôme", "64": "Pyrénées-Atlantiques",
    "65": "Hautes-Pyrénées", "66": "Pyrénées-Orientales", "67": "Bas-Rhin", "68": "Haut-Rhin", "69": "Rhône",
    "70": "Haute-Saône", "71": "Saône-et-Loire", "72": "Sarthe", "73": "Savoie", "74": "Haute-Savoie",
    "75": "Paris", "76": "Seine-Maritime", "77": "Seine-et-Marne", "78": "Yvelines", "79": "Deux-Sèvres",
    "80": "Somme", "81": "Tarn", "82": "Tarn-et-Garonne", "83": "Var", "84": "Vaucluse",
    "85": "Vendée", "86": "Vienne", "87": "Haute-Vienne", "88": "Vosges", "89": "Yonne",
    "90": "Territoire de Belfort", "91": "Essonne", "92": "Hauts-de-Seine", "93": "Seine-Saint-Denis",
    "94": "Val-de-Marne", "95": "Val-d'Oise",
    "971": "Guadeloupe", "972": "Martinique", "973": "Guyane", "974": "La Réunion", "976": "Mayotte"
}

REGIONS = {
    "01": "Guadeloupe", "02": "Martinique", "03": "Guyane", "04": "La Réunion", "06": "Mayotte",
    "11": "Île-de-France", "24": "Centre-Val de Loire", "27": "Bourgogne-Franche-Comté",
    "28": "Normandie", "32": "Hauts-de-France", "44": "Grand Est", "52": "Pays de la Loire",
    "53": "Bretagne", "75": "Nouvelle-Aquitaine", "76": "Occitanie", "84": "Auvergne-Rhône-Alpes",
    "93": "Provence-Alpes-Côte d’Azur", "94": "Corse"
}

# Mapping région → départements
REGION_TO_DEPTS = {
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

# -------------------------------------------------
# 2. Dialogue de sélection
# -------------------------------------------------
def select_perimeter_dialog(parent=None):
    dlg = QDialog(parent)
    dlg.setWindowTitle("Sélection du territoire de travail")
    layout = QFormLayout(dlg)

    type_cb = QComboBox()
    type_cb.addItems(["Département", "Région"])
    layout.addRow("Type :", type_cb)

    choice_cb = QComboBox()
    layout.addRow("Territoire :", choice_cb)

    def update_choices():
        choice_cb.clear()
        if type_cb.currentText() == "Département":
            items = [f"{code} – {nom}" for code, nom in sorted(DEPARTEMENTS.items(), key=lambda x: x[1])]
        else:
            items = [f"{code} – {nom}" for code, nom in sorted(REGIONS.items(), key=lambda x: x[1])]
        choice_cb.addItems(items)

    type_cb.currentTextChanged.connect(update_choices)
    update_choices()

    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addRow(buttons)

    if dlg.exec_() != QDialog.Accepted:
        return None, None

    territory_type = type_cb.currentText()
    selected_code = choice_cb.currentText().split(" – ")[0]
    return territory_type, selected_code


# -------------------------------------------------
# 3. Calcul du périmètre (ADMIN_EXPRESS compatible)
# -------------------------------------------------
def get_perimeter(territory_type: str, selected_code: str,
                  departements_path: str, regions_path: str):
    """
    Retourne (liste_depts, liste_regions)
    Fonctionne avec ADMIN_EXPRESS (colonnes INSEE_DEP et INSEE_REG)
    """
    dep_gdf = gpd.read_file(departements_path).to_crs(epsg=2154)
    reg_gdf = gpd.read_file(regions_path).to_crs(epsg=2154)

    if territory_type == "Département":
        # ADMIN_EXPRESS utilise INSEE_DEP
        selected_dep = dep_gdf[dep_gdf['INSEE_DEP'] == selected_code]
        if selected_dep.empty:
            raise ValueError(f"Département {selected_code} non trouvé dans le fichier départements")

        # Départements mitoyens
        neighbors_dep = dep_gdf[dep_gdf.touches(selected_dep.geometry.unary_union)]
        depts = [selected_code] + neighbors_dep['INSEE_DEP'].tolist()

        # Région du département sélectionné
        dept_to_reg = {d: reg for reg, depts_list in REGION_TO_DEPTS.items() for d in depts_list}
        selected_reg = dept_to_reg.get(selected_code)
        if not selected_reg:
            raise ValueError(f"Région non trouvée pour le département {selected_code}")

        selected_reg_gdf = reg_gdf[reg_gdf['INSEE_REG'] == selected_reg]
        neighbors_reg = reg_gdf[reg_gdf.touches(selected_reg_gdf.geometry.unary_union)]
        regions = [selected_reg] + neighbors_reg['INSEE_REG'].tolist()

    else:  # Région
        selected_reg_gdf = reg_gdf[reg_gdf['INSEE_REG'] == selected_code]
        if selected_reg_gdf.empty:
            raise ValueError(f"Région {selected_code} non trouvée dans le fichier régions")

        neighbors_reg = reg_gdf[reg_gdf.touches(selected_reg_gdf.geometry.unary_union)]
        regions = [selected_code] + neighbors_reg['INSEE_REG'].tolist()

        depts = REGION_TO_DEPTS.get(selected_code, [])
        for r in regions:
            depts.extend(REGION_TO_DEPTS.get(r, []))
        depts = list(set(depts))
        
    territory_name = DEPARTEMENTS.get(selected_code) if territory_type == "Département" else REGIONS.get(selected_code)

 
    QgsMessageLog.logMessage(
        f"Périmètre → Départements : {sorted(depts)} | Régions : {sorted(regions)}",
        "Mes Élus", Qgis.Info
    )
    
    if dlg.exec_() != QDialog.Accepted:
        return None, None

    territory_type = type_cb.currentText()
    selected_code = choice_cb.currentText().split(" – ")[0]

    # Message de confirmation
    territory_name = choice_cb.currentText().split(" – ")[1]
    QMessageBox.information(
        dlg,
        "Confirmation",
        f"Vous avez sélectionné :\n{territory_type} {territory_name}"
    )

    return territory_type, selected_code
    return depts, regions