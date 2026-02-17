# -*- coding: utf-8 -*-
# lib/export.py
# Créé le 17/12/2025, modifié pour débogage
import os
from qgis.core import QgsProject, QgsVectorFileWriter, QgsMapLayerStyle, Qgis
from qgis.PyQt.QtXml import QDomDocument
from qgis.core import QgsReadWriteContext,QgsVectorLayer

def export_layers(layer_names, output_dir, iface):
    """
    Exporte les couches sélectionnées dans le format spécifié.
    :param layer_names: Liste des noms des couches à exporter.
    :param output_dir: Dossier de destination.
    :param iface: Interface QGIS pour afficher les messages.
    """
    # Récupère les couches du projet QGIS
    layers = QgsProject.instance().mapLayers().values()
    layers_dict = {layer.name(): layer for layer in layers}
    
    # Débogage : Affiche toutes les couches détectées pour vérifier
    all_layer_names = list(layers_dict.keys())
    iface.messageBar().pushMessage(
        "Débogage",
        f"Couches disponibles dans le projet : {', '.join(all_layer_names)}",
        level=Qgis.Info,
        duration=10  # Affiche plus longtemps
    )
    
    # Vérifie que les couches sélectionnées existent
    missing_layers = [name for name in layer_names if name not in layers_dict]
    if missing_layers:
        iface.messageBar().pushMessage(
            "Erreur",
            f"Les couches suivantes sont introuvables : {', '.join(missing_layers)}. Vérifiez le chargement.",
            level=Qgis.Critical
        )
        return
    
    # Chemin du GeoPackage de sortie
    output_gpkg = os.path.join(output_dir, "Mes_élus.gpkg")
    
    # Supprime le fichier GeoPackage s'il existe déjà
    if os.path.exists(output_gpkg):
        try:
            os.remove(output_gpkg)
            iface.messageBar().pushMessage(
                "Info",
                f"L'ancien fichier GeoPackage a été supprimé : {output_gpkg}",
                level=Qgis.Info
            )
        except Exception as e:
            iface.messageBar().pushMessage(
                "Erreur",
                f"Impossible de supprimer l'ancien fichier GeoPackage : {str(e)}",
                level=Qgis.Critical
            )
            return
    
    # Options d'export pour GeoPackage
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.fileEncoding = "UTF-8"  # Changé en UTF-8 pour mieux gérer accents/unicode
    options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile  # Pour la première couche
    
    # Contexte de transformation
    transform_context = QgsProject.instance().transformContext()
    
    # Exporte chaque couche dans le GeoPackage
    try:
        for i, name in enumerate(layer_names):
            layer = layers_dict[name]
            layer_output_name = name  # Nom original complet avec espaces et accents
            # layer_output_name = f"layer_{i}_{name.replace(' ', '_').replace('é', 'e').replace('è', 'e')}"  # Nettoie pour éviter problèmes unicode
            layer_options = QgsVectorFileWriter.SaveVectorOptions(options)  # copie des options de base
            layer_options.layerName = layer_output_name
            layer_options.driverName = "GPKG"
            layer_options.fileEncoding = "UTF-8"
            if i == 0:
                layer_options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile   # crée/écrase le GPKG entier
            else:
                layer_options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer  # ajoute une nouvelle couche dans le GPKG existant
            
            # Sauvegarde le style QML
            style_manager = layer.styleManager()
            current_style = style_manager.currentStyle()
            qml_style = QgsMapLayerStyle()
            qml_style.readFromLayer(layer)
            layer_options.includeStyle = True  # Inclut le style directement
            
            error = QgsVectorFileWriter.writeAsVectorFormatV3(
                layer,
                output_gpkg,
                transform_context,
                layer_options
            )
            if error[0] == QgsVectorFileWriter.NoError:
                # Sauvegarde du style comme défaut dans le GeoPackage
                from qgis.PyQt.QtXml import QDomDocument

                doc = QDomDocument()
                
                # Exporte le style de la couche source (sans contexte)
                layer.exportNamedStyle(doc)

                # Recharge la couche écrite dans le GPKG
                gpkg_layer_uri = f"{output_gpkg}|layername={layer_output_name}"
                gpkg_layer = QgsVectorLayer(gpkg_layer_uri, name, "ogr")

                if gpkg_layer.isValid():
                    # Importe le style (uniquement le doc)
                    gpkg_layer.importNamedStyle(doc)

                    # Enregistre comme style par défaut (clé pour l'application automatique)
                    gpkg_layer.saveStyleToDatabase(
                        name=name,               # Nom du style (identique au nom de couche)
                        description="",
                        useAsDefault=True,
                        uiFileContent=""
                    )
                    iface.messageBar().pushMessage("Succès", f"Style embarqué comme défaut pour {name}", level=Qgis.Success)
                else:
                    iface.messageBar().pushMessage("Avertissement", f"Impossible de recharger {name} pour sauver le style", level=Qgis.Warning)
                    
    except Exception as e:
        iface.messageBar().pushMessage("Erreur", f"Erreur inattendue lors de l'export : {str(e)}", level=Qgis.Critical)