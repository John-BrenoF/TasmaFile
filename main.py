import sys
import os
import json
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal

# Adiciona o diretório 'src' ao path para permitir importações relativas a ele.
# Isso torna o script executável a partir do diretório raiz do projeto.
project_root = os.path.abspath(os.path.dirname(__file__))
src_path = os.path.join(project_root, 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from ui.tf_window import TasmaFileWindow
from core.theme_manager import ThemeManager

# --- Mock Objects for Dependencies ---
# Estas classes simulam o comportamento de módulos externos necessários 
# para a inicialização da TasmaFileWindow, já que seus códigos-fonte 
# não foram fornecidos.

class SessionManager:
    """Gerencia o estado da sessão, como abas abertas e histórico."""
    def __init__(self):
        # Cria um diretório temporário para arquivos de sessão
        self.session_dir = os.path.join(project_root, "tmp_session")
        os.makedirs(self.session_dir, exist_ok=True)
        self.session_file = os.path.join(self.session_dir, "session.json")

    def load_session(self):
        """Carrega os dados da sessão a partir de um arquivo JSON."""
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, 'r') as f:
                    return json.load(f)
            except: pass # Em caso de erro, retorna o padrão
        return {"recent_projects": [os.path.expanduser("~")], "open_tabs": []}

    def save_session(self, data):
        """Salva os dados da sessão em um arquivo JSON."""
        try:
            with open(self.session_file, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Erro ao salvar sessão: {e}")

class ConfigManager(QObject):
    """Gerenciador de configurações persistente."""
    config_changed = Signal(str, object)

    def __init__(self, root_dir):
        super().__init__()
        self.config_path = os.path.join(root_dir, "config.json")
        self.config = {}
        self.load()

    def load(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    self.config = json.load(f)
            except: self.config = {}
    
    def save(self):
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
        except: pass

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save()
        self.config_changed.emit(key, value)

def main():
    """Função principal para executar a aplicação TasmaFile."""
    app = QApplication(sys.argv)
    config_manager = ConfigManager(project_root)

    # Aplica o tamanho da fonte global antes de criar a janela
    font_size = config_manager.get("font_size", -1)
    if font_size > 0:
        font = app.font()
        font.setPointSize(font_size)
        app.setFont(font)

    window = TasmaFileWindow(config_manager=config_manager, session_manager=SessionManager(), root_dir=project_root, theme_manager=ThemeManager(project_root))
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()