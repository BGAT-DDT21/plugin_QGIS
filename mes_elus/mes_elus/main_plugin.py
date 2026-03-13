# -*- coding: utf-8 -*-
# main_plugin.py
# Modifié le 17/12/2025
import os
import json
import pandas as pd

from qgis.PyQt.QtWidgets import (
    QAction, QCheckBox,QDialog, QDialogButtonBox, QTabWidget, QWidget, QVBoxLayout, QListWidget, QComboBox, QListWidgetItem,
    QLabel, QLineEdit, QPushButton, QTextEdit, QSizePolicy, QFileDialog, QMessageBox, QHBoxLayout, QScrollArea
)
from qgis.PyQt.QtCore import Qt, QSettings
from qgis.PyQt.QtGui import (QIcon,QPixmap)
from qgis.core import Qgis, QgsMessageLog, QgsProject
from qgis.utils import pluginDirectory

from .lib.download_rne import download_and_filter
from .lib.process_rne_geo import process_geo
from .lib.geom_paths import GeomPathsTab
from .lib.select_perimeter import select_perimeter_dialog, DEPARTEMENTS, REGIONS
from .lib.apply_styles import apply_all_styles
from .lib.utils import info, warning


logo_label = QLabel()
logo_path = os.path.join(pluginDirectory("mes_elus"), "resources", "logo.png")
logo_label.setPixmap(QPixmap(logo_path).scaled(300, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))

class MesElusPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.output_dir = None
        self.dialog = None
        self.selected_territory = None  # Variable pour stocker le territoire sélectionné
        self.lbl_dossier = None  # <-- Ajoute cette ligne
        


    def initGui(self):
        icon = QIcon(os.path.join(self.plugin_dir, "icon.png"))
        self.action = QAction(icon, "Mes Élus", self.iface.mainWindow())
        self.action.triggered.connect(self.show_dialog)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&Mes Élus", self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu("&Mes Élus", self.action)
            self.iface.removeToolBarIcon(self.action)

    # ==================================================================
    # ONGLETS
    # ==================================================================
    
    def create_tab_accueil(self):
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # Logo
        logo_label = QLabel()
        logo_path = os.path.join(pluginDirectory("mes_elus"), "ressources", "logo.png")
        if os.path.exists(logo_path):
            logo_label.setPixmap(QPixmap(logo_path).scaled(400, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo_label)

        # Texte d’accueil
        text = QTextEdit()
        text.setReadOnly(True)
        text.setMinimumHeight(400)          # ← hauteur fixe suffisante
        text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        text.setHtml("""
        <h1 style="color:#d4380d">Mes Élus</h1>
        <p>Plugin complet pour charger, géocoder et mettre en forme <b>les données du Répertoire National des Élus (RNE)</b> de votre département ou région.</p>
        <h3>Fonctionnalités</h3>
        <ul>
            <li> Étape 1 : Téléchargement filtré du RNE (seulement votre territoire)</li>
            <li> Étape 2 : Géocodage automatique (attribution des géométries des territoires d'exercice des mandats des types d'élus sélectionnés)</li>
            <li> Étape 3 : Mise en forme en 1 clic avec Groupe thématique + zoom automatique</li>
            <li> Étape 4 : Export en gpkg des couches créées avec leur mise en forme </li>
            <li>Compatible RNE 2026</li>
        </ul>
        """)
        layout.addWidget(text)
        tab.setLayout(layout)
        
        return tab



    def create_tab_configuration(self):
        tab = QWidget()
        layout = QVBoxLayout()
        layout.setSpacing(15)

        # --- 1. Répertoire de travail ---
        hbox_dossier = QHBoxLayout()
        self.lbl_dossier = QLabel("Aucun dossier sélectionné")
        self.lbl_dossier.setStyleSheet("QLabel { padding: 10px; background:#f0f0f0; border-radius:5px; }")
        hbox_dossier.addWidget(self.lbl_dossier)

        # Bouton pour choisir le dossier
        btn_dossier = QPushButton("Choisir le dossier de travail")
        btn_dossier.clicked.connect(self.select_output_directory)
        hbox_dossier.addWidget(btn_dossier)

        # Ajouter une description sous le bouton
        description_label = QLabel("Les données du RNE y seront téléchargées")
        description_label.setStyleSheet("color: #555; font-style: italic;")
        layout.addLayout(hbox_dossier)
        layout.addWidget(description_label)  # Ajoute le texte sous le bouton

        # --- 2. Chemins des géométries ---
        self.geom_paths_tab = GeomPathsTab()  # Réutilisation de la classe existante
        layout.addWidget(QLabel("<h3>Chemins des couches géométriques</h3>"))
        layout.addWidget(self.geom_paths_tab)

        # --- 3. Configuration du proxy ---
        layout.addWidget(QLabel("<h3>Configuration du proxy</h3>"))

        hbox_proxy = QHBoxLayout()
        self.proxy_checkbox = QCheckBox("Utiliser un proxy")
        self.proxy_checkbox.stateChanged.connect(self.toggle_proxy)
        hbox_proxy.addWidget(self.proxy_checkbox)

        self.proxy_input = QLineEdit()
        self.proxy_input.setPlaceholderText("http://monproxy:8080")
        self.proxy_input.setEnabled(False)
        hbox_proxy.addWidget(self.proxy_input)

        btn_save_proxy = QPushButton("Enregistrer")
        btn_save_proxy.clicked.connect(self.save_proxy_config)
        hbox_proxy.addWidget(btn_save_proxy)
        layout.addLayout(hbox_proxy)
        
         # --- 4. Bouton de réinitialisation ---
        btn_reset = QPushButton("Réinitialiser les paramètres")
        btn_reset.setStyleSheet("background-color: #ff6b6b; color: white; font-weight: bold;")
        btn_reset.clicked.connect(self.reset_settings)
        layout.addWidget(btn_reset)

        # Charger la configuration actuelle du proxy
        self.load_proxy_config()

        layout.addStretch()
        tab.setLayout(layout)
        return tab

    
    
    def create_tab_telechargement(self):
        tab = QWidget()
        layout = QVBoxLayout()
        btn = QPushButton("Télécharger et filtrer les données")
        btn.clicked.connect(self.run_download)
        layout.addWidget(QLabel("<h2>Étape 1 : Téléchargement</h2><p>Lance le téléchargement filtré du RNE selon votre territoire.</p>"))
        layout.addWidget(btn)
        layout.addStretch()
        tab.setLayout(layout)
        return tab
        
    def create_tab_traitement(self):
        tab = QWidget()
        layout = QVBoxLayout()
        btn = QPushButton("Créer les couches géographiques")
        btn.clicked.connect(self.run_processing)
        layout.addWidget(QLabel("<h2>Étape 2 : Création des couches</h2><p>Géocode automatiquement tous les élus sélectionnés.</p>"))
        layout.addWidget(btn)
        layout.addStretch()  # Ajout des parenthèses

        tab.setLayout(layout)
        
        return tab


    def create_tab_styles(self):
        tab = QWidget()
        layout = QVBoxLayout()
        lbl = QLabel("""
        <h2>Étape 3 : Mise en forme automatique</h2>
        <p>Un seul clic pour appliquer des styles à toutes les couches :</p>
        <ul>
            <li>Maires → contours des communes en pointillés + étiquette</li>
            <li>Députés → délimitation en rouge des circonscriptions + étiquette</li>
            <li>Sénateurs → délimitation en noir du département + étiquette</li>
            <li>Président du Département → délimitation en bleu du département + étiquette</li>
            <li>Conseillers départementaux → délimitation en bleu des cantons + étiquette </li>
            <li>Conseillers communautaires → vert EPCI</li>
            <li>Conseillers municipaux → point gris discret</li>
            <li>Conseillers régionaux → polygone département</li>
        </ul>
        <p><b>Groupe créé + zoom automatique</b></p>
        """)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        btn = QPushButton(
            "APPLIQUER LES STYLES\n"
            "(styles modifiables dans le répertoire styles du plugin)"
        )
        btn.setStyleSheet("""
            QPushButton {
                font-size: 18pt;
                padding: 20px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0077B6, stop:1 #003366);
                color: white;
                font-weight: bold;
                border-radius: 15px;
            }
        """)
        btn.clicked.connect(lambda: apply_all_styles(self.iface.mainWindow(), self.output_dir))
        layout.addWidget(btn)
        layout.addStretch()
        tab.setLayout(layout)
        return tab
        
    def create_tab_export(self):
        tab = QWidget()
        layout = QVBoxLayout()

        # Texte d'introduction
        lbl = QLabel("""
        <h2>Étape 4 : Export des données sur mes élus</h2>
        <p>Sélectionnez les couches à exporter et le format de sortie :</p>
        """)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        # Bouton pour rafraîchir la liste des couches
        refresh_button = QPushButton("Rafraîchir la liste des couches")
        refresh_button.clicked.connect(self.update_layer_list)
        layout.addWidget(refresh_button)

        # Liste des couches disponibles (dans un QScrollArea)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        self.layer_list_widget = QListWidget()
        scroll_layout.addWidget(self.layer_list_widget)
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)

        # Bouton pour sélectionner le dossier de destination
        self.select_dir_button = QPushButton("Sélectionner le dossier de destination")
        self.select_dir_button.clicked.connect(self.select_output_directory)
        layout.addWidget(self.select_dir_button)

        # Bouton pour lancer l'export
        self.export_button = QPushButton("Exporter")
        self.export_button.clicked.connect(self.run_export)
        layout.addWidget(self.export_button)

        # Ajouter un espace flexible pour pousser les boutons vers le haut
        layout.addStretch()

        tab.setLayout(layout)
        self.update_layer_list()
        return tab


    # ==================================================================
    # DIALOGUE PRINCIPAL
    # ==================================================================
    def show_dialog(self):
        if self.dialog is None:
            self.dialog = QDialog(self.iface.mainWindow())
            self.dialog.setWindowTitle("Mes Élus")
            self.dialog.setMinimumSize(850, 600)

            tab_widget = QTabWidget()
            tab_widget.addTab(self.create_tab_accueil(), "Accueil")
            tab_widget.addTab(self.create_tab_configuration(), "Configuration")  # Nouvel onglet
            tab_widget.addTab(self.create_tab_telechargement(), "Téléchargement")
            tab_widget.addTab(self.create_tab_traitement(), "Création des couches")
            tab_widget.addTab(self.create_tab_styles(), "Mise en forme")
            tab_widget.addTab(self.create_tab_export(), "Export")

            layout = QVBoxLayout()
            layout.addWidget(tab_widget)
            self.dialog.setLayout(layout)
            
            # Charger le chemin du dossier de travail
            self.load_output_dir()

        self.dialog.show()
        self.dialog.raise_()


    # ==================================================================
    # CONFIGURATION
    # ==================================================================

    def toggle_proxy(self, state):
        """Active/désactive le champ de saisie du proxy."""
        self.proxy_input.setEnabled(state == Qt.Checked)

    def load_proxy_config(self):
        """Charge la configuration du proxy depuis QSettings."""
        settings = QSettings("MesElusPlugin", "Proxy")
        proxy_url = settings.value("proxy_url", "")
        use_proxy = settings.value("use_proxy", False, type=bool)
        self.proxy_checkbox.setChecked(use_proxy)
        self.proxy_input.setText(proxy_url)
        self.proxy_input.setEnabled(use_proxy)

    def save_proxy_config(self):
        """Enregistre la configuration du proxy dans QSettings."""
        settings = QSettings("MesElusPlugin", "Proxy")
        settings.setValue("use_proxy", self.proxy_checkbox.isChecked())
        settings.setValue("proxy_url", self.proxy_input.text())
        QMessageBox.information(self.iface.mainWindow(), "Succès", "Configuration du proxy enregistrée.")

    def reset_settings(self):
        """Réinitialise les paramètres sauvegardés dans QSettings (proxy et chemins des couches)."""
        # Réinitialiser la configuration du proxy
        settings_proxy = QSettings("MesElusPlugin", "Proxy")
        settings_proxy.remove("use_proxy")
        settings_proxy.remove("proxy_url")

        # Réinitialiser les chemins des couches géométriques
        settings_geom = QSettings("MesElusPlugin", "Fonds")
        layer_types = ["communes", "cantons", "departements", "regions", "epci", "circonscriptions"]
        for layer_type in layer_types:
            settings_geom.remove(f"{layer_type}_path")
            settings_geom.remove(f"{layer_type}_field")

        # Afficher un message de confirmation
        QMessageBox.information(
            self.iface.mainWindow(),
            "Réinitialisation terminée",
            "Tous les paramètres (proxy et chemins des couches) ont été réinitialisés."
        )

        # Rafraîchir l'affichage
        self.load_proxy_config()
        self.geom_paths_tab.update_table()


    # ==================================================================
    # SÉLECTION DOSSIER DE TRAVAIL
    # ==================================================================
    def select_output_directory(self):
        dir_path = QFileDialog.getExistingDirectory(
            self.iface.mainWindow(),
            "Dossier de travail (toutes les données seront ici)",
            os.path.expanduser("~")
        )
        if dir_path:
            self.output_dir = dir_path
            self.lbl_dossier.setText(f"<b>Dossier de travail :</b> {dir_path}")
            self.iface.messageBar().pushMessage("Mes Élus", f"Dossier de travail sélectionné : {dir_path}", level=Qgis.Info)
     # Crée le sous-dossier "rne_data" s'il n'existe pas
        rne_data_dir = os.path.join(self.output_dir, "rne_data")
        os.makedirs(rne_data_dir, exist_ok=True)
    # ==================================================================
    # LANCEMENT DES FONCTIONS
    # ==================================================================
    def run_download(self):
        if not self.output_dir:
            warning(self.iface.mainWindow(), "Attention", "Sélectionnez d'abord un dossier de travail.")
            return

        # Récupérer la configuration du proxy
        settings = QSettings("MesElusPlugin", "Proxy")
        proxy_url = settings.value("proxy_url", "") if settings.value("use_proxy", False, type=bool) else None

        rne_data_dir = os.path.join(self.output_dir, "rne_data")
        filtered_data_dir = os.path.join(rne_data_dir, "filtered")
        territory_type, selected_code = select_perimeter_dialog(self.iface.mainWindow())

        if territory_type:
            territory_name = DEPARTEMENTS.get(selected_code) if territory_type == "Département" else REGIONS.get(selected_code)
            territory_info = {
                "territory_type": territory_type,
                "selected_code": selected_code,
                "territory_name": territory_name,
                "year": pd.Timestamp.now().year
            }
            with open(os.path.join(self.output_dir, "selected_territory.json"), "w") as f:
                json.dump(territory_info, f)

            download_and_filter(rne_data_dir, filtered_data_dir, territory_type, selected_code, self.iface.mainWindow())


    def load_output_dir(self):
        """Charge le chemin du dossier de travail depuis QSettings."""
        settings = QSettings("MesElusPlugin", "Settings")
        dir_path = settings.value("output_dir", None)
        if dir_path and os.path.exists(dir_path):
            self.output_dir = dir_path
            if self.lbl_dossier:
                self.lbl_dossier.setText(f"<b>Dossier de travail :</b> {dir_path}")

    
    def run_processing(self):
        if not self.output_dir:
            warning(self.iface.mainWindow(), "Attention", "Sélectionnez d'abord un dossier de travail.")
            return
        filtered_data_dir = os.path.join(self.output_dir, "rne_data", "filtered")
        process_geo(filtered_data_dir, self.iface.mainWindow())
        
    def update_layer_list(self):
        """Met à jour la liste des couches disponibles dans QGIS, en filtrant celles créées par le plugin."""
        try:
            print("Mise à jour de la liste des couches...")
            self.layer_list_widget.clear()

            # Récupère toutes les couches du projet QGIS
            layers = QgsProject.instance().mapLayers().values()
            print(f"Nombre de couches trouvées : {len(layers)}")

            if not layers:
                print("Aucune couche trouvée !")
                self.iface.messageBar().pushMessage(
                    "Info",
                    "Aucune couche n'est chargée dans QGIS. Veuillez en ajouter avant d'exporter.",
                    level=Qgis.Info
                )
                return

            # Filtre les couches créées par le plugin (ex: "Maires", "Députés", etc.)
            plugin_layers = [
                "Maires", "Conseillers municipaux", "Conseillers communautaires",
                "Conseillers départementaux", "Présidents des conseils départementaux",
                "Députés", "Sénateurs", "Conseillers régionaux", "Président du Conseil régional",
                "Président EPCI"
            ]

            # Ajoute chaque couche filtrée à la liste
            for layer in layers:
                if layer.name() in plugin_layers:
                    print(f"Ajout de : {layer.name()}")
                    item = QListWidgetItem(layer.name())
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(Qt.Unchecked)
                    self.layer_list_widget.addItem(item)

        except Exception as e:
            print(f"Erreur dans update_layer_list : {e}")
            self.iface.messageBar().pushMessage(
                "Erreur",
                f"Erreur lors de la mise à jour de la liste des couches : {e}",
                level=Qgis.Critical
            )


    def select_output_directory(self):
        dir_path = QFileDialog.getExistingDirectory(
            self.iface.mainWindow(),
            "Dossier de travail (toutes les données seront ici)",
            os.path.expanduser("~")
        )
        if dir_path:
            self.output_dir = dir_path
            if self.lbl_dossier:  # <-- Vérifie que self.lbl_dossier existe
                self.lbl_dossier.setText(f"<b>Dossier de travail :</b> {dir_path}")
            
            # Enregistrer le chemin dans QSettings
            settings = QSettings("MesElusPlugin", "Settings")
            settings.setValue("output_dir", dir_path)
            
            self.iface.messageBar().pushMessage("Mes Élus", f"Dossier de travail sélectionné : {dir_path}", level=Qgis.Info)
            # Crée le sous-dossier "rne_data" s'il n'existe pas
            rne_data_dir = os.path.join(self.output_dir, "rne_data")
            os.makedirs(rne_data_dir, exist_ok=True)
            self.iface.messageBar().pushMessage("Succès", f"Dossier de destination sélectionné : {dir_path}", level=Qgis.Info)
             
    
    def run_export(self):
        """Lance l'export des couches sélectionnées dans un GeoPackage."""
        # Récupère les couches cochées
        selected_layers = []
        for i in range(self.layer_list_widget.count()):
            item = self.layer_list_widget.item(i)
            if item.checkState() == Qt.Checked:
                selected_layers.append(item.text())

        # Vérifie qu'un dossier de destination a été sélectionné
        if not hasattr(self, 'output_dir') or not self.output_dir:
            self.iface.messageBar().pushMessage("Erreur", "Veuillez sélectionner un dossier de destination.", level=Qgis.Critical)
            return

        # Vérifie qu'au moins une couche est sélectionnée
        if not selected_layers:
            self.iface.messageBar().pushMessage("Erreur", "Veuillez sélectionner au moins une couche.", level=Qgis.Critical)
            return

        # Appelle le module export.py
        from .lib.export import export_layers
        export_layers(selected_layers, self.output_dir, self.iface)
