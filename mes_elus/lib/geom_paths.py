# -*- coding: utf-8 -*-
# lib/geom_paths.py
# Gestion des chemins des couches géométriques utilisées pour les jointures
# Version propre et stabilisée – 11/09/2026

import os
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QDialog, QComboBox, QDialogButtonBox, QMessageBox
)
from qgis.PyQt.QtCore import QSettings


# ===========================================================================
# CONSTANTES
# ===========================================================================

# Types de territoires gérés par le plugin
LAYER_TYPES = [
    "communes",
    "cantons",
    "departements",
    "regions",
    "epci",
    "circonscriptions"
]

# Libellés affichés dans l’interface (plus lisibles)
LAYER_LABELS = {
    "communes": "Communes",
    "cantons": "Cantons",
    "departements": "Départements",
    "regions": "Régions",
    "epci": "EPCI",
    "circonscriptions": "Circonscriptions législatives"
}


# ===========================================================================
# FONCTION PRINCIPALE UTILISÉE PAR LE RESTE DU PLUGIN
# ===========================================================================
def get_geom_paths():
    """
    Récupère les chemins et champs identifiants des couches géométriques
    stockés dans les paramètres du plugin (QSettings).

    Retour
    ------
    dict
        {
            "communes": {"path": "...", "field": "..."},
            "cantons":  {"path": "...", "field": "..."},
            ...
        }
        Seuls les types pour lesquels un chemin ET un champ sont définis
        (et dont le fichier existe) sont renvoyés.
    """
    settings = QSettings("MesElusPlugin", "Fonds")
    paths = {}

    for layer_type in LAYER_TYPES:
        path = settings.value(f"{layer_type}_path", None)
        field = settings.value(f"{layer_type}_field", None)

        # On ne conserve que les entrées valides (chemin existant + champ renseigné)
        if path and field and os.path.exists(path):
            paths[layer_type] = {
                "path": path,
                "field": field
            }

    return paths


# ===========================================================================
# ONGLET D’INTERFACE GRAPHIQUE
# ===========================================================================
class GeomPathsTab(QWidget):
    """
    Onglet permettant de visualiser, modifier et réinitialiser
    les chemins des couches géométriques utilisées pour les jointures.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # ----- Titre / explication -----
        title = QLabel(
            "<b>Couches géométriques utilisées pour les jointures</b><br>"
            "Ces couches servent de référentiel géographique (communes, cantons, EPCI…).<br>"
            "Vous pouvez modifier un chemin ou réinitialiser tous les paramètres."
        )
        title.setWordWrap(True)
        self.layout.addWidget(title)

        # ----- Tableau -----
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels([
            "Type de territoire",
            "Chemin du fichier (.shp)",
            "Champ identifiant",
            "Actions"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.layout.addWidget(self.table)

        # ----- Boutons d’action globaux -----
        btn_layout = QHBoxLayout()

        self.refresh_button = QPushButton("Rafraîchir la liste")
        self.refresh_button.clicked.connect(self.update_table)
        btn_layout.addWidget(self.refresh_button)

        self.reset_button = QPushButton("Réinitialiser tous les paramètres")
        self.reset_button.setStyleSheet("background-color: #f8d7da;")  # rouge clair
        self.reset_button.clicked.connect(self.reset_all_settings)
        btn_layout.addWidget(self.reset_button)

        self.layout.addLayout(btn_layout)

        # Chargement initial
        self.update_table()

    # -----------------------------------------------------------------------
    def update_table(self):
        """Met à jour le tableau avec l’état actuel des paramètres."""
        self.table.setRowCount(0)
        paths = get_geom_paths()

        # On affiche tous les types connus, même s’ils ne sont pas encore définis
        for row, layer_type in enumerate(LAYER_TYPES):
            self.table.insertRow(row)

            # Colonne 0 : Type de territoire (libellé lisible)
            label = LAYER_LABELS.get(layer_type, layer_type)
            self.table.setItem(row, 0, QTableWidgetItem(label))

            if layer_type in paths:
                data = paths[layer_type]
                self.table.setItem(row, 1, QTableWidgetItem(data["path"]))
                self.table.setItem(row, 2, QTableWidgetItem(data["field"]))
            else:
                self.table.setItem(row, 1, QTableWidgetItem("— non défini —"))
                self.table.setItem(row, 2, QTableWidgetItem("—"))

            # Colonne 3 : Bouton Modifier
            edit_button = QPushButton("Modifier…")
            edit_button.clicked.connect(
                lambda checked, lt=layer_type: self.edit_path(lt)
            )
            self.table.setCellWidget(row, 3, edit_button)

    # -----------------------------------------------------------------------
    def edit_path(self, layer_type):
        """
        Ouvre les dialogues permettant de choisir un nouveau fichier
        et le champ identifiant associé, puis mémorise le choix.
        """
        settings = QSettings("MesElusPlugin", "Fonds")
        current_path = settings.value(f"{layer_type}_path", "")
        current_field = settings.value(f"{layer_type}_field", "")

        # 1. Sélection du fichier
        new_path, _ = QFileDialog.getOpenFileName(
            self,
            f"Sélectionner la couche « {LAYER_LABELS.get(layer_type, layer_type)} »",
            current_path if current_path else "",
            "Fichiers Shapefile (*.shp);;Tous les fichiers géographiques (*.shp *.gpkg *.geojson)"
        )

        if not new_path:
            return  # Annulé

        # 2. Lecture des champs disponibles
        try:
            import geopandas as gpd
            gdf = gpd.read_file(new_path)
            fields = list(gdf.columns)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Erreur de lecture",
                f"Impossible de lire le fichier :\n{new_path}\n\n{e}"
            )
            return

        # 3. Choix du champ identifiant
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Champ identifiant – {LAYER_LABELS.get(layer_type, layer_type)}")
        layout = QVBoxLayout(dialog)

        layout.addWidget(QLabel(
            f"Sélectionnez le champ qui contient le code unique\n"
            f"pour le territoire « {LAYER_LABELS.get(layer_type, layer_type)} » :"
        ))

        combo = QComboBox()
        combo.addItems(fields)
        if current_field in fields:
            combo.setCurrentText(current_field)
        layout.addWidget(combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec_() != QDialog.Accepted:
            return  # Annulé

        new_field = combo.currentText()

        # 4. Enregistrement dans les paramètres du plugin
        settings.setValue(f"{layer_type}_path", new_path)
        settings.setValue(f"{layer_type}_field", new_field)

        QMessageBox.information(
            self,
            "Paramètre enregistré",
            f"La couche « {LAYER_LABELS.get(layer_type, layer_type)} » a été mise à jour.\n\n"
            f"Fichier : {new_path}\n"
            f"Champ   : {new_field}"
        )

        # 5. Rafraîchissement de l’affichage
        self.update_table()

    # -----------------------------------------------------------------------
    def reset_all_settings(self):
        """
        Supprime tous les paramètres de chemins/champs stockés.
        Permet de tester le plugin dans les conditions d’une première utilisation.
        """
        reply = QMessageBox.question(
            self,
            "Réinitialiser les paramètres",
            "Voulez-vous vraiment supprimer TOUS les chemins et champs enregistrés ?\n\n"
            "Le plugin se comportera ensuite comme lors d’une première utilisation\n"
            "(il demandera de sélectionner chaque couche).",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        settings = QSettings("MesElusPlugin", "Fonds")

        for layer_type in LAYER_TYPES:
            settings.remove(f"{layer_type}_path")
            settings.remove(f"{layer_type}_field")

        QMessageBox.information(
            self,
            "Réinitialisation effectuée",
            "Tous les paramètres de couches géométriques ont été effacés.\n"
            "Vous êtes maintenant dans les conditions d’une première utilisation."
        )

        self.update_table()