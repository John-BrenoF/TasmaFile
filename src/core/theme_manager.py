import os
import json
from PySide6.QtCore import QObject, Signal

class ThemeManager(QObject):
    """Gerencia o carregamento e aplicação de temas via JSON."""
    
    theme_changed = Signal()

    def __init__(self, root_dir):
        super().__init__()
        self.root_dir = root_dir
        self.themes_dir = os.path.join(root_dir, "themes")
        self.themes = {}
        
        # Tema padrão (Dark)
        self.default_theme = {
            "name": "Padrão (Dark)",
            "background": "#1e1e1e", "foreground": "#d4d4d4",
            "sidebar_bg": "#252526", "selection": "#094771",
            "border_color": "#3c3c3c", "accent": "#007acc"
        }
        
        self.current_theme = self.default_theme.copy()
        
        # Garante que a pasta de temas existe
        if not os.path.exists(self.themes_dir):
            os.makedirs(self.themes_dir)
            # Cria um tema de exemplo
            self._save_example_theme()

        self.load_themes()

    def _save_example_theme(self):
        light_theme = {
            "name": "Claro (Exemplo)",
            "background": "#ffffff", "foreground": "#333333",
            "sidebar_bg": "#f3f3f3", "selection": "#cce8ff",
            "border_color": "#e5e5e5", "accent": "#0078d4"
        }
        try:
            with open(os.path.join(self.themes_dir, "light_theme.json"), 'w') as f:
                json.dump(light_theme, f, indent=4)
        except: pass

    def load_themes(self):
        """Carrega todos os JSONs da pasta themes."""
        self.themes = {"Padrão": self.default_theme}
        if os.path.exists(self.themes_dir):
            for filename in os.listdir(self.themes_dir):
                if filename.endswith(".json"):
                    try:
                        with open(os.path.join(self.themes_dir, filename), 'r') as f:
                            theme_data = json.load(f)
                            name = theme_data.get("name", filename)
                            self.themes[name] = theme_data
                    except Exception as e:
                        print(f"Erro ao carregar tema {filename}: {e}")

    def set_theme(self, theme_name):
        if theme_name in self.themes:
            self.current_theme = self.themes[theme_name]
            self.theme_changed.emit()