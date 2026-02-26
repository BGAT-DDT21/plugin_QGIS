# -*- coding: utf-8 -*-
"""
generate_default_qml.py
Génère des fichiers .qml par défaut pour toutes les couches RNE.
Utilisé dans l'onglet "Mise en forme" si les .qml sont absents.
"""

import os
from qgis.core import (
    QgsSymbol, QgsSingleSymbolRenderer, QgsMarkerSymbol, QgsSimpleMarkerSymbolLayer,
    QgsTextFormat, QgsTextBufferSettings, QgsBackgroundSettings, QgsLabeling,
    QgsPalLayerSettings, QgsProperty, QgsVectorLayerSimpleLabeling
)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QMessageBox


def create_default_symbol(color, size=3.0, shape="circle", outline_width=0.4):
    """Crée un symbole simple avec couleur, taille, forme"""
    symbol = QgsMarkerSymbol()
    layer = QgsSimpleMarkerSymbolLayer(shape)
    layer.setColor(QColor(color))
    layer.setStrokeColor(QColor("black"))
    layer.setStrokeWidth(outline_width)
    layer.setSize(size)
    symbol.changeSymbolLayer(0, layer)
    return symbol


def create_label_settings(field, font_size=10, color="black", buffer=True):
    """Crée les paramètres d'étiquetage"""
    label = QgsPalLayerSettings()
    label.fieldName = field
    label.enabled = True

    text_format = QgsTextFormat()
    text_format.setFont(text_format.font().fromString(f"Arial,{font_size},0,5,0"))
    text_format.setColor(QColor(color))
    text_format.setSize(font_size)

    if buffer:
        buffer = QgsTextBufferSettings()
        buffer.setEnabled(True)
        buffer.setSize(1.0)
        buffer.setColor(QColor("white"))
        text_format.setBuffer(buffer)

    label.setFormat(text_format)
    return label


def generate_default_qml_files(output_dir, iface):
    """
    Génère des .qml par défaut dans output_dir si absents.
    Retourne True si au moins un .qml a été créé.
    """
    if not output_dir or not os.path.exists(output_dir):
        QMessageBox.critical(iface.mainWindow(), "Erreur", "Dossier de sortie invalide.")
        return False

    gpkg_path = os.path.join(output_dir, "rne_elus.gpkg")
    if not os.path.exists(gpkg_path):
        QMessageBox.warning(iface.mainWindow(), "Info", "GeoPackage introuvable. Les .qml seront générés à la prochaine création.")
        return False

    # === Configuration des styles par couche ===
    styles_config = {
        "maires-mai": {
            "color": "#d7191c",  # Rouge foncé
            "size": 4.5,
            "shape": "star",
            "label_field": "Nom de l'élu",
            "label2_field": "Maire",
            "font_size": 11
        },
        "conseillers-municipaux-cm": {
            "color": "#fdae61",  # Orange clair
            "size": 2.8,
            "shape": "circle",
            "label_field": "Nom de l'élu",
            "font_size": 9
        },
        "conseillers-departementaux-cd": {
            "color": "#2c7bb6",  # Bleu
            "size": 3.2,
            "shape": "square",
            "label_field": "Nom de l'élu",
            "font_size": 10
        },
        "deputes-dep": {
            "color": "#1a9850",  # Vert
            "size": 4.0,
            "shape": "triangle",
            "label_field": "Nom de l'élu",
            "font_size": 10
        },
        "senateurs-sen": {
            "color": "#7b3294",  # Violet
            "size": 4.2,
            "shape": "diamond",
            "label_field": "Nom de l'élu",
            "font_size": 11
        },
        "conseillers-regionaux-cr": {
            "color": "#e78ac3",  # Rose
            "size": 3.0,
            "shape": "pentagon",
            "label_field": "Nom de l'élu",
            "font_size": 9
        },
        "conseillers-communautaires-epci": {
            "color": "#a6d96a",  # Vert clair
            "size": 2.5,
            "shape": "circle",
            "label_field": "Nom de l'élu",
            "font_size": 8
        },
        # Président spécial (même couche que conseillers-regionaux-cr)
        "Président_Conseil_Régional": {
            "color": "#d7191c",  # Rouge
            "size": 6.0,
            "shape": "star",
            "label_field": "Nom de l'élu",
            "label2_field": "Président du Conseil Régional",
            "font_size": 12
        },
        "President_epci": {
            "color": "#d7191c",
            "size": 5.0,
            "shape": "star",
            "label_field": "Nom de l'élu",
            "label2_field": "Président EPCI",
            "font_size": 11
        }
    }

    created = 0
    for layer_name, config in styles_config.items():
        qml_path = os.path.join(output_dir, f"{layer_name}.qml")

        # Ne générer que si le fichier n'existe pas
        if os.path.exists(qml_path):
            continue

        # Vérifier que la couche existe dans le GeoPackage
        uri = f"{gpkg_path}|layername={layer_name.split('_')[0]}"
        if "Président" in layer_name:
            uri = f"{gpkg_path}|layername={layer_name.split('_')[0].replace('President', 'conseillers')}"
        layer = QgsVectorLayer(uri, layer_name, "ogr")
        if not layer.isValid():
            continue

        # === Symbole ===
        symbol = create_default_symbol(
            color=config["color"],
            size=config["size"],
            shape=config.get("shape", "circle"),
            outline_width=0.5
        )
        renderer = QgsSingleSymbolRenderer(symbol)
        layer.setRenderer(renderer)

        # === Étiquettes ===
        if "label_field" in config:
            label = create_label_settings(
                field=config["label_field"],
                font_size=config["font_size"],
                color="black",
                buffer=True
            )
            if "label2_field" in config:
                # Étiquette sur deux lignes
                label.fieldName = f"concat(\"{config['label_field']}\", '\\n', \"{config['label2_field']}\")"
            labeling = QgsVectorLayerSimpleLabeling(label)
            layer.setLabeling(labeling)
            layer.setLabelsEnabled(True)

        # === Sauvegarde .qml ===
        try:
            layer.saveNamedStyle(qml_path)
            created += 1
        except Exception as e:
            print(f"Erreur sauvegarde {qml_path} : {e}")

    if created > 0:
        QMessageBox.information(
            iface.mainWindow(),
            "Styles générés",
            f"{created} fichier(s) .qml par défaut créés dans :\n{output_dir}"
        )
    return created > 0