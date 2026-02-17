# mes_elus/lib/utils.py

from qgis.PyQt.QtWidgets import QMessageBox

def info(parent, titre, message):
    """Affiche une petite fenêtre "information" """
    QMessageBox.information(parent, titre, message)

def warning(parent, titre, message):
    """Affiche une petite fenêtre "attention" """
    QMessageBox.warning(parent, titre, message)

def erreur(parent, titre, message):
    """Affiche une petite fenêtre "erreur" """
    QMessageBox.critical(parent, titre, message)