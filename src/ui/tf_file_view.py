from PySide6.QtWidgets import QWidget, QVBoxLayout, QListView, QFileSystemModel, QLineEdit, QAbstractItemView, QHBoxLayout, QPushButton, QStyle, QMenu, QInputDialog, QMessageBox, QToolTip, QScrollArea, QFrame, QSlider, QComboBox, QLabel, QApplication, QFileIconProvider
from PySide6.QtCore import Qt, Signal, QDir, QSize, QEvent, QThread
from PySide6.QtGui import QKeySequence, QCursor, QIcon
from datetime import datetime
import os, platform, subprocess
import shutil

class FolderStatsThread(QThread):
    """Thread para calcular tamanho de pasta sem travar a UI."""
    stats_ready = Signal(str, int, float) # path, count, size_gb

    def __init__(self, path):
        super().__init__()
        self.path = path
        self._is_running = True

    def run(self):
        total_size = 0
        file_count = 0
        try:
            for dirpath, _, filenames in os.walk(self.path):
                if not self._is_running: return
                file_count += len(filenames)
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    if not os.path.islink(fp):
                        total_size += os.path.getsize(fp)
        except:
            pass
        
        size_gb = total_size / (1024 * 1024 * 1024)
        self.stats_ready.emit(self.path, file_count, size_gb)

    def stop(self):
        self._is_running = False

class BreadcrumbBar(QWidget):
    """Barra de navegação com breadcrumbs clicáveis."""
    path_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)
        self.layout().setAlignment(Qt.AlignLeft)
        self.setStyleSheet("background: transparent;")

    def set_path(self, path):
        while self.layout().count():
            child = self.layout().takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        path = os.path.normpath(path)
        path_parts = []
        temp_path = path
        while True:
            head, tail = os.path.split(temp_path)
            if tail:
                path_parts.insert(0, (tail, temp_path))
            elif head:
                path_parts.insert(0, (head, head))
                break
            if head == temp_path: break # Root reached
            temp_path = head

        if not path_parts and path == os.path.sep:
            path_parts.append((os.path.sep, os.path.sep))

        for i, (part_name, part_path) in enumerate(path_parts):
            btn = QPushButton(part_name)
            btn.setFlat(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, p=part_path: self.path_clicked.emit(p))
            self.layout().addWidget(btn)
            if i < len(path_parts) - 1:
                self.layout().addWidget(QLabel(os.path.sep))

class TasmaFileView(QWidget):
    """Área principal de visualização de arquivos."""
    
    path_changed = Signal(str)   # Sinaliza que o caminho da view mudou
    path_selected = Signal(str)
    path_confirmed = Signal(str) # Double click ou Enter
    status_updated = Signal(str) # Envia texto para a barra de status
    selection_changed = Signal(int, str) # count, total_size_str

    def __init__(self, config_manager=None, provider=None, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.provider = provider
        self.theme = {}
        self._clipboard = None # (path, operation: 'copy' or 'cut')
        self._stats_thread = None
        self._history = []
        self._future = []
        self._is_navigating_history = False
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # --- Barra Superior ---
        # Design: uma única linha enxuta com os controles essenciais, e uma
        # segunda linha (filtro + zoom) que só aparece quando necessária,
        # reduzindo a poluição visual no estado padrão.
        BTN_SIZE = 28
        ICON_BTN_SIZE = QSize(BTN_SIZE, BTN_SIZE)

        top_bar_widget = QWidget()
        top_bar_layout = QVBoxLayout(top_bar_widget)
        top_bar_layout.setContentsMargins(10, 8, 10, 6)
        top_bar_layout.setSpacing(6)

        # Linha única: Navegação + Endereço + Ações
        nav_layout = QHBoxLayout()
        nav_layout.setSpacing(4)

        def _make_tool_button(icon, tooltip, checkable=False):
            btn = QPushButton()
            btn.setIcon(icon)
            btn.setFixedSize(BTN_SIZE, BTN_SIZE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tooltip)
            btn.setFlat(True)
            btn.setCheckable(checkable)
            return btn

        self.btn_back = _make_tool_button(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack), "Voltar")
        self.btn_back.clicked.connect(self.go_back)
        self.btn_back.setEnabled(False)

        self.btn_forward = _make_tool_button(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward), "Avançar")
        self.btn_forward.clicked.connect(self.go_forward)
        self.btn_forward.setEnabled(False)

        self.btn_up = _make_tool_button(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp), "Subir um nível")
        self.btn_up.clicked.connect(self._go_up)

        self.address_bar = BreadcrumbBar()
        self.address_bar.path_clicked.connect(self.set_path)

        self.btn_search = _make_tool_button(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView), "Filtrar arquivos", checkable=True)
        self.btn_search.toggled.connect(self._toggle_filter_row)

        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Nome", "Tamanho", "Data de Modificação"])
        self.sort_combo.setToolTip("Ordenar por")
        self.sort_combo.setFixedHeight(BTN_SIZE)
        self.sort_combo.setMaximumWidth(150)
        self.sort_combo.currentIndexChanged.connect(self._on_sort_changed)

        self.btn_sort_order = _make_tool_button(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown), "Ordem Ascendente/Descendente", checkable=True)
        self.btn_sort_order.clicked.connect(self._on_sort_changed)

        self.btn_toggle_view = _make_tool_button(QIcon(), "Alternar Visualização")
        self.btn_toggle_view.clicked.connect(self._toggle_view_mode)

        self.btn_refresh = _make_tool_button(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "Atualizar")
        self.btn_refresh.clicked.connect(self._refresh_view)

        self.btn_terminal = _make_tool_button(self.style().standardIcon(QStyle.StandardPixmap.SP_DriveDVDIcon), "Abrir no Terminal")
        self.btn_terminal.clicked.connect(self._open_in_terminal)

        nav_layout.addWidget(self.btn_back)
        nav_layout.addWidget(self.btn_forward)
        nav_layout.addWidget(self.btn_up)
        nav_layout.addSpacing(6)
        nav_layout.addWidget(self.address_bar, 1)
        nav_layout.addSpacing(6)
        nav_layout.addWidget(self.btn_search)
        nav_layout.addWidget(self.sort_combo)
        nav_layout.addWidget(self.btn_sort_order)
        nav_layout.addWidget(self.btn_toggle_view)
        nav_layout.addWidget(self.btn_refresh)
        nav_layout.addWidget(self.btn_terminal)
        top_bar_layout.addLayout(nav_layout)

        # Linha secundária (retrátil): Filtro de texto + Zoom
        self.filter_row_widget = QWidget()
        filter_row_layout = QHBoxLayout(self.filter_row_widget)
        filter_row_layout.setContentsMargins(0, 0, 0, 0)
        filter_row_layout.setSpacing(8)

        self.filter_bar = QLineEdit()
        self.filter_bar.setPlaceholderText("Filtrar por nome...")
        self.filter_bar.setClearButtonEnabled(True)
        self.filter_bar.setFixedHeight(BTN_SIZE)
        self.filter_bar.textChanged.connect(self._on_filter_changed)
        filter_row_layout.addWidget(self.filter_bar, 1)

        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(32, 128) # Tamanho do ícone
        self.zoom_slider.setValue(48)
        self.zoom_slider.setFixedWidth(120)
        self.zoom_slider.setToolTip("Tamanho dos ícones")
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        filter_row_layout.addWidget(self.zoom_slider)

        top_bar_layout.addWidget(self.filter_row_widget)
        self.filter_row_widget.hide() # Retrátil: só aparece ao clicar em Filtrar

        layout.addWidget(top_bar_widget)

        # --- Barra de Favoritos Rápidos ---
        self.favorites_container = QWidget()
        self.favorites_container.setFixedHeight(38)
        fav_layout_outer = QHBoxLayout(self.favorites_container)
        fav_layout_outer.setContentsMargins(10, 0, 10, 4)
        
        self.favorites_scroll = QScrollArea()
        self.favorites_scroll.setWidgetResizable(True)
        self.favorites_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.favorites_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.favorites_scroll.setStyleSheet("background: transparent; border: none;")
        self.favorites_scroll.setFixedHeight(34)
        
        self.favorites_content = QWidget()
        self.favorites_layout = QHBoxLayout(self.favorites_content)
        self.favorites_layout.setContentsMargins(0, 0, 0, 0)
        self.favorites_layout.setSpacing(6)
        self.favorites_layout.setAlignment(Qt.AlignLeft)
        
        self.favorites_scroll.setWidget(self.favorites_content)
        fav_layout_outer.addWidget(self.favorites_scroll)
        
        layout.addWidget(self.favorites_container)
        self.favorites_container.hide() # Oculta se não houver favoritos

        # Modelo de Arquivos
        self.model = QFileSystemModel()
        self.model.setIconProvider(QFileIconProvider())
        self.model.setFilter(QDir.AllEntries | QDir.NoDotAndDotDot)
        self.model.setRootPath(QDir.rootPath())
        self.model.setReadOnly(False) # Habilita operações de arquivo (Drag & Drop)
        self.model.directoryLoaded.connect(self._on_directory_loaded)
        
        # List View (Modo Ícones / Grid)
        self.list_view = QListView()
        self.list_view.setModel(self.model)
        self.list_view.setRootIndex(self.model.index(QDir.homePath()))
        
        # Context Menu
        self.list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self._show_context_menu)
        
        # Configuração de Drag & Drop
        self.list_view.setDragEnabled(True)
        self.list_view.setAcceptDrops(True)
        self.list_view.setDropIndicatorShown(True)
        self.list_view.setDragDropMode(QAbstractItemView.DragDrop)
        self.list_view.setDefaultDropAction(Qt.MoveAction)
        
        # Tooltips e Mouse Tracking
        self.list_view.setMouseTracking(True)
        self.list_view.entered.connect(self._on_item_entered)
        self.list_view.installEventFilter(self) # Para atalhos de teclado

        # Mensagem de Pasta Vazia
        self.empty_label = QLabel("Esta pasta está vazia.", self.list_view)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.hide()
        
        # Configurações iniciais
        if self.config_manager:
            self.config_manager.config_changed.connect(self._on_config_changed)
            self._apply_config()
        else:
            self._set_icon_mode()
        
        self.list_view.doubleClicked.connect(self._on_double_click)
        self.list_view.clicked.connect(self._on_click)
        self.list_view.selectionModel().selectionChanged.connect(self._on_selection_changed)
        
        layout.addWidget(self.list_view)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Centraliza a mensagem de pasta vazia
        self.empty_label.setGeometry(self.list_view.rect())

    def get_navigation_state(self):
        """Retorna o estado de navegação atual para persistência."""
        return {
            "current_path": self.model.rootPath(),
            "history": self._history,
            "future": self._future
        }

    def set_navigation_state(self, state):
        """Restaura o estado de navegação a partir de dados persistidos."""
        self._history = state.get("history", [])
        self._future = state.get("future", [])
        self._is_navigating_history = True
        self.set_path(state.get("current_path", QDir.homePath()))
        self._is_navigating_history = False

    def _apply_config(self):
        """Aplica configurações salvas."""
        # Arquivos Ocultos
        show_hidden = self.config_manager.get("show_hidden", False)
        filters = QDir.AllEntries | QDir.NoDotAndDotDot
        if show_hidden:
            filters |= QDir.Hidden
        self.model.setFilter(filters)

        # Modo de Visualização
        view_mode = self.config_manager.get("view_mode", "icon")
        if view_mode == "list":
            self._set_list_mode()
        else:
            self._set_icon_mode()

    def _on_config_changed(self, key, value):
        if key in ["show_hidden", "view_mode"]:
            self._apply_config()

    def _open_in_terminal(self):
        path = self.model.rootPath()
        system = platform.system()
        try:
            if system == "Windows":
                subprocess.Popen(['cmd.exe'], creationflags=subprocess.CREATE_NEW_CONSOLE, cwd=path)
            elif system == "Darwin":
                subprocess.call(['open', '-a', 'Terminal', path])
            else: # Linux
                try:
                    subprocess.Popen(['gnome-terminal', '--working-directory', path])
                except FileNotFoundError:
                    subprocess.Popen(['konsole', '--workdir', path])
        except Exception as e:
            QMessageBox.warning(self, "Terminal", f"Não foi possível abrir o terminal: {e}")

    def _set_icon_mode(self):
        """Configura visualização em grade (ícones grandes)."""
        self.list_view.setViewMode(QListView.IconMode)
        self.list_view.setResizeMode(QListView.Adjust)
        self.list_view.setGridSize(QSize(100, 100))
        self.list_view.setIconSize(QSize(48, 48))
        self.list_view.setUniformItemSizes(True)
        self.list_view.setWordWrap(True)
        self.list_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.zoom_slider.show()
        self.btn_toggle_view.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView))
        self.btn_toggle_view.setToolTip("Mudar para Lista")

    def _set_list_mode(self):
        """Configura visualização em lista (detalhes compactos)."""
        self.list_view.setViewMode(QListView.ListMode)
        self.list_view.setResizeMode(QListView.Adjust)
        self.list_view.setGridSize(QSize()) # Reseta grid
        self.list_view.setIconSize(QSize(16, 16))
        self.list_view.setUniformItemSizes(False)
        self.list_view.setWordWrap(False)
        self.zoom_slider.hide()
        self.btn_toggle_view.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView))
        self.btn_toggle_view.setToolTip("Mudar para Grade")

    def _toggle_view_mode(self):
        if self.list_view.viewMode() == QListView.IconMode:
            self._set_list_mode()
        else:
            self._set_icon_mode()

    def _toggle_filter_row(self, checked):
        """Mostra ou oculta a linha de filtro/zoom, mantendo a barra de ferramentas enxuta."""
        self.filter_row_widget.setVisible(checked)
        if checked:
            self.filter_bar.setFocus()
        else:
            self.filter_bar.clear()

    def go_back(self):
        if not self._history:
            return
        self._is_navigating_history = True
        current_path = self.model.rootPath()
        self._future.append(current_path)
        self.set_path(self._history.pop())
        self._is_navigating_history = False

    def go_forward(self):
        if not self._future:
            return
        self._is_navigating_history = True
        current_path = self.model.rootPath()
        self._history.append(current_path)
        self.set_path(self._future.pop())
        self._is_navigating_history = False

    def _go_up(self):
        current_path = self.model.rootPath()
        parent_path = os.path.dirname(current_path)
        if parent_path != current_path:
            self.set_path(parent_path)

    def _refresh_view(self):
        current_path = self.model.rootPath()
        self.model.setRootPath("") # Invalida o cache
        self.model.setRootPath(current_path) # Recarrega

    def _on_filter_changed(self, text):
        self.model.setNameFilters([f"*{text}*"] if text else [])

    def _on_sort_changed(self):
        # Colunas: 0=Nome, 1=Tamanho, 3=Data
        sort_map = { 0: 0, 1: 1, 2: 3 }
        column = sort_map.get(self.sort_combo.currentIndex(), 0)
        
        is_descending = self.btn_sort_order.isChecked()
        order = Qt.SortOrder.DescendingOrder if is_descending else Qt.SortOrder.AscendingOrder
        self.btn_sort_order.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp if is_descending else QStyle.StandardPixmap.SP_ArrowDown))
        
        self.model.sort(column, order)

    def _on_zoom_changed(self, value):
        if self.list_view.viewMode() == QListView.IconMode:
            self.list_view.setIconSize(QSize(value, value))
            self.list_view.setGridSize(QSize(value + 20, value + 40))

    def update_favorites(self, favorites):
        """Atualiza a barra de favoritos rápidos."""
        # Limpa itens existentes
        while self.favorites_layout.count():
            child = self.favorites_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        if not favorites:
            self.favorites_container.hide()
            return
            
        self.favorites_container.show()
        
        for name, path in favorites.items():
            btn = QPushButton(name)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(path)
            btn.clicked.connect(lambda checked=False, p=path: self.set_path(p))
            self.favorites_layout.addWidget(btn)
            
        if self.theme:
            self.apply_theme(self.theme)

    def apply_theme(self, theme):
        self.theme = theme
        bg = theme.get("background", "#1e1e1e")
        fg = theme.get("foreground", "#cccccc")
        input_bg = theme.get("sidebar_bg", "#3c3c3c")
        border = theme.get("border_color", "#454545")
        selection = theme.get("selection", "#094771")
        accent = theme.get("accent", "#007acc")

        self.address_bar.setStyleSheet(f"QPushButton {{ color: {fg}; font-weight: 500; border: none; background: transparent; padding: 4px 6px; }} QPushButton:hover {{ color: {accent}; }} QLabel {{ color: {border}; padding: 0 2px; }}")

        # Botões de ferramenta: totalmente flat, sem borda; hover mostra apenas um leve tom de fundo.
        tool_button_style = f"""
            QPushButton {{ background-color: transparent; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background-color: {input_bg}; }}
            QPushButton:disabled {{ background-color: transparent; }}
        """
        checkable_button_style = f"""
            QPushButton {{ background-color: transparent; border: none; border-radius: 6px; }}
            QPushButton:hover {{ background-color: {input_bg}; }}
            QPushButton:checked {{ background-color: {accent}; }}
            QPushButton:disabled {{ background-color: transparent; }}
        """
        self.filter_bar.setStyleSheet(f"""
            QLineEdit {{ background-color: {input_bg}; color: {fg}; padding: 6px 10px; border: none; border-radius: 6px; }}
            QLineEdit:focus {{ background-color: {input_bg}; }}
        """)

        self.btn_back.setStyleSheet(tool_button_style)
        self.btn_forward.setStyleSheet(tool_button_style)
        self.btn_up.setStyleSheet(tool_button_style)
        self.btn_refresh.setStyleSheet(tool_button_style)
        self.btn_toggle_view.setStyleSheet(tool_button_style)
        self.btn_sort_order.setStyleSheet(checkable_button_style)
        self.btn_terminal.setStyleSheet(tool_button_style)
        self.btn_search.setStyleSheet(checkable_button_style)

        self.sort_combo.setStyleSheet(f"""
            QComboBox {{ background-color: transparent; color: {fg}; border: none; padding: 4px 6px; border-radius: 6px; }}
            QComboBox:hover {{ background-color: {input_bg}; }}
            QComboBox::drop-down {{ border: none; width: 18px; }}
            QComboBox QAbstractItemView {{ background-color: {bg}; color: {fg}; selection-background-color: {accent}; border: 1px solid {border}; outline: none; }}
        """)
        self.zoom_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ background: {input_bg}; height: 4px; border-radius: 2px; }}
            QSlider::handle:horizontal {{ background: {accent}; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }}
        """)

        # Chips de favoritos: cápsula discreta, ganha cor apenas no hover.
        fav_btn_style = f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {input_bg};
                border-radius: 13px;
                padding: 3px 12px;
                color: {fg};
                font-weight: 500;
            }}
            QPushButton:hover {{
                background-color: {accent};
                color: #ffffff;
                border: 1px solid {accent};
            }}
        """
        for i in range(self.favorites_layout.count()):
            widget = self.favorites_layout.itemAt(i).widget()
            if widget:
                widget.setStyleSheet(fav_btn_style)

        self.list_view.setStyleSheet(f"""
            QListView {{ background-color: {bg}; color: {fg}; border: none; }}
            QListView::item {{ padding: 6px; border-radius: 6px; }}
            QListView::item:selected {{ background-color: {selection}; color: #ffffff; }}
            QListView::item:hover {{ background-color: {input_bg}; }}
        """)

    def set_path(self, path):
        if not self._is_navigating_history:
            old_path = self.model.rootPath()
            if old_path != path and os.path.exists(old_path):
                self._history.append(old_path)
                self._future.clear() # Clear forward history on new navigation
        
        self.btn_back.setEnabled(bool(self._history))
        self.btn_forward.setEnabled(bool(self._future))
        
        self.address_bar.set_path(path)
        idx = self.model.setRootPath(path)
        self.list_view.setRootIndex(idx)
        self.path_changed.emit(path)

    def _on_click(self, index):
        path = self.model.filePath(index)
        self.path_selected.emit(path)

    def _cut_selection(self):
        """Marca o item selecionado para ser movido (recortar)."""
        index = self.list_view.currentIndex()
        if index.isValid():
            path = self.model.filePath(index)
            self._clipboard = (path, 'cut')
            self.status_updated.emit(f"Recortado: {os.path.basename(path)}")

    def _copy_path(self, path):
        """Copia o caminho absoluto do item para o clipboard."""
        QApplication.clipboard().setText(path)
        self.status_updated.emit("Caminho copiado para a área de transferência")

    def _duplicate_item(self, path):
        """Cria uma cópia do item no mesmo diretório."""
        self._paste_to_current(source_path=path, duplicate=True)

    def _on_selection_changed(self, selected, deselected):
        selected_indexes = self.list_view.selectedIndexes()
        count = len(selected_indexes)
        
        if count == 0:
            self.selection_changed.emit(0, "")
            return

        total_size = 0
        for index in selected_indexes:
            if not self.model.isDir(index):
                total_size += self.model.size(index)
        
        if total_size < 1024:
            size_str = f"{total_size} B"
        elif total_size < 1024**2:
            size_str = f"{total_size/1024:.1f} KB"
        elif total_size < 1024**3:
            size_str = f"{total_size/1024**2:.1f} MB"
        else:
            size_str = f"{total_size/1024**3:.2f} GB"
        self.selection_changed.emit(count, size_str)

    def _on_double_click(self, index):
        path = self.model.filePath(index)
        if self.model.isDir(index):
            self.set_path(path)
        else:
            self.path_confirmed.emit(path)

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        index = self.list_view.indexAt(pos)
        
        # Apply theme
        bg = self.theme.get("background", "#1e1e1e")
        fg = self.theme.get("foreground", "#cccccc")
        accent = self.theme.get("accent", "#007acc")
        menu.setStyleSheet(f"QMenu {{ background-color: {bg}; color: {fg}; }} QMenu::item:selected {{ background-color: {accent}; }}")
        
        # --- Ações no item selecionado ---
        if index.isValid():
            path = self.model.filePath(index)
            
            # --- Ações principais (Abrir, etc) ---
            if not self.model.isDir(index):
                open_action = menu.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOkButton), "Abrir")
                open_action.triggered.connect(lambda: self.path_confirmed.emit(path))
                menu.addSeparator()

            # --- Ações de Edição (Recortar, Copiar, Colar) ---
            cut_action = menu.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileLinkIcon), "Recortar (Ctrl+X)")
            cut_action.triggered.connect(self._cut_selection)
            
            copy_action = menu.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView), "Copiar (Ctrl+C)")
            copy_action.triggered.connect(self._copy_selection)

            # Ação de colar só aparece se houver algo no clipboard
            if self._clipboard and os.path.exists(self._clipboard[0]):
                paste_action = menu.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DirLinkIcon), "Colar (Ctrl+V)")
                paste_action.triggered.connect(self._paste_to_current)
            
            menu.addSeparator()

            # --- Ações de Modificação (Excluir, Renomear, Duplicar) ---
            delete_action = menu.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon), "Excluir (Del)")
            delete_action.triggered.connect(lambda: self._delete_item(path))

            rename_action = menu.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_LineEditClearButton), "Renomear")
            rename_action.triggered.connect(lambda: self._rename_item(path))

            duplicate_action = menu.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), "Duplicar")
            duplicate_action.triggered.connect(lambda: self._duplicate_item(path))

            menu.addSeparator()

            # --- Ações de Atalho/Info ---
            if self.model.isDir(index) and self.provider:
                add_fav_action = menu.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton), "Adicionar aos Favoritos")
                add_fav_action.triggered.connect(lambda: self._add_to_favorites(path))

            copy_path_action = menu.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DirLinkIcon), "Copiar Caminho")
            copy_path_action.triggered.connect(lambda: self._copy_path(path))
            
            properties_action = menu.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogInfoView), "Propriedades")
            properties_action.triggered.connect(lambda: self._show_properties_dialog(path))

        # --- Ações de criação (sempre visíveis) ---
        menu.addSeparator()
        new_folder = menu.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon), "Nova Pasta")
        new_folder.triggered.connect(lambda: self._create_item(is_folder=True))
        
        new_file = menu.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon), "Novo Arquivo")
        new_file.triggered.connect(lambda: self._create_item(is_folder=False))
        
        # --- Colar (se houver algo no clipboard e nenhum item selecionado) ---
        if not index.isValid() and self._clipboard and os.path.exists(self._clipboard[0]):
            menu.addSeparator()
            paste_action = menu.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DirLinkIcon), "Colar (Ctrl+V)")
            paste_action.triggered.connect(self._paste_to_current)
        
        menu.exec(self.list_view.mapToGlobal(pos))

    def _show_properties_dialog(self, path):
        try:
            stat = os.stat(path)
            size = stat.st_size
            
            if size < 1024: size_str = f"{size} Bytes"
            elif size < 1024**2: size_str = f"{size/1024:.2f} KB ({size:,} Bytes)"
            elif size < 1024**3: size_str = f"{size/1024**2:.2f} MB ({size:,} Bytes)"
            else: size_str = f"{size/1024**3:.2f} GB ({size:,} Bytes)"

            type_str = "Pasta" if os.path.isdir(path) else f"Arquivo ({os.path.splitext(path)[1]})"
            created = datetime.fromtimestamp(stat.st_ctime).strftime('%d/%m/%Y %H:%M:%S')
            modified = datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m/%Y %H:%M:%S')

            info = (f"<b>Nome:</b> {os.path.basename(path)}<br>"
                    f"<b>Tipo:</b> {type_str}<br>"
                    f"<b>Local:</b> {os.path.dirname(path)}<br><hr>"
                    f"<b>Tamanho:</b> {size_str}<br><hr>"
                    f"<b>Criado em:</b> {created}<br>"
                    f"<b>Modificado em:</b> {modified}<br>")
            
            QMessageBox.information(self, f"Propriedades de {os.path.basename(path)}", info)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Não foi possível obter as propriedades: {e}")

    def _add_to_favorites(self, path):
        """Adiciona um caminho aos favoritos através do provider."""
        if not self.provider:
            return
        name, ok = QInputDialog.getText(self, "Adicionar Favorito", "Nome do Favorito:", text=os.path.basename(path))
        if ok and name:
            self.provider.add_custom_category(name, path)

    def _create_item(self, is_folder):
        current_dir = self.model.rootPath()
        type_str = "Pasta" if is_folder else "Arquivo"
        name, ok = QInputDialog.getText(self, f"Nova {type_str}", f"Nome da {type_str}:")
        if ok and name:
            try:
                path = os.path.join(current_dir, name)
                if is_folder:
                    os.mkdir(path)
                else:
                    with open(path, 'w', encoding='utf-8') as f:
                        pass # Cria um arquivo vazio
            except Exception as e:
                QMessageBox.critical(self, "Erro", str(e))

    def _rename_item(self, path):
        old_name = os.path.basename(path)
        dir_path = os.path.dirname(path)
        
        name, ok = QInputDialog.getText(self, "Renomear", "Novo nome:", text=old_name)
        if ok and name and name != old_name:
            new_path = os.path.join(dir_path, name)
            try:
                os.rename(path, new_path)
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao renomear: {e}")

    def _delete_item(self, path):
        name = os.path.basename(path)
        reply = QMessageBox.question(self, "Excluir", f"Tem certeza que deseja excluir '{name}'?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except Exception as e:
                QMessageBox.critical(self, "Erro", f"Erro ao excluir: {e}")

    def _copy_selection(self):
        index = self.list_view.currentIndex()
        if index.isValid():
            path = self.model.filePath(index)
            self._clipboard = (path, 'copy')
            self.status_updated.emit(f"Copiado: {os.path.basename(path)}")

    def _paste_to_current(self, source_path=None, duplicate=False):
        if not source_path:
            if not self._clipboard: return
            source_path, operation = self._clipboard
            if not os.path.exists(source_path):
                self._clipboard = None
                return
        else:
            operation = 'copy'

        dest_dir = self.model.rootPath()
        src_name = os.path.basename(source_path)
        dest_path = os.path.join(dest_dir, src_name)

        if dest_path == source_path and not duplicate:
            return

        # Evita sobrescrever
        if os.path.exists(dest_path):
            if operation == 'cut':
                 QMessageBox.warning(self, "Mover", f"Não é possível mover. Já existe um item com o nome '{src_name}' no destino.")
                 return
            base, ext = os.path.splitext(src_name)
            counter = 1
            suffix = "_cópia" if duplicate else "_copy"
            while os.path.exists(dest_path):
                dest_path = os.path.join(dest_dir, f"{base}{suffix}{counter if counter > 1 else ''}{ext}")
                counter += 1

        try:
            if operation == 'copy':
                if os.path.isdir(source_path):
                    shutil.copytree(source_path, dest_path)
                else:
                    shutil.copy2(source_path, dest_path)
                self.status_updated.emit(f"{'Duplicado' if duplicate else 'Colado'}: {os.path.basename(dest_path)}")
            else:
                shutil.move(source_path, dest_path)
                self.status_updated.emit(f"Movido: {os.path.basename(dest_path)}")
                self._clipboard = None # Limpa o clipboard após mover
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Erro ao {operation}: {e}")

    def _delete_selection(self):
        index = self.list_view.currentIndex()
        if index.isValid():
            self._delete_item(self.model.filePath(index))

    def eventFilter(self, obj, event):
        if obj == self.list_view and event.type() == QEvent.Type.KeyPress:
            if event.matches(QKeySequence.Copy):
                self._copy_selection()
                return True
            elif event.matches(QKeySequence.Cut):
                self._cut_selection()
                return True
            elif event.matches(QKeySequence.Paste):
                self._paste_to_current()
                return True
            elif event.key() == Qt.Key.Key_Delete:
                self._delete_selection()
                return True
        return super().eventFilter(obj, event)

    def _on_directory_loaded(self, path):
        """Atualiza a barra de status com contagem e espaço em disco."""
        count = self.model.rowCount(self.list_view.rootIndex())
        try:
            if count == 0:
                self.empty_label.show()
            else:
                self.empty_label.hide()

            # Apenas atualiza o status se a seleção estiver vazia
            if len(self.list_view.selectedIndexes()) > 0: return
            _, _, free = shutil.disk_usage(path)
            free_gb = free / (1024**3)
            self.status_updated.emit(f"{count} itens | Livre: {free_gb:.2f} GB")
        except:
            self.status_updated.emit(f"{count} itens")

    def _on_item_entered(self, index):
        """Mostra tooltip com informações da pasta."""
        if not index.isValid(): return
        
        if self.model.isDir(index):
            path = self.model.filePath(index)
            
            # Cancela thread anterior se existir
            if self._stats_thread and self._stats_thread.isRunning():
                self._stats_thread.stop()
                self._stats_thread.wait()
            
            self._stats_thread = FolderStatsThread(path)
            self._stats_thread.stats_ready.connect(self._show_folder_tooltip)
            self._stats_thread.start()
            
            QToolTip.showText(QCursor.pos(), "Calculando...", self.list_view)

    def _show_folder_tooltip(self, path, count, size_gb):
        text = f"<b>{os.path.basename(path)}</b><br>Arquivos: {count}<br>Tamanho: {size_gb:.2f} GB"
        # Verifica se o mouse ainda está sobre o item (opcional, mas bom para UX)
        QToolTip.showText(QCursor.pos(), text, self.list_view)