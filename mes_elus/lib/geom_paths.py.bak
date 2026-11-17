# -*- coding: utf-8 -*-
# lib/geom_paths.py
# Script pour gérer l'affichage et la modification des chemins des couches géométriques

from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QFileDialog, QDialog, QVBoxLayout, QComboBox, QDialogButtonBox
)
from qgis.PyQt.QtCore import Qt, QSettings
import os

def get_geom_paths():
    """Récupère les chemins des couches géométriques depuis QSettings."""
    settings = QSettings("MesElusPlugin", "Fonds")
    paths = {}

    # Liste des types de couches possibles
    layer_types = ["communes", "cantons", "departements", "regions", "epci", "circonscriptions"]

    for layer_type in layer_types:
        path = settings.value(f"{layer_type}_path", None)
        field = settings.value(f"{layer_type}_field", None)
        if path and field:
            paths[layer_type] = {
                "path": path,
                "field": field
            }

    return paths

class GeomPathsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout()
        self.table = QTableWidget()
        self.table.setColumnCount(4)  # Ajout d'une colonne pour le bouton "Modifier"
        self.table.setHorizontalHeaderLabels(["Type de couche", "Chemin du fichier", "Champ identifiant", "Actions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.layout.addWidget(self.table)

        # Bouton pour rafraîchir la liste
        self.refresh_button = QPushButton("Rafraîchir la liste des chemins")
        self.refresh_button.clicked.connect(self.update_table)
        self.layout.addWidget(self.refresh_button)

        self.setLayout(self.layout)
        self.update_table()

    def update_table(self):
        """Met à jour le tableau avec les chemins des couches géométriques."""
        self.table.setRowCount(0)
        paths = get_geom_paths()

        for row, (layer_type, data) in enumerate(paths.items()):
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(layer_type))
            self.table.setItem(row, 1, QTableWidgetItem(data["path"]))
            self.table.setItem(row, 2, QTableWidgetItem(data["field"]))

            # Ajout du bouton "Modifier"
            edit_button = QPushButton("Modifier")
            edit_button.clicked.connect(lambda _, lt=layer_type: self.edit_path(lt))
            self.table.setCellWidget(row, 3, edit_button)

        if not paths:
            self.table.setRowCount(1)
            self.table.setItem(0, 0, QTableWidgetItem("Aucun chemin enregistré"))
            self.table.setSpan(0, 0, 1, 4)  # Étendre sur toutes les colonnes

    def edit_path(self, layer_type):
        """Ouvre une boîte de dialogue pour modifier le chemin et le champ identifiant."""
        settings = QSettings("MesElusPlugin", "Fonds")
        current_path = settings.value(f"{layer_type}_path", "")
        current_field = settings.value(f"{layer_type}_field", "")

        # Boîte de dialogue pour sélectionner un nouveau fichier
        new_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Sélectionner le fichier pour {layer_type}",
            current_path,
            "Fichiers géo (*.gpkg *.shp *.geojson)"
        )

        if not new_path:
            return  # Annulé par l'utilisateur

        # Charger le fichier pour obtenir la liste des champs
        try:
            import geopandas as gpd
            gdf = gpd.read_file(new_path)
            fields = list(gdf.columns)
        except Exception as e:
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Erreur", f"Impossible de lire le fichier : {e}")
            return

        # Boîte de dialogue pour sélectionner le champ identifiant
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Champ identifiant pour {layer_type}")
        layout = QVBoxLayout()

        combo = QComboBox()
        combo.addItems(fields)
        if current_field in fields:
            combo.setCurrentText(current_field)

        layout.addWidget(QLabel(f"Sélectionner le champ identifiant pour {layer_type} :"))
        layout.addWidget(combo)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        layout.addWidget(btns)

        dialog.setLayout(layout)

        if dialog.exec_() != QDialog.Accepted:
            return  # Annulé par l'utilisateur

        new_field = combo.currentText()

        # Mettre à jour QSettings
        settings.setValue(f"{layer_type}_path", new_path)
        settings.setValue(f"{layer_type}_field", new_field)

        # Rafraîchir le tableau
        self.update_table()
