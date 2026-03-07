from PySide6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel, QMenu, QInputDialog, QFileDialog, QStyle, QLineEdit, QAbstractItemView
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon, QColor
import os

class SidebarListWidget(QListWidget):
    """ListWidget personalizado para aceitar Drag & Drop de pastas."""
    def __init__(self, provider, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setProperty("is_dropping", False)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            self.setProperty("is_dropping", True)
            self.style().polish(self) # Força a atualização do estilo
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            super().dragMoveEvent(event)
    
    def dragLeaveEvent(self, event):
        self.setProperty("is_dropping", False)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self.setProperty("is_dropping", False)
        self.style().polish(self)
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = url.toLocalFile()
                if os.path.exists(path) and os.path.isdir(path):
                    self.provider.add_custom_category(os.path.basename(path), path)
            event.accept()
        else:
            super().dropEvent(event)

class TasmaSidebar(QWidget):
    """Barra lateral do TasmaFile."""
    
    category_selected = Signal(str, str) # tipo, dados (caminho ou id)

    def __init__(self, provider, parent=None):
        super().__init__(parent)
        self.provider = provider
        self.setFixedWidth(200)
        self.theme = {}
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Buscar...")
        self.search_bar.textChanged.connect(self._filter_items)
        layout.addWidget(self.search_bar)

        self.list_widget = SidebarListWidget(self.provider)
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        
        # Context Menu
        self.list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(self.list_widget)
        self._populate()

    def apply_theme(self, theme):
        self.theme = theme
        bg = theme.get("sidebar_bg", "#252526")
        fg = theme.get("foreground", "#cccccc")
        border = theme.get("border_color", "#3e3e42")
        hover = theme.get("selection", "#37373d")
        
        self.setStyleSheet(f"background-color: {bg}; border-right: 1px solid {border};")

        input_bg = theme.get("background", "#1e1e1e")
        self.search_bar.setStyleSheet(f"""
            QLineEdit {{ background-color: {input_bg}; color: {fg}; padding: 5px; border: 1px solid {border}; border-radius: 4px; }}
        """)
        
        self.list_widget.setStyleSheet(f"""
            QListWidget {{ border: none; background-color: transparent; color: {fg}; font-size: 13px; }}
            QListWidget::item {{ padding: 8px; border-radius: 4px; margin: 2px 5px; }}
            QListWidget::item:selected {{ background-color: {hover}; color: white; }}
            QListWidget::item:hover {{ background-color: {border}; }}
        """)
        self.list_widget.setStyleSheet(self.list_widget.styleSheet() + f"""
            SidebarListWidget[is_dropping="true"] {{ border: 2px dashed {theme.get('accent', '#007acc')}; }}
        """)

    def _get_icon_for_type(self, type_id):
        """Retorna um ícone padrão com base no tipo de categoria."""
        style = self.style()
        icon_map = {
            "trash": QStyle.StandardPixmap.SP_TrashIcon,
            "custom": QStyle.StandardPixmap.SP_DirLinkIcon,
            "root": QStyle.StandardPixmap.SP_ComputerIcon,
            "home": QStyle.StandardPixmap.SP_DirHomeIcon,
            "recent": QStyle.StandardPixmap.SP_DirOpenIcon,
            "source": QStyle.StandardPixmap.SP_FileIcon,
            "plugins_root": QStyle.StandardPixmap.SP_FileDialogDetailedView,
            "config_general": QStyle.StandardPixmap.SP_ToolBarHorizontalExtensionButton,
        }
        pixmap_enum = icon_map.get(type_id, QStyle.StandardPixmap.SP_FileIcon)
        return style.standardIcon(pixmap_enum)

    def _populate(self):
        # Limpa a lista para evitar duplicatas ao recarregar
        self.list_widget.clear()

        # Seção: Navegação
        
        # Seção: Favoritos (Custom)
        custom = self.provider.get_custom_categories()
        if custom:
            self._add_header("FAVORITOS")
            for name, path in custom.items():
                self._add_item(name, "custom", path)

        self._add_header("NAVEGAÇÃO")
        trash_path = self.provider.get_trash_dir()
        if trash_path and os.path.exists(trash_path):
            self._add_item("Lixeira", "trash", trash_path)

        self._add_item("Este Computador", "root", self.provider.get_root_dir())
        self._add_item("Pasta de Usuário", "home", self.provider.get_home_dir())
        
        # Seção: Projetos
        self._add_header("PROJETOS")
        recents = self.provider.get_recent_projects()
        for path in recents:
            self._add_item(path.split("/")[-1], "recent", path)
            
        # Seção: Sistema JCode
        self._add_header("JCODE SYSTEM")
        self._add_item("Código Fonte", "source", self.provider.get_editor_source())
        self._add_item("Plugins", "plugins_root", "plugins_virtual_root") # Placeholder logic

        # Seção: Configurações
        self._add_header("CONFIGURAÇÕES")
        self._add_item("Geral", "config_general", "config_general_view")

        if hasattr(self, 'search_bar') and self.search_bar.text():
            self._filter_items(self.search_bar.text())

    def _add_header(self, text):
        item = QListWidgetItem(text)
        item.setFlags(Qt.NoItemFlags) # Não selecionável
        item.setForeground(QColor("#808080"))
        font = item.font()
        font.setBold(True)
        font.setPointSize(10)
        item.setFont(font)
        self.list_widget.addItem(item)

    def _add_item(self, label, type_id, data):
        icon = self._get_icon_for_type(type_id)
        item = QListWidgetItem(icon, label)
        item.setData(Qt.UserRole, {"type": type_id, "data": data})
        self.list_widget.addItem(item)

    def _on_item_clicked(self, item):
        data = item.data(Qt.UserRole)
        if data:
            self.category_selected.emit(data["type"], data["data"])

    def _filter_items(self, text):
        search_text = text.lower()

        header_indices = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.flags() == Qt.NoItemFlags:
                header_indices.append(i)

        # Se não houver texto na busca, mostra tudo e sai
        if not search_text:
            for i in range(self.list_widget.count()):
                self.list_widget.item(i).setHidden(False)
            return

        # Itera sobre cada seção (delimitada por cabeçalhos)
        for i in range(len(header_indices)):
            start_index = header_indices[i] + 1
            end_index = header_indices[i+1] if (i + 1) < len(header_indices) else self.list_widget.count()
            
            header_item = self.list_widget.item(header_indices[i])
            section_has_visible_items = False

            for j in range(start_index, end_index):
                item = self.list_widget.item(j)
                data = item.data(Qt.UserRole)
                # Obtém o caminho ou ID associado ao item
                item_path = str(data.get("data", "")) if data else ""
                
                if search_text in item.text().lower() or search_text in item_path.lower():
                    item.setHidden(False)
                    section_has_visible_items = True
                else:
                    item.setHidden(True)
            
            header_item.setHidden(not section_has_visible_items)

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        
        # Apply theme
        bg = self.theme.get("sidebar_bg", "#252526")
        fg = self.theme.get("foreground", "#cccccc")
        accent = self.theme.get("accent", "#007acc")
        menu.setStyleSheet(f"QMenu {{ background-color: {bg}; color: {fg}; }} QMenu::item:selected {{ background-color: {accent}; }}")
        
        add_action = menu.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton), "Adicionar aos Favoritos")
        add_action.triggered.connect(self._add_category_dialog)
        
        item = self.list_widget.itemAt(pos)
        if item:
            data = item.data(Qt.UserRole)
            if data and data.get("type") == "custom":
                name = item.text()
                remove_action = menu.addAction(self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon), f"Remover '{name}'")
                remove_action.triggered.connect(lambda: self.provider.remove_custom_category(name) or self._populate())

        menu.exec(self.list_widget.mapToGlobal(pos))

    def _add_category_dialog(self):
        path = QFileDialog.getExistingDirectory(self, "Selecionar Pasta para Favoritos")
        if path:
            name, ok = QInputDialog.getText(self, "Adicionar Favorito", "Nome:", text=os.path.basename(path))
            if ok and name:
                self.provider.add_custom_category(name, path)
                self._populate()