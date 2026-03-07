from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QPushButton, QFrame, QLabel, QStyle, QSplitter, QStackedWidget, QApplication, QTabWidget, QToolButton, QMenu
from PySide6.QtCore import Qt, QEvent
from core.data_provider import TasmaDataProvider
from tf_sidebar import TasmaSidebar
from ui.tf_file_view import TasmaFileView
from ui.tf_preview_panel import PreviewPanel
from ui.tf_settings import TasmaSettings
import os, platform, subprocess

class TasmaFileWindow(QDialog):
    """Janela Principal do Gerenciador de Arquivos TasmaFile."""
    
    def __init__(self, config_manager, session_manager, root_dir, theme_manager, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.theme_manager = theme_manager
        self.session_manager = session_manager
        self.config_manager.config_changed.connect(self._on_main_config_changed)
        self.theme_manager.theme_changed.connect(self._apply_theme) # Conecta sinal de mudança
        self.setWindowTitle("TasmaFile - Gerenciador de Arquivos")
        self.resize(1000, 700)
        self.selected_path = None
        
        # Lógica
        self.provider = TasmaDataProvider(session_manager, root_dir)
        
        # Layout Principal
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Sidebar
        self.sidebar = TasmaSidebar(self.provider)
        self.sidebar.category_selected.connect(self._on_category_selected)
        
        # Conteúdo (File View + Botões de Ação)
        content_widget = QFrame()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # --- Abas para Navegação ---
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        # Menu de contexto para abas
        self.tabs.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabs.tabBar().customContextMenuRequested.connect(self.show_tab_context_menu)

        # Botão de Nova Aba
        new_tab_btn = QToolButton()
        new_tab_btn.setText("+")
        new_tab_btn.setCursor(Qt.PointingHandCursor)
        new_tab_btn.clicked.connect(lambda: self.add_new_tab())
        self.tabs.setCornerWidget(new_tab_btn, Qt.TopLeftCorner)

        # Stack para alternar entre Arquivos e Configurações
        self.stack = QStackedWidget()
        self.settings_view = TasmaSettings(self.theme_manager, self.config_manager)
        
        self.stack.addWidget(self.tabs)           # Index 0
        self.stack.addWidget(self.settings_view)  # Index 1
        
        # Botões Inferiores
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(10, 10, 10, 10)
        
        self.lbl_status = QLabel("Pronto")
        self.lbl_status.setStyleSheet("color: #808080; font-size: 11px; padding-left: 5px;")
        
        btn_layout.addWidget(self.lbl_status)
        btn_layout.addStretch()
        
        content_layout.addWidget(self.stack)
        content_layout.addLayout(btn_layout)
        
        # Preview Panel
        self.preview_panel = PreviewPanel(self.theme_manager.current_theme)
        
        # Splitter para File View e Preview
        view_splitter = QSplitter(Qt.Horizontal)
        view_splitter.addWidget(content_widget)
        view_splitter.addWidget(self.preview_panel)
        view_splitter.setStretchFactor(0, 2) # File view é maior
        view_splitter.setStretchFactor(1, 1) # Preview é menor
        
        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(view_splitter)
        
        # Aplica o tema
        self._apply_theme()
        
        # Conecta e carrega favoritos
        self.provider.favorites_changed.connect(self._refresh_favorites)
        self._refresh_favorites()
        self.load_session_tabs()

    def _apply_theme(self):
        theme = self.theme_manager.current_theme
        bg = theme.get("background", "#1e1e1e")
        fg = theme.get("foreground", "#cccccc")
        accent = theme.get("accent", "#007acc")
        border = theme.get("border_color", "#3c3c3c")
        
        scrollbar_style = f"""
            QScrollBar:vertical {{
                border: none; background: {bg}; width: 10px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {border}; min-height: 20px; border-radius: 5px;
            }}
            QScrollBar:horizontal {{
                border: none; background: {bg}; height: 10px; margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background: {border}; min-width: 20px; border-radius: 5px;
            }}
        """
        
        tab_style = f"""
            QTabWidget::pane {{
                border: none;
            }}
            QTabBar::tab {{
                background: {bg};
                color: {fg};
                border: 1px solid {bg};
                border-bottom-color: {border};
                padding: 8px 12px;
                min-width: 100px;
            }}
            QTabBar::tab:selected {{
                background: {bg};
                border: 1px solid {border};
                border-bottom-color: {bg};
                color: {accent};
            }}
            QTabBar::tab:hover {{
                background: {border};
            }}
            QTabWidget::corner-widget {{
                border: none;
            }}
        """
        
        splitter_style = f"""
            QSplitter::handle:horizontal {{
                background: {border};
                width: 1px;
            }}
            QSplitter::handle:hover {{
                background: {accent};
            }}
        """
        
        self.setStyleSheet(f"QDialog {{ background-color: {bg}; color: {fg}; }}" + scrollbar_style + splitter_style)
        self.tabs.setStyleSheet(tab_style)

        self.sidebar.apply_theme(theme)
        self.preview_panel.apply_theme(theme)
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if hasattr(widget, 'apply_theme'):
                widget.apply_theme(theme)
        
        # Aplica estilo na Settings View (básico)
        self.settings_view.setStyleSheet(f"background-color: {bg}; color: {fg};")

    def _refresh_favorites(self):
        favs = self.provider.get_custom_categories()
        for i in range(self.tabs.count()):
            view = self.tabs.widget(i)
            if isinstance(view, TasmaFileView):
                view.update_favorites(favs)
        self.sidebar._populate()

    def current_file_view(self):
        """Retorna a instância de TasmaFileView da aba atual."""
        return self.tabs.currentWidget()

    def add_new_tab(self, state=None):
        """Cria e adiciona uma nova aba de navegação."""
        view = TasmaFileView(self.config_manager, self.provider)
        view.path_confirmed.connect(self._on_path_confirmed)
        view.path_selected.connect(self._on_path_selected)
        view.status_updated.connect(self._update_status)
        view.selection_changed.connect(self._update_status_selection)
        view.path_changed.connect(lambda text, v=view: self.update_tab_title(v, text))
        
        view.apply_theme(self.theme_manager.current_theme)
        view.update_favorites(self.provider.get_custom_categories())

        path_to_load = None
        if state:
            view.set_navigation_state(state)
            path_to_load = state.get('current_path')
        else:
            startup_mode = self.config_manager.get("startup_mode", "recent")
            path_to_load = self.provider.get_home_dir()
            if startup_mode == "custom":
                custom = self.config_manager.get("startup_path", "")
                if custom and os.path.exists(custom): path_to_load = custom
            elif startup_mode == "recent":
                recents = self.provider.get_recent_projects()
                if recents: path_to_load = recents[0]
        
        view.set_path(path_to_load)

        tab_name = os.path.basename(path_to_load) if path_to_load and os.path.basename(path_to_load) else "Início"
        index = self.tabs.addTab(view, tab_name)
        self.tabs.setCurrentIndex(index)
        return view

    def close_tab(self, index):
        """Fecha uma aba. Se for a última, fecha a janela."""
        if self.tabs.count() > 1:
            self.tabs.removeTab(index)
        else:
            self.close()

    def show_tab_context_menu(self, pos):
        index = self.tabs.tabBar().tabAt(pos)
        if index < 0: return

        menu = QMenu(self)
        theme = self.theme_manager.current_theme
        menu.setStyleSheet(f"QMenu {{ background-color: {theme.get('sidebar_bg')}; color: {theme.get('foreground')}; }} QMenu::item:selected {{ background-color: {theme.get('accent')}; }}")

        dup_action = menu.addAction("Duplicar Aba")
        dup_action.triggered.connect(lambda: self.duplicate_tab(index))
        menu.addSeparator()
        close_others_action = menu.addAction("Fechar Outras Abas")
        close_others_action.triggered.connect(lambda: self.close_other_tabs(index))
        close_right_action = menu.addAction("Fechar Abas à Direita")
        close_right_action.triggered.connect(lambda: self.close_tabs_to_right(index))

        menu.exec(self.tabs.tabBar().mapToGlobal(pos))

    def duplicate_tab(self, index):
        view = self.tabs.widget(index)
        if isinstance(view, TasmaFileView):
            state = view.get_navigation_state()
            self.add_new_tab(state)

    def close_other_tabs(self, index_to_keep):
        for i in range(self.tabs.count() - 1, -1, -1):
            if i != index_to_keep:
                self.tabs.removeTab(i)

    def close_tabs_to_right(self, index):
        for i in range(self.tabs.count() - 1, index, -1):
            self.tabs.removeTab(i)


    def update_tab_title(self, view, text):
        """Atualiza o título da aba com o nome da pasta atual."""
        index = self.tabs.indexOf(view)
        if index != -1:
            name = os.path.basename(text) or "/"
            self.tabs.setTabText(index, name)

    def load_session_tabs(self):
        """Carrega as abas da sessão anterior."""
        session_data = self.session_manager.load_session()
        tabs_state = session_data.get("open_tabs", [])
        
        if tabs_state:
            for state in tabs_state:
                self.add_new_tab(state)
        else:
            self.add_new_tab() # Adiciona uma aba padrão se não houver sessão

    def save_session_tabs(self):
        """Salva o estado de todas as abas abertas."""
        tabs_state = []
        for i in range(self.tabs.count()):
            view = self.tabs.widget(i)
            if isinstance(view, TasmaFileView):
                tabs_state.append(view.get_navigation_state())
        
        session_data = self.session_manager.load_session()
        session_data["open_tabs"] = tabs_state
        self.session_manager.save_session(session_data)

    def _on_category_selected(self, type_id, data):
        if type_id.startswith("config_"):
            self.stack.setCurrentWidget(self.settings_view)
        else:
            self.stack.setCurrentWidget(self.tabs)
            view = self.current_file_view() or self.add_new_tab()
            view.set_path(data)

    def _on_path_selected(self, path):
        self.selected_path = path
        self.preview_panel.show_preview(path)

    def _on_path_confirmed(self, path):
        """Ação de duplo-clique em um arquivo. Abre com o app padrão do sistema."""
        if path and os.path.exists(path) and os.path.isfile(path):
            system = platform.system()
            try:
                if system == "Windows":
                    os.startfile(path)
                elif system == "Darwin": # macOS
                    subprocess.call(['open', path])
                else: # Linux and other Unix-like
                    subprocess.call(['xdg-open', path])
            except Exception as e:
                self.status_updated.emit(f"Erro ao abrir arquivo: {e}")
        # Não fechar a aplicação. A lógica anterior com self.accept() foi removida.

    def _update_status(self, msg):
        self.lbl_status.setText(msg)

    def _update_status_selection(self, count, total_size):
        if count == 0:
            view = self.current_file_view()
            if view:
                view._on_directory_loaded(view.model.rootPath())
            return
        
        self.lbl_status.setText(f"{count} {'item' if count == 1 else 'itens'} selecionados ({total_size})")

    def _on_main_config_changed(self, key, value):
        """Aplica mudanças de configuração globais."""
        if key == "font_size":
            font = QApplication.font()
            font.setPointSize(value)
            QApplication.setFont(font)

    def _on_tab_changed(self, index):
        """Chamado quando o usuário troca de aba."""
        view = self.current_file_view()
        if not view: return
        self.preview_panel.show_preview(None) # Limpa o painel de pré-visualização

    def closeEvent(self, event):
        """Salva a sessão antes de fechar."""
        self.save_session_tabs()
        super().closeEvent(event)