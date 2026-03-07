from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QComboBox, QGroupBox, QFormLayout, QCheckBox, QSpinBox, QApplication, QLineEdit, QPushButton, QFileDialog, QHBoxLayout
from PySide6.QtCore import Qt, Slot

class TasmaSettings(QWidget):
    """Tela de configurações do aplicativo."""
    
    def __init__(self, theme_manager, config_manager, parent=None):
        super().__init__(parent)
        self.theme_manager = theme_manager
        self.config_manager = config_manager
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setAlignment(Qt.AlignTop)
        
        title = QLabel("Configurações")
        title.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title)
        
        # Grupo de Inicialização
        group_startup = QGroupBox("Inicialização")
        startup_layout = QFormLayout(group_startup)
        
        self.combo_startup = QComboBox()
        self.combo_startup.addItems(["Projetos Recentes", "Pasta de Usuário", "Personalizada"])
        
        startup_mode = self.config_manager.get("startup_mode", "recent")
        mode_map = {"recent": 0, "home": 1, "custom": 2}
        self.combo_startup.setCurrentIndex(mode_map.get(startup_mode, 0))
        self.combo_startup.currentIndexChanged.connect(self._on_startup_mode_changed)
        
        startup_layout.addRow("Abrir em:", self.combo_startup)
        
        self.custom_path_widget = QWidget()
        cp_layout = QHBoxLayout(self.custom_path_widget)
        cp_layout.setContentsMargins(0,0,0,0)
        
        self.line_startup_path = QLineEdit()
        self.line_startup_path.setText(self.config_manager.get("startup_path", ""))
        self.line_startup_path.textChanged.connect(lambda t: self.config_manager.set("startup_path", t))
        
        self.btn_browse_startup = QPushButton("...")
        self.btn_browse_startup.clicked.connect(self._browse_startup_path)
        
        cp_layout.addWidget(self.line_startup_path)
        cp_layout.addWidget(self.btn_browse_startup)
        
        startup_layout.addRow("Caminho:", self.custom_path_widget)
        self._update_custom_path_visibility()
        
        layout.addWidget(group_startup)

        # Grupo de Comportamento
        group_behavior = QGroupBox("Comportamento")
        behavior_layout = QFormLayout(group_behavior)

        self.check_hidden = QCheckBox("Mostrar arquivos ocultos")
        self.check_hidden.setChecked(self.config_manager.get("show_hidden", False))
        self.check_hidden.toggled.connect(lambda v: self.config_manager.set("show_hidden", v))
        behavior_layout.addRow(self.check_hidden)

        self.combo_view_mode = QComboBox()
        self.combo_view_mode.addItems(["Grade (Ícones)", "Lista (Detalhes)"])
        current_mode = self.config_manager.get("view_mode", "icon")
        self.combo_view_mode.setCurrentIndex(0 if current_mode == "icon" else 1)
        self.combo_view_mode.currentIndexChanged.connect(lambda i: self.config_manager.set("view_mode", "icon" if i == 0 else "list"))
        behavior_layout.addRow("Visualização Padrão:", self.combo_view_mode)

        layout.addWidget(group_behavior)

        # Grupo de Terminal
        group_terminal = QGroupBox("Terminal")
        terminal_layout = QFormLayout(group_terminal)
        self.line_terminal_cmd = QLineEdit()
        self.line_terminal_cmd.setText(self.config_manager.get("terminal_command", ""))
        self.line_terminal_cmd.setPlaceholderText("ex: konsole --workdir {path}")
        self.line_terminal_cmd.textChanged.connect(lambda t: self.config_manager.set("terminal_command", t))
        terminal_layout.addRow("Comando customizado:", self.line_terminal_cmd)
        cmd_info = QLabel("Use <code>{path}</code> como placeholder para o diretório atual.")
        cmd_info.setWordWrap(True)
        terminal_layout.addRow(cmd_info)
        layout.addWidget(group_terminal)

        # Grupo de Aparência
        group_appearance = QGroupBox("Aparência")
        form_layout = QFormLayout(group_appearance)
        
        self.combo_themes = QComboBox()
        self._populate_themes()
        self.combo_themes.currentTextChanged.connect(self._on_theme_changed)
        
        form_layout.addRow("Tema:", self.combo_themes)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(8, 24)
        self.font_size_spin.setSuffix(" pt")
        default_font_size = self.config_manager.get("font_size", QApplication.font().pointSize())
        if default_font_size <= 0: default_font_size = 10 # Fallback
        self.font_size_spin.setValue(default_font_size)
        self.font_size_spin.valueChanged.connect(self.on_font_size_changed)
        form_layout.addRow("Tamanho da Fonte:", self.font_size_spin)

        layout.addWidget(group_appearance)
        
    def _populate_themes(self):
        self.combo_themes.blockSignals(True)
        self.combo_themes.clear()
        themes = list(self.theme_manager.themes.keys())
        self.combo_themes.addItems(themes)
        
        # Tenta selecionar o tema atual (pelo nome, se possível)
        current_name = self.theme_manager.current_theme.get("name", "Padrão")
        # Busca aproximada ou exata
        index = self.combo_themes.findText(current_name, Qt.MatchContains)
        if index >= 0:
            self.combo_themes.setCurrentIndex(index)
            
        self.combo_themes.blockSignals(False)

    def _on_theme_changed(self, text):
        self.theme_manager.set_theme(text)

    @Slot(int)
    def on_font_size_changed(self, value):
        self.config_manager.set("font_size", value)

    def _on_startup_mode_changed(self, index):
        modes = {0: "recent", 1: "home", 2: "custom"}
        self.config_manager.set("startup_mode", modes.get(index, "recent"))
        self._update_custom_path_visibility()

    def _update_custom_path_visibility(self):
        is_custom = self.combo_startup.currentIndex() == 2
        self.custom_path_widget.setVisible(is_custom)
        label = self.custom_path_widget.parentWidget().layout().labelForField(self.custom_path_widget)
        if label: label.setVisible(is_custom)

    def _browse_startup_path(self):
        path = QFileDialog.getExistingDirectory(self, "Selecionar Pasta Inicial")
        if path:
            self.line_startup_path.setText(path)