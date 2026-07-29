import os
import json
from PySide6.QtCore import QObject, Signal

DEFAULT_THEME = {
    "name": "Padrão (Dark)",
    "background": "#1e1e1e", "foreground": "#d4d4d4",
    "sidebar_bg": "#252526", "selection": "#094771",
    "border_color": "#3c3c3c", "accent": "#007acc"
}

EXAMPLE_LIGHT_THEME = {
    "name": "Claro (Exemplo)",
    "background": "#ffffff", "foreground": "#333333",
    "sidebar_bg": "#f3f3f3", "selection": "#cce8ff",
    "border_color": "#e5e5e5", "accent": "#0078d4"
}


class ThemeManager(QObject):
    """Gerencia o carregamento e aplicação de temas via JSON."""

    theme_changed = Signal()

    def __init__(self, root_dir):
        super().__init__()
        self.root_dir = root_dir
        self.themes_dir = os.path.join(root_dir, "themes")
        self.themes = {}
        self.default_theme = DEFAULT_THEME.copy()
        self.current_theme = self.default_theme.copy()

        if not os.path.exists(self.themes_dir):
            os.makedirs(self.themes_dir)
            self._save_example_theme()

        self.load_themes()

    def _save_example_theme(self):
        try:
            path = os.path.join(self.themes_dir, "light_theme.json")
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(EXAMPLE_LIGHT_THEME, f, indent=4)
        except OSError as e:
            print(f"Erro ao criar tema de exemplo: {e}")

    def load_themes(self):
        """Carrega todos os JSONs da pasta themes."""
        self.themes = {"Padrão": self.default_theme}
        if not os.path.exists(self.themes_dir):
            return

        for filename in os.listdir(self.themes_dir):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(self.themes_dir, filename)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    theme_data = json.load(f)
                name = theme_data.get("name", filename)
                self.themes[name] = theme_data
            except (OSError, json.JSONDecodeError) as e:
                print(f"Erro ao carregar tema {filename}: {e}")

    def set_theme(self, theme_name):
        if theme_name in self.themes:
            self.current_theme = self.themes[theme_name]
            self.theme_changed.emit()