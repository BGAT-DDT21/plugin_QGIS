# X.FAYOUX 2025
# -*- coding: utf-8 -*-
# __init__.py du plugin
def classFactory(iface):
    from .main_plugin import MesElusPlugin
    return MesElusPlugin(iface)

