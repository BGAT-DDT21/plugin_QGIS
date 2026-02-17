# -*- coding: utf-8 -*-
# lib/apply_styles.py
# Application automatique des styles QML du dossier "styles"

import json
import os
import pandas as pd
from qgis.core import QgsApplication,QgsProject, QgsMessageLog, QgsRectangle
from qgis.utils import iface
from PyQt5.QtWidgets import QMessageBox

def apply_all_styles(parent=None, output_dir=None):
    plugin_dir = os.path.dirname(os.path.dirname(__file__))  # remonte au dossier plugin
    styles_dir = os.path.join(plugin_dir, "styles")
    if not os.path.exists(styles_dir):
        QMessageBox.critical(parent, "Erreur", f"Dossier 'styles' non trouvé :\n{styles_dir}")
        return

    # Correspondance nom de couche → fichier QML
    mapping = {
        "maires": "maires-mai.qml",
        "conseillers municipaux": "conseillers-municipaux-cm.qml",
        "conseillers communautaires": "conseillers-communautaires-epci.qml",
        "conseillers départementaux": "conseillers-departementaux-cd.qml",
        "conseillers régionaux": "conseillers-regionaux-cr.qml",
        "députés": "deputes-dep.qml",
        "sénateurs": "senateurs-sen.qml",
        "présidents des conseils départementaux": "Président_Conseil_Départemental.qml",
        "président du conseil régional": "Président_Conseil_Régional.qml",
        "président epci": "President_epci.qml",
    }

    root = QgsProject.instance().layerTreeRoot()
    
   # Lire le fichier JSON contenant les informations du territoire sélectionné
    territory_info = {}
    try:
        # Utiliser le même chemin que dans main_plugin.py
        json_path = os.path.join(output_dir, "selected_territory.json")
        
        if os.path.exists(json_path):
            with open(json_path, "r") as f:
                territory_info = json.load(f)
        else:
            QMessageBox.warning(
                parent,
                "Fichier non trouvé",
                f"Le fichier JSON n'existe pas au chemin : {json_path}"
            )
    except Exception as e:
        QMessageBox.critical(
            parent,
            "Erreur",
            f"Erreur lors de la lecture du fichier de territoire : {e}"
        )
        
    # Importer les dictionnaires de noms de territoires
    from .select_perimeter import DEPARTEMENTS, REGIONS
    
    # Déterminer le nom du territoire
    if territory_info:
        territory_type = territory_info.get("territory_type")
        selected_code = territory_info.get("selected_code")

        if territory_type == "Département":
            territory_name = DEPARTEMENTS.get(selected_code, f"Département {selected_code}")
        elif territory_type == "Région":
            territory_name = REGIONS.get(selected_code, f"Région {selected_code}")

    if not territory_info:
        territory_name = "Territoire inconnu"
        year = pd.Timestamp.now().year
        group_name = f"Élus {territory_name} {year}"

    year = territory_info.get("year", pd.Timestamp.now().year) if territory_info else pd.Timestamp.now().year
    group_name = f"Élus {territory_name} {year}"

 
    # Création du groupe
    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup(group_name)
    if not group:
        group = root.addGroup(group_name)
        
    count = 0
    for layer in list(QgsProject.instance().mapLayers().values()):
        layer_name = layer.name().lower()

        qml_file = None
        for key, filename in mapping.items():
            if key in layer_name:
                qml_file = os.path.join(styles_dir, filename)
                break

        if qml_file and os.path.exists(qml_file):
            layer.loadNamedStyle(qml_file)
            layer.triggerRepaint()
            count += 1

            # Déplacement dans le groupe
            node = root.findLayer(layer.id())
            if node and node.parent() != group:
                clone = node.clone()
                group.insertChildNode(0, clone)
                root.removeChildNode(node)

    # Zoom auto sur le groupe
    if group:
        extent = QgsRectangle()
        for layer in group.findLayers():
            if layer.layer().extent().isFinite():
                extent.combineExtentWith(layer.layer().extent())
        iface.mapCanvas().setExtent(extent)
        iface.mapCanvas().refresh()

    QMessageBox.information(
        parent,
        "Succès total !",
        f"{count} couche(s) stylisée(s) avec succès !\n\n"
        f"Groupe « {group_name} » créé\n"
        f"Zoom automatique effectué"
    )