"""
Task Manager - GUI Components Module
Reusable UI components for Task Manager application
Python 3.14+ Compatible
Apple-level UX/UI Design
"""
try:
    import customtkinter as ctk
except ImportError:
    import sys
    print("⚠️ Ошибка: Не установлен customtkinter. Выполните: pip install -r requirements.txt")
    sys.exit(1)

from datetime import datetime
from typing import Callable, Optional
from functools import lru_cache

try:
    from ..core import Task, TaskStatus, Priority
    from ..utils.helpers import format_time_spent
except ImportError:
    import sys
    from pathlib import Path
    src_path = Path(__file__).parent.parent
    sys.path.insert(0, str(src_path))
    from core import Task, TaskStatus, Priority
    from utils.helpers import format_time_spent


# ============================================================================
# CONFIGURATION & CONSTANTS - Apple-inspired Design System
# ============================================================================

COLORS = {
    # Backgrounds
    "bg_dark": "#0a0a0a",
    "bg_card": "#1c1c1e",
    "bg_card_light": "#2c2c2e",
    "bg_button": "#3a3a3c",
    "bg_button_cancel": "#636366",
    "bg_button_delete": "#ff453a",
    
    # Text
    "text_primary": "#f5f5f7",
    "text_secondary": "#86868b",
    "text_muted": "#636366",
    
    # Priority colors
    "priority_low": "#30d158",
    "priority_medium": "#ff9f0a",
    "priority_high": "#ff453a",
    
    # Status colors
    "status_todo": "#8e8e93",
    "status_in_progress": "#ff9f0a",
    "status_done": "#30d158",
    
    # Accents
    "accent_blue": "#0a84ff",
    "accent_purple": "#bf5af2",
}

FONTS = {
    "title": ("SF Pro Display", 24, "bold"),
    "heading": ("SF Pro Display", 18, "bold"),
    "label_bold": ("SF Pro Text", 13, "bold"),
    "label": ("SF Pro Text", 13, "normal"),
    "small": ("SF Pro Text", 11, "normal"),
    "tiny": ("SF Pro Text", 9, "normal"),
}

SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 16,
    "lg": 24,
    "xl": 32,
}

RADIUS = {
    "small": 6,
    "medium": 10,
    "large": 14,
    "xlarge": 20,
}

DIMENSIONS = {
    "entry_height": 44,
    "button_height": 40,
    "button_width": 120,
    "card_corner_radius": 12,
    "button_corner_radius": 8,
}


class PrioritySelector(ctk.CTkFrame):
    """Компонент выбора приоритета с визуальной индикацией."""
    
    def __init__(self, parent, on_change: Callable[[str], None] | None = None, initial_value: str = "Medium"):
        super().__init__(parent, fg_color=COLORS["bg_card"])
        
        self.on_change = on_change
        self.priority_var = ctk.StringVar(value=initial_value)
        
        self._create_widgets()
        self._on_priority_change(initial_value)
    
    def _create_widgets(self):
        """Создание виджетов селектора."""
        priorities = [
            ("Low", COLORS["priority_low"]),
            ("Medium", COLORS["priority_medium"]),
            ("High", COLORS["priority_high"])
        ]
        
        for i, (prio_name, color) in enumerate(priorities):
            radio_btn = ctk.CTkRadioButton(
                self, 
                text=f"● {prio_name}", 
                variable=self.priority_var, 
                value=prio_name,
                text_color=COLORS["text_primary"],
                fg_color=color,
                hover_color=color,
                command=lambda p=prio_name: self._on_priority_change(p)
            )
            radio_btn.grid(row=0, column=i, padx=SPACING["md"], sticky="w", pady=SPACING["xs"])
        
        # Индикатор текущего приоритета
        self.priority_indicator = ctk.CTkLabel(
            self, text="", font=("Arial", 24, "bold"),
            text_color=COLORS["priority_medium"]
        )
        self.priority_indicator.grid(row=0, column=3, padx=SPACING["lg"])
    
    def _on_priority_change(self, priority: str):
        """Обработка изменения приоритета."""
        color_map = {
            "Low": COLORS["priority_low"],
            "Medium": COLORS["priority_medium"],
            "High": COLORS["priority_high"]
        }
        self.priority_indicator.configure(text="●", text_color=color_map[priority])
        
        if self.on_change:
            self.on_change(priority)
    
    def get_priority(self) -> str:
        """Получить текущий приоритет."""
        return self.priority_var.get()
    
    def set_priority(self, priority: str):
        """Установить приоритет."""
        self.priority_var.set(priority)
        self._on_priority_change(priority)


class DateEntry(ctk.CTkFrame):
    """Компонент ввода даты с подсказкой."""
    
    def __init__(self, parent, label: str, placeholder: str = "", hint: str = ""):
        super().__init__(parent, fg_color="transparent")
        
        self._create_widgets(label, placeholder, hint)
    
    def _create_widgets(self, label: str, placeholder: str, hint: str):
        """Создание виджетов."""
        ctk.CTkLabel(
            self, text=label, font=FONTS["label_bold"], 
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", pady=(0, SPACING["sm"]))
        
        self.entry = ctk.CTkEntry(
            self, 
            width=200, 
            height=DIMENSIONS["entry_height"],
            placeholder_text=placeholder,
            font=FONTS["label"]
        )
        self.entry.pack(anchor="w", pady=(0, SPACING["md"]))
        
        if hint:
            hint_label = ctk.CTkLabel(
                self, text=hint,
                font=FONTS["tiny"], text_color=COLORS["text_secondary"]
            )
            hint_label.pack(anchor="w")
    
    def get_value(self) -> str:
        """Получить значение."""
        return self.entry.get().strip()
    
    def set_value(self, value: str):
        """Установить значение."""
        self.entry.delete(0, 'end')
        self.entry.insert(0, value)
    
    def clear(self):
        """Очистить поле."""
        self.entry.delete(0, 'end')


class StatusBadge(ctk.CTkLabel):
    """Бейдж статуса задачи."""
    
    STATUS_CONFIG = {
        TaskStatus.TODO: {"icon": "📝", "color": COLORS["status_todo"]},
        TaskStatus.IN_PROGRESS: {"icon": "🔄", "color": COLORS["status_in_progress"]},
        TaskStatus.DONE: {"icon": "✅", "color": COLORS["status_done"]},
    }
    
    def __init__(self, parent, status: TaskStatus, **kwargs):
        config = self.STATUS_CONFIG.get(status, {"icon": "📌", "color": "#999999"})
        
        super().__init__(
            parent,
            text=config["icon"],
            font=("Arial", 12),
            text_color=config["color"],
            **kwargs
        )
        
        self._status = status
    
    def set_status(self, status: TaskStatus):
        """Обновить статус."""
        config = self.STATUS_CONFIG.get(status, {"icon": "📌", "color": "#999999"})
        self.configure(text=config["icon"], text_color=config["color"])
        self._status = status
    
    def get_status(self) -> TaskStatus:
        """Получить текущий статус."""
        return self._status


class ActionButton(ctk.CTkButton):
    """Стандартизированная кнопка действий."""
    
    def __init__(self, parent, text: str, command: Callable | None = None, 
                 style: str = "default", width: int | None = None, **kwargs):
        
        style_config = {
            "default": {"fg": COLORS["accent_blue"], "hover": "#1976D2"},
            "cancel": {"fg": COLORS["bg_button_cancel"], "hover": "#555555"},
            "delete": {"fg": COLORS["bg_button_delete"], "hover": "#d63026"},
            "secondary": {"fg": COLORS["bg_button"], "hover": "#555555"},
        }
        
        config = style_config.get(style, style_config["default"])
        
        super().__init__(
            parent,
            text=text,
            command=command,
            width=width or DIMENSIONS["button_width"],
            height=DIMENSIONS["button_height"],
            fg_color=config["fg"],
            hover_color=config["hover"],
            corner_radius=DIMENSIONS["button_corner_radius"],
            font=FONTS["label"],
            **kwargs
        )


class CardFrame(ctk.CTkFrame):
    """Базовый класс для карточек в стиле Apple."""
    
    def __init__(self, parent, **kwargs):
        super().__init__(
            parent,
            fg_color=COLORS["bg_card"],
            corner_radius=RADIUS["large"],
            **kwargs
        )


__all__ = [
    'PrioritySelector',
    'DateEntry',
    'StatusBadge',
    'ActionButton',
    'CardFrame',
    'COLORS',
    'FONTS',
    'SPACING',
    'RADIUS',
    'DIMENSIONS',
]
