"""
Task Manager - Modern Kanban Board
GUI Components: Main Window, Kanban Board, Dashboard with Charts
Python 3.14+ Compatible
Apple-level UX/UI Design
"""
try:
    import customtkinter as ctk
    from tkinter import messagebox
except ImportError:
    import sys
    print("⚠️ Ошибка: Не установлен customtkinter. Выполните: pip install -r requirements.txt")
    sys.exit(1)

from collections.abc import Callable
from datetime import datetime
import logging
from typing import Optional
from functools import lru_cache

try:
    from ..core import Task, TaskStatus, Priority, TaskService
except ImportError:
    import sys
    from pathlib import Path
    src_path = Path(__file__).parent.parent
    sys.path.insert(0, str(src_path))
    from core import Task, TaskStatus, Priority, TaskService

# ============================================================================
# CONFIGURATION & CONSTANTS - Apple-inspired Design System
# ============================================================================

# Colors - Refined palette with better contrast and accessibility
COLORS = {
    # Backgrounds
    "bg_dark": "#0a0a0a",           # Deeper black for OLED displays
    "bg_card": "#1c1c1e",           # Apple-style card background
    "bg_card_light": "#2c2c2e",     # Slightly lighter for elevation
    "bg_button": "#3a3a3c",         # Button background
    "bg_button_cancel": "#636366",  # Secondary actions
    "bg_button_delete": "#ff453a",  # Destructive actions (Apple red)
    
    # Text
    "text_primary": "#f5f5f7",      # Apple primary text
    "text_secondary": "#86868b",    # Secondary text
    "text_muted": "#636366",        # Muted text
    
    # Priority colors (refined)
    "priority_low": "#30d158",      # Apple green
    "priority_medium": "#ff9f0a",   # Apple orange
    "priority_high": "#ff453a",     # Apple red
    
    # Status colors
    "status_todo": "#8e8e93",       # Gray
    "status_in_progress": "#ff9f0a", # Orange
    "status_done": "#30d158",       # Green
    
    # Accents
    "accent_blue": "#0a84ff",       # Apple blue
    "accent_purple": "#bf5af2",     # Purple
    "hover_overlay": "rgba(255,255,255,0.08)",  # Subtle hover
}

# Typography - San Francisco-like font stack
FONTS = {
    "title": ("SF Pro Display", 24, "bold"),
    "heading": ("SF Pro Display", 18, "semibold"),
    "label_bold": ("SF Pro Text", 13, "bold"),
    "label": ("SF Pro Text", 13, "regular"),
    "small": ("SF Pro Text", 11, "regular"),
    "tiny": ("SF Pro Text", 9, "regular"),
    "caption": ("SF Pro Text", 12, "italic"),
}

# Spacing - 8pt grid system
SPACING = {
    "xs": 4,
    "sm": 8,
    "md": 16,
    "lg": 24,
    "xl": 32,
}

# Border radius - Apple-style smooth corners
RADIUS = {
    "small": 6,
    "medium": 10,
    "large": 14,
    "xlarge": 20,
}

# Animation timing (ms)
ANIMATION = {
    "fast": 150,
    "normal": 250,
    "slow": 350,
}

# Window dimensions
DIMENSIONS = {
    "window_width": 1440,
    "window_height": 900,
    "dialog_width": 560,
    "dialog_height": 520,
    "header_height": 80,
    "card_min_height": 100,
    "entry_height": 44,
    "button_height": 40,
    "button_min_width": 120,
    "padding_small": 8,
    "padding_medium": 16,
    "padding_large": 24,
}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Helper functions for Apple-style UI
def get_system_font(family: str = "SF Pro Text") -> str:
    """Получить системный шрифт с fallback на Arial."""
    try:
        # Try to use system fonts if available
        return family
    except Exception:
        return "Arial"


class TaskDialog(ctk.CTkToplevel):
    """Диалог создания/редактирования задачи с улучшенным UX в стиле Apple."""
    
    def __init__(self, parent, task: Task | None = None, on_save: Callable | None = None):
        super().__init__(parent)
        
        self.task = task
        self.on_save = on_save
        self.is_editing = task is not None
        
        # Setup window first
        self._setup_window()
        self._create_widgets()
        
        if self.task:
            self._fill_data(self.task)
        else:
            # Фокус на поле заголовка для новой задачи
            self.after(100, lambda: self.title_entry.focus_set())
    
    def _setup_window(self):
        """Настройка окна диалога в стиле Apple."""
        width = DIMENSIONS["dialog_width"]
        height = DIMENSIONS["dialog_height"]
        
        title = "✏️ Редактирование задачи" if self.is_editing else "➕ Новая задача"
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.resizable(False, False)
        self.configure(fg_color=COLORS["bg_dark"])
        
        # Центрирование окна с анимацией появления
        self.update_idletasks()
        screen_x = (self.winfo_screenwidth() - width) // 2
        screen_y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"+{screen_x}+{screen_y}")
        
        # Привязка клавиш для быстрого управления
        self.bind('<Return>', lambda e: self._save())
        self.bind('<Escape>', lambda e: self.destroy())
        
        # Сделать диалог модальным
        self.transient(self.master)
        self.grab_set()
    
    def _create_widgets(self):
        """Создание виджетов диалога с улучшенной эргономикой."""
        # Используем SPACING константы для консистентности
        main_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True, padx=SPACING["lg"], pady=SPACING["lg"])
        
        self._create_title_field(main_frame)
        self._create_description_field(main_frame)
        self._create_priority_field(main_frame)
        self._create_due_date_field(main_frame)
        self._create_start_date_field(main_frame)  # Для диаграммы Ганта
        self._create_time_spent_field(main_frame)
        self._create_buttons(main_frame)
    
    def _create_title_field(self, parent):
        """Поле заголовка с улучшенным UX."""
        ctk.CTkLabel(
            parent, text="Заголовок *", font=FONTS["label_bold"], 
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", pady=(0, SPACING["sm"]))
        
        self.title_entry = ctk.CTkEntry(
            parent, 
            width=DIMENSIONS["dialog_width"] - SPACING["xl"], 
            height=DIMENSIONS["entry_height"],
            placeholder_text="Введите название задачи...",
            font=FONTS["label"],
            corner_radius=RADIUS["medium"]
        )
        self.title_entry.pack(fill="x", pady=(0, SPACING["md"]))
        
        # Добавить визуальный фокус при клике
        self.title_entry.bind("<FocusIn>", lambda e: self.title_entry.configure(fg_color="#3a3a3c"))
        self.title_entry.bind("<FocusOut>", lambda e: self.title_entry.configure(fg_color="#2c2c2e"))
    
    def _create_description_field(self, parent):
        """Поле описания с авто-размером."""
        ctk.CTkLabel(
            parent, text="Описание", font=FONTS["label_bold"], 
            text_color=COLORS["text_primary"]
        ).pack(anchor="w", pady=(0, SPACING["sm"]))
        
        self.desc_text = ctk.CTkTextbox(
            parent, 
            width=DIMENSIONS["dialog_width"] - SPACING["xl"], 
            height=120,
            font=FONTS["small"],
            corner_radius=RADIUS["medium"]
        )
        self.desc_text.pack(fill="x", pady=(0, SPACING["md"]))
    
    def _create_priority_field(self, parent):
        """Выбор приоритета с визуальной индикацией."""
        ctk.CTkLabel(parent, text="Приоритет", font=FONTS["label_bold"], 
                    text_color=COLORS["text_primary"]).pack(anchor="w", pady=(0, 5))
        
        self.priority_var = ctk.StringVar(value="Medium")
        priority_frame = ctk.CTkFrame(parent, fg_color=COLORS["bg_card"])
        priority_frame.pack(fill="x", pady=(0, DIMENSIONS["padding_medium"]))
        
        priorities = [
            ("Low", COLORS["priority_low"]),
            ("Medium", COLORS["priority_medium"]),
            ("High", COLORS["priority_high"])
        ]
        
        for i, (prio_name, color) in enumerate(priorities):
            radio_btn = ctk.CTkRadioButton(
                priority_frame, 
                text=f"● {prio_name}", 
                variable=self.priority_var, 
                value=prio_name,
                text_color=COLORS["text_primary"],
                fg_color=color,
                hover_color=color,
                command=lambda p=prio_name: self._on_priority_change(p)
            )
            radio_btn.grid(row=0, column=i, padx=DIMENSIONS["padding_medium"], 
                          sticky="w", pady=DIMENSIONS["padding_small"])
        
        # Индикатор текущего приоритета
        self.priority_indicator = ctk.CTkLabel(
            priority_frame, text="", font=("Arial", 24, "bold"),
            text_color=COLORS["priority_medium"]
        )
        self.priority_indicator.grid(row=0, column=3, padx=DIMENSIONS["padding_large"])
        self._on_priority_change("Medium")
    
    def _on_priority_change(self, priority: str):
        """Обработка изменения приоритета."""
        color_map = {
            "Low": COLORS["priority_low"],
            "Medium": COLORS["priority_medium"],
            "High": COLORS["priority_high"]
        }
        self.priority_indicator.configure(text="●", text_color=color_map[priority])
    
    def _create_due_date_field(self, parent):
        """Поле дедлайна."""
        ctk.CTkLabel(parent, text="Дедлайн (ГГГГ-ММ-ДД)", font=FONTS["label_bold"], 
                    text_color=COLORS["text_primary"]).pack(anchor="w", pady=(0, 5))
        self.due_entry = ctk.CTkEntry(
            parent, width=200, height=DIMENSIONS["entry_height"],
            placeholder_text="2025-12-31",
            font=FONTS["label"]
        )
        self.due_entry.pack(anchor="w", pady=(0, DIMENSIONS["padding_medium"]))
        
        hint_label = ctk.CTkLabel(
            parent, text="💡 Оставьте пустым, если нет дедлайна",
            font=FONTS["tiny"], text_color=COLORS["text_secondary"]
        )
        hint_label.pack(anchor="w")
    
    def _create_time_spent_field(self, parent):
        """Поле затраченного времени."""
        ctk.CTkLabel(parent, text="Затрачено времени (часы)", font=FONTS["label_bold"], 
                    text_color=COLORS["text_primary"]).pack(anchor="w", pady=(0, 5))
        self.time_entry = ctk.CTkEntry(
            parent, width=200, height=DIMENSIONS["entry_height"],
            placeholder_text="0.0",
            font=FONTS["label"]
        )
        self.time_entry.pack(anchor="w", pady=(0, DIMENSIONS["padding_medium"]))
    
    def _create_start_date_field(self, parent):
        """Поле даты начала для диаграммы Ганта."""
        ctk.CTkLabel(parent, text="Дата начала (ГГГГ-ММ-ДД)", font=FONTS["label_bold"], 
                    text_color=COLORS["text_primary"]).pack(anchor="w", pady=(0, 5))
        self.start_date_entry = ctk.CTkEntry(
            parent, width=200, height=DIMENSIONS["entry_height"],
            placeholder_text=f"{datetime.now().strftime('%Y-%m-%d')}",
            font=FONTS["label"]
        )
        self.start_date_entry.pack(anchor="w", pady=(0, DIMENSIONS["padding_medium"]))
        
        hint_label = ctk.CTkLabel(
            parent, text="💡 Для отображения на диаграмме Ганта",
            font=FONTS["tiny"], text_color=COLORS["text_secondary"]
        )
        hint_label.pack(anchor="w")
    
    def _create_buttons(self, parent):
        """Кнопки действий."""
        btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(DIMENSIONS["padding_medium"], 0))
        
        # Left side: Cancel button
        cancel_btn = ctk.CTkButton(
            btn_frame, text="❌ Отмена", command=self.destroy,
            width=DIMENSIONS["button_width"], height=DIMENSIONS["button_height"],
            fg_color=COLORS["bg_button_cancel"], hover_color="#555555",
            corner_radius=DIMENSIONS["button_corner_radius"],
            font=FONTS["label"]
        )
        cancel_btn.pack(side="left")
        
        # Right side: Save and optional status change
        right_frame = ctk.CTkFrame(btn_frame, fg_color="transparent")
        right_frame.pack(side="right")
        
        # Status change buttons (only for editing)
        if self.is_editing and self.task:
            status_label = ctk.CTkLabel(
                right_frame, text="Статус:", 
                font=FONTS["small"], text_color=COLORS["text_secondary"]
            )
            status_label.pack(side="left", padx=(0, 5))
            
            for status in [TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.DONE]:
                icon, color = self._get_status_icon_color(status)
                is_current = status == self.task.status
                
                status_btn = ctk.CTkButton(
                    right_frame, text=icon, width=36, height=DIMENSIONS["button_height"],
                    fg_color=color if is_current else COLORS["bg_button"],
                    hover_color=self._lighten_color(color) if is_current else "#555555",
                    corner_radius=DIMENSIONS["button_corner_radius"],
                    command=lambda s=status: self._change_status_and_save(s),
                    font=("Arial", 12)
                )
                status_btn.pack(side="left", padx=2)
        
        # Save button
        save_text = "💾 Сохранить изменения" if self.is_editing else "✅ Создать задачу"
        save_btn = ctk.CTkButton(
            right_frame, text=save_text, command=self._save,
            width=DIMENSIONS["button_width"], height=DIMENSIONS["button_height"],
            corner_radius=DIMENSIONS["button_corner_radius"],
            font=("Arial", 12, "bold"),
            fg_color=COLORS["accent_blue"], hover_color="#1976D2"
        )
        save_btn.pack(side="left", padx=5)
    
    def _get_status_icon_color(self, status: TaskStatus) -> tuple:
        """Получить иконку и цвет для статуса."""
        mapping = {
            TaskStatus.TODO: ("📝", COLORS["status_todo"]),
            TaskStatus.IN_PROGRESS: ("🔄", COLORS["status_in_progress"]),
            TaskStatus.DONE: ("✅", COLORS["status_done"])
        }
        return mapping.get(status, ("📌", "#999999"))
    
    def _lighten_color(self, hex_color: str) -> str:
        """Осветлить цвет на 20%."""
        try:
            hex_color = hex_color.lstrip('#')
            r = min(255, int(hex_color[0:2], 16) + 40)
            g = min(255, int(hex_color[2:4], 16) + 40)
            b = min(255, int(hex_color[4:6], 16) + 40)
            return f"#{r:02x}{g:02x}{b:02x}"
        except (ValueError, IndexError):
            return "#666666"
    
    def _change_status_and_save(self, new_status: TaskStatus):
        """Изменить статус и сохранить задачу."""
        if self.on_save:
            task_data = self._validate_and_get_data()
            if not task_data:
                return
            task_data['status'] = new_status
            task_id = self.task.id if self.task else None
            self.on_save(task_data, task_id)
        self.destroy()
    
    def _fill_data(self, task: Task):
        """Заполнение данными существующей задачи."""
        self.title_entry.insert(0, task.title)
        self.desc_text.insert("0.0", task.description)
        self.priority_var.set(task.priority.value)
        self._on_priority_change(task.priority.value)
        
        if task.due_date:
            self.due_entry.insert(0, task.due_date)
        if task.time_spent and task.time_spent > 0:
            self.time_entry.insert(0, str(task.time_spent))
        if task.start_date:
            self.start_date_entry.insert(0, task.start_date)
    
    def _validate_and_get_data(self) -> dict | None:
        """Валидация и получение данных формы."""
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showerror("⚠️ Ошибка", "Заголовок обязателен!", parent=self)
            self.title_entry.focus_set()
            return None
        
        # Валидация времени
        time_value = self.time_entry.get().strip()
        try:
            time_spent = float(time_value) if time_value else 0.0
            if time_spent < 0:
                raise ValueError("Отрицательное значение")
        except ValueError:
            messagebox.showerror("⚠️ Ошибка", "Введите корректное число часов!", parent=self)
            self.time_entry.focus_set()
            return None
        
        # Валидация даты (если заполнена)
        due_date = self.due_entry.get().strip()
        if due_date:
            from ..utils.helpers import validate_date
            if not validate_date(due_date):
                messagebox.showerror("⚠️ Ошибка", "Некорректный формат даты! Используйте ГГГГ-ММ-ДД", 
                                   parent=self)
                self.due_entry.focus_set()
                return None
        
        priority_map = {
            "Low": Priority.LOW, 
            "Medium": Priority.MEDIUM, 
            "High": Priority.HIGH
        }
        
        result = {
            'title': title,
            'description': self.desc_text.get("0.0", "end-1c").strip(),
            'priority': priority_map[self.priority_var.get()],
            'due_date': due_date or None,
            'time_spent': time_spent
        }
        
        # Добавить start_date если есть (для диаграммы Ганта)
        if hasattr(self, 'start_date_entry') and self.start_date_entry:
            start_date = self.start_date_entry.get().strip()
            if start_date and validate_date(start_date):
                result['start_date'] = start_date
        
        return result
    
    def _save(self):
        """Сохранение задачи с валидацией."""
        task_data = self._validate_and_get_data()
        if not task_data:
            return
        
        logger.info(f"Saving task: {task_data['title']}")
        
        if self.on_save:
            task_id = self.task.id if self.task else None
            self.on_save(task_data, task_id)
        
        self.destroy()


class TaskCard(ctk.CTkFrame):
    """Карточка задачи для Kanban-доски с улучшенным UX."""
    
    def __init__(self, parent, task: Task, on_edit: Callable, on_delete: Callable, 
                 on_status_change: Callable = None, **kwargs):
        super().__init__(parent, **kwargs)
        self.task = task
        self.on_edit = on_edit
        self.on_delete = on_delete
        self.on_status_change = on_status_change
        
        # Hover effect variables
        self._original_bg = COLORS["bg_card_light"]
        self._hover_bg = "#4a4a4a"
        
        # Store buttons for status update
        self.status_buttons = {}
        self._action_buttons_parent = None
        
        self._setup_styling()
        self._render()
    
    def _setup_styling(self):
        """Настройка стилей карточки."""
        self.configure(
            fg_color=self._original_bg,
            corner_radius=DIMENSIONS["card_corner_radius"]
        )
        
        # Bind hover events for interactive feel
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
    
    def _on_enter(self, event=None):
        """Эффект при наведении."""
        self.configure(fg_color=self._hover_bg)
    
    def _on_leave(self, event=None):
        """Возврат к исходному цвету."""
        self.configure(fg_color=self._original_bg)
    
    def _render(self):
        """Отрисовка карточки."""
        self.pack(fill="x", padx=DIMENSIONS["padding_medium"], pady=DIMENSIONS["padding_small"])
        
        # Header with priority and title
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=DIMENSIONS["padding_medium"], pady=(DIMENSIONS["padding_medium"], DIMENSIONS["padding_small"]))
        
        # Priority indicator with larger dot
        prio_color = self.task.priority.color
        prio_dot = ctk.CTkLabel(
            header, text="●", text_color=prio_color,
            font=("Arial", 18, "bold")
        )
        prio_dot.pack(side="left")
        
        # Priority badge
        prio_badge = ctk.CTkLabel(
            header, text=self.task.priority.value,
            text_color=prio_color, font=FONTS["small"]
        )
        prio_badge.pack(side="left", padx=(5, 10))
        
        # Title with truncation - improved to use wraplength instead of hard cut
        title_label = ctk.CTkLabel(
            header, text=self.task.title,
            font=("Arial", 13, "bold"), anchor="w",
            wraplength=200  # Wrap text instead of cutting
        )
        title_label.pack(side="left", padx=DIMENSIONS["padding_small"], fill="x", expand=True)
        
        # Action buttons
        self._create_action_buttons(header)
        
        # Description preview with proper wrapping
        if self.task.description:
            desc_label = ctk.CTkLabel(
                self, text=self.task.description,
                text_color=COLORS["text_secondary"], font=FONTS["small"],
                justify="left", wraplength=260
            )
            desc_label.pack(anchor="w", padx=DIMENSIONS["padding_medium"], pady=(0, DIMENSIONS["padding_small"]))
        
        # Footer with metadata
        self._render_footer()
    
    def _create_action_buttons(self, parent):
        """Создание кнопок действий."""
        # Store parent reference for potential updates
        self._action_buttons_parent = parent
        
        # Status change buttons (always visible on card for quick actions)
        if self.on_status_change:
            status_btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
            status_btn_frame.pack(side="right", padx=5)
            
            # Show all status options except current one
            all_statuses = [TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.DONE]
            next_statuses = [s for s in all_statuses if s != self.task.status]
            
            for next_status in next_statuses:
                icon, color = self._get_status_icon_color(next_status)
                status_btn = ctk.CTkButton(
                    status_btn_frame, text=icon, width=28, height=28,
                    fg_color=color, hover_color=self._lighten_color(color),
                    corner_radius=DIMENSIONS["button_corner_radius"],
                    command=lambda s=next_status: self._on_status_click(s),
                    font=("Arial", 12)
                )
                status_btn.pack(side="left", padx=2)
                # Store reference for updating later
                self.status_buttons[next_status] = status_btn
        
        edit_btn = ctk.CTkButton(
            parent, text="✏️", width=32, height=28,
            fg_color=COLORS["bg_button"], hover_color="#555555",
            corner_radius=DIMENSIONS["button_corner_radius"],
            command=lambda: self.on_edit(self.task),
            font=("Arial", 14)
        )
        edit_btn.pack(side="right", padx=2)
        
        del_btn = ctk.CTkButton(
            parent, text="🗑️", width=32, height=28,
            fg_color=COLORS["bg_button_delete"], hover_color="#b71c1c",
            corner_radius=DIMENSIONS["button_corner_radius"],
            command=lambda: self.on_delete(self.task.id),
            font=("Arial", 14)
        )
        del_btn.pack(side="right", padx=2)
    
    def _on_status_click(self, new_status: TaskStatus):
        """Обработка клика по кнопке статуса."""
        if self.on_status_change:
            try:
                self.on_status_change(self.task.id, new_status)
                # Update local task status after successful change
                self.task.status = new_status
            except Exception as e:
                import logging
                logging.error(f"Error changing status: {e}")
    
    def refresh_status_buttons(self):
        """Обновить кнопки статуса после изменения статуса задачи."""
        # Clear existing buttons
        for btn in list(self.status_buttons.values()):
            btn.destroy()
        self.status_buttons.clear()
        
        # Recreate buttons based on new status
        if self.on_status_change and self._action_buttons_parent:
            # Find the status_btn_frame and recreate buttons there
            for widget in self._action_buttons_parent.winfo_children():
                if isinstance(widget, ctk.CTkFrame) and widget.cget('fg_color') == 'transparent':
                    # Clear this frame
                    for child in widget.winfo_children():
                        child.destroy()
                    # Recreate buttons
                    all_statuses = [TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.DONE]
                    next_statuses = [s for s in all_statuses if s != self.task.status]
                    
                    for next_status in next_statuses:
                        icon, color = self._get_status_icon_color(next_status)
                        status_btn = ctk.CTkButton(
                            widget, text=icon, width=28, height=28,
                            fg_color=color, hover_color=self._lighten_color(color),
                            corner_radius=DIMENSIONS["button_corner_radius"],
                            command=lambda s=next_status: self._on_status_click(s),
                            font=("Arial", 12)
                        )
                        status_btn.pack(side="left", padx=2)
                        self.status_buttons[next_status] = status_btn
                    break
    
    def _get_next_statuses(self) -> list:
        """Получить следующие возможные статусы для задачи."""
        all_statuses = [TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.DONE]
        # Return all statuses except current one
        return [s for s in all_statuses if s != self.task.status]
    
    def _get_status_icon_color(self, status: TaskStatus) -> tuple:
        """Получить иконку и цвет для статуса."""
        mapping = {
            TaskStatus.TODO: ("📝", COLORS["status_todo"]),
            TaskStatus.IN_PROGRESS: ("🔄", COLORS["status_in_progress"]),
            TaskStatus.DONE: ("✅", COLORS["status_done"])
        }
        return mapping.get(status, ("📌", "#999999"))
    
    def _lighten_color(self, hex_color: str) -> str:
        """Осветлить цвет на 20%."""
        try:
            hex_color = hex_color.lstrip('#')
            r = min(255, int(hex_color[0:2], 16) + 40)
            g = min(255, int(hex_color[2:4], 16) + 40)
            b = min(255, int(hex_color[4:6], 16) + 40)
            return f"#{r:02x}{g:02x}{b:02x}"
        except (ValueError, IndexError):
            return "#666666"
    
    def _render_footer(self):
        """Отрисовка футера с мета-информацией."""
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=DIMENSIONS["padding_medium"], pady=(0, DIMENSIONS["padding_medium"]))
        
        # Due date badge
        if self.task.due_date:
            days = self.task.days_until_due()
            if days is not None:
                due_info = self._get_due_date_info(days)
                due_label = ctk.CTkLabel(
                    footer, text=due_info["text"],
                    text_color=due_info["color"],
                    font=("Arial", 10, "bold")
                )
                due_label.pack(side="left")
        
        # Time spent
        if self.task.time_spent and self.task.time_spent > 0:
            from ..utils.helpers import format_time_spent
            time_text = format_time_spent(self.task.time_spent)
            time_label = ctk.CTkLabel(
                footer, text=f"⏱ {time_text}",
                text_color=COLORS["text_secondary"], font=FONTS["small"]
            )
            time_label.pack(side="right")
        
        # ID badge
        id_label = ctk.CTkLabel(
            footer, text=f"#{self.task.id}",
            text_color=COLORS["text_muted"], font=FONTS["tiny"]
        )
        id_label.pack(side="right", padx=DIMENSIONS["padding_medium"])
    
    def _get_due_date_info(self, days: int) -> dict:
        """Получение информации о дедлайне."""
        if days < 0:
            return {
                "text": f"📅 Просрочено {-days} дн.",
                "color": COLORS["priority_high"]
            }
        elif days == 0:
            return {
                "text": "📅 Сегодня!",
                "color": COLORS["priority_high"]
            }
        elif days <= 3:
            return {
                "text": f"📅 Осталось {days} дн.",
                "color": COLORS["priority_medium"]
            }
        else:
            return {
                "text": f"📅 {self.task.due_date}",
                "color": COLORS["priority_low"]
            }


class DashboardFrame(ctk.CTkScrollableFrame):
    """Дашборд с графиками и статистикой."""
    
    def __init__(self, parent, service: TaskService, **kwargs):
        super().__init__(parent, **kwargs)
        self.service = service
        
        self._refresh()
    
    def _refresh(self):
        """Обновление дашборда."""
        # Clear existing
        for widget in self.winfo_children():
            widget.destroy()
        
        stats = self.service.get_statistics()
        
        # Title
        title = ctk.CTkLabel(self, text="📊 Дашборд", font=("Arial", 20, "bold"))
        title.pack(pady=20)
        
        # Stats cards row
        cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        cards_frame.pack(fill="x", padx=20, pady=10)
        
        self._create_stat_card(cards_frame, "Всего задач", str(stats['total']), "#2196F3", 0)
        self._create_stat_card(cards_frame, "Выполнено", f"{stats['by_status']['done']}", "#4CAF50", 1)
        self._create_stat_card(cards_frame, "В работе", f"{stats['by_status']['in_progress']}", "#FF9800", 2)
        self._create_stat_card(cards_frame, "Просрочено", f"{stats['overdue']}", "#F44336", 3)
        
        # Completion rate
        rate_frame = ctk.CTkFrame(self, fg_color="#3a3a3a", corner_radius=10)
        rate_frame.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkLabel(rate_frame, text="Процент выполнения", font=("Arial", 14, "bold")).pack(pady=10)
        
        # Progress bar
        progress = ctk.CTkProgressBar(rate_frame, width=400, height=25, corner_radius=10)
        progress.pack(pady=10)
        progress.set(stats['completion_rate'] / 100)
        
        ctk.CTkLabel(rate_frame, text=f"{stats['completion_rate']}%", 
                     font=("Arial", 18, "bold"), text_color="#4CAF50").pack(pady=5)
        
        # Charts section
        charts_frame = ctk.CTkFrame(self, fg_color="transparent")
        charts_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Status distribution chart
        self._create_chart(charts_frame, stats, "by_status", 
                          ["Todo", "In Progress", "Done"], 
                          ["#9E9E9E", "#FF9800", "#4CAF50"],
                          "Распределение по статусам")
        
        # Priority distribution chart
        self._create_chart(charts_frame, stats, "by_priority",
                          ["Low", "Medium", "High"],
                          ["#4CAF50", "#FF9800", "#F44336"],
                          "Распределение по приоритетам")
    
    def _create_stat_card(self, parent, title: str, value: str, color: str, col: int):
        """Создание карточки статистики."""
        card = ctk.CTkFrame(parent, fg_color="#3a3a3a", corner_radius=10, width=140, height=100)
        card.grid(row=0, column=col, padx=10, pady=10, sticky="nsew")
        parent.grid_columnconfigure(col, weight=1)
        
        ctk.CTkLabel(card, text=title, font=("Arial", 11), text_color="#aaaaaa").pack(pady=(15, 5))
        ctk.CTkLabel(card, text=value, font=("Arial", 28, "bold"), text_color=color).pack()
    
    def _create_chart(self, parent, stats: dict, data_key: str, labels: list, 
                      colors: list, title: str):
        """Создание круговой диаграммы."""
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from io import BytesIO
        from PIL import Image
        
        chart_frame = ctk.CTkFrame(parent, fg_color="#3a3a3a", corner_radius=10)
        chart_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        
        ctk.CTkLabel(chart_frame, text=title, font=("Arial", 14, "bold")).pack(pady=10)
        
        # Get data
        data = stats[data_key]
        values = list(data.values())
        
        if sum(values) == 0:
            ctk.CTkLabel(chart_frame, text="Нет данных", text_color="#888888").pack(pady=30)
            return
        
        # Create pie chart
        fig, ax = plt.subplots(figsize=(4, 3), facecolor='#3a3a3a')
        result = ax.pie(values, labels=labels, colors=colors, autopct='%1.0f%%',
                               textprops={'color': 'white', 'fontsize': 10})
        wedges, texts = result[0], result[1]
        ax.set_facecolor('#3a3a3a')
        
        # Save to buffer
        buf = BytesIO()
        plt.savefig(buf, format='png', bbox_inches='tight', facecolor='#3a3a3a', 
                    edgecolor='none', dpi=100)
        buf.seek(0)
        plt.close()
        
        # Load and display
        img = Image.open(buf)
        photo = ctk.CTkImage(light_image=img, dark_image=img, size=(200, 150))
        
        img_label = ctk.CTkLabel(chart_frame, image=photo, text="")
        img_label.image = photo  # Keep reference
        img_label.pack(pady=10)


class KanbanColumn(ctk.CTkScrollableFrame):
    """Колонка Kanban-доски с улучшенным оформлением."""
    
    def __init__(self, parent, status: TaskStatus, tasks: list, 
                 on_edit: Callable, on_delete: Callable, 
                 on_status_change: Callable = None, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.status = status
        self.on_edit = on_edit
        self.on_delete = on_delete
        self.on_status_change = on_status_change
        
        # Setup styling using CONSTANTS
        self.configure(
            fg_color=COLORS["bg_card"],
            corner_radius=DIMENSIONS["card_corner_radius"]
        )
        
        self._create_header()
        self._render_tasks(tasks)
    
    def _create_header(self):
        """Создание заголовка колонки."""
        status_colors_map = {
            TaskStatus.TODO: COLORS["status_todo"],
            TaskStatus.IN_PROGRESS: COLORS["status_in_progress"],
            TaskStatus.DONE: COLORS["status_done"]
        }
        
        header = ctk.CTkFrame(
            self, fg_color=status_colors_map[self.status],
            corner_radius=DIMENSIONS["button_corner_radius"],
            height=45
        )
        header.pack(fill="x", padx=DIMENSIONS["padding_small"], pady=DIMENSIONS["padding_small"])
        
        # Status icon mapping
        status_icons = {
            TaskStatus.TODO: "📝",
            TaskStatus.IN_PROGRESS: "🔄",
            TaskStatus.DONE: "✅"
        }
        
        icon = status_icons.get(self.status, "📌")
        ctk.CTkLabel(
            header, text=f"{icon} {self.status.value}",
            font=("Arial", 14, "bold"), text_color="#000000"
        ).pack(side="left", padx=DIMENSIONS["padding_medium"], pady=DIMENSIONS["padding_small"])
    
    def _render_tasks(self, tasks: list):
        """Отрисовка задач в колонке с адаптивной высотой."""
        # Configure grid to expand properly
        self.grid_columnconfigure(0, weight=1)
        
        for idx, task in enumerate(tasks):
            card = TaskCard(
                self, task, self.on_edit, self.on_delete,
                on_status_change=self.on_status_change,
                fg_color=COLORS["bg_card_light"]
            )
            card.grid(row=idx, column=0, sticky="ew", padx=5, pady=3)
        
        # Add stretchable empty row at bottom to fill available space
        self.grid_rowconfigure(len(tasks), weight=1)
    
    def refresh_tasks(self, tasks: list):
        """Обновить задачи в колонке."""
        # Clear all existing cards
        for widget in self.winfo_children():
            if isinstance(widget, TaskCard):
                widget.destroy()
        
        # Re-render tasks
        self._render_tasks(tasks)


class TaskManagerApp(ctk.CTk):
    """Главное приложение Task Manager."""
    
    def __init__(self):
        super().__init__()
        
        # Window setup
        self.title("📋 Task Manager - Kanban Board")
        self.geometry(f"{DIMENSIONS['window_width']}x{DIMENSIONS['window_height']}")
        self.minsize(1200, 700)
        
        # Setup theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Initialize service
        self.service = TaskService()
        
        self._setup_ui()
        self._refresh_board()
    
    def _setup_ui(self):
        """Настройка интерфейса."""
        # Main container
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=DIMENSIONS["padding_large"], pady=DIMENSIONS["padding_large"])
        
        # Header with improved styling
        header = ctk.CTkFrame(
            main, fg_color=COLORS["bg_card"],
            corner_radius=DIMENSIONS["card_corner_radius"],
            height=DIMENSIONS["header_height"]
        )
        header.pack(fill="x", pady=(0, DIMENSIONS["padding_medium"]))
        header.pack_propagate(False)
        
        # Title with icon
        title = ctk.CTkLabel(
            header, text="📋 Task Manager",
            font=FONTS["heading"], text_color=COLORS["text_primary"]
        )
        title.pack(side="left", padx=DIMENSIONS["padding_large"], pady=DIMENSIONS["padding_medium"])
        
        # Action buttons
        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right", padx=DIMENSIONS["padding_large"], pady=DIMENSIONS["padding_small"])
        
        ctk.CTkButton(
            btn_frame, text="🔄 Обновить", command=self._refresh_board,
            width=110, height=DIMENSIONS["button_height"],
            fg_color=COLORS["bg_button"], hover_color="#555555",
            corner_radius=DIMENSIONS["button_corner_radius"],
            font=FONTS["label"]
        ).pack(side="left", padx=DIMENSIONS["padding_small"])
        
        ctk.CTkButton(
            btn_frame, text="➕ Новая задача", command=self._open_new_task_dialog,
            width=150, height=DIMENSIONS["button_height"],
            corner_radius=DIMENSIONS["button_corner_radius"],
            font=("Arial", 12, "bold")
        ).pack(side="left", padx=DIMENSIONS["padding_small"])
        
        # Tab view: Kanban vs Dashboard vs Gantt
        self.tabview = ctk.CTkTabview(main, fg_color=COLORS["bg_card"], command=self._on_tab_changed)
        self.tabview.pack(fill="both", expand=True)
        
        kanban_tab = self.tabview.add("📊 Kanban Доска")
        dashboard_tab = self.tabview.add("📈 Аналитика")
        gantt_tab = self.tabview.add("📅 Диаграмма Ганта")
        
        # Kanban board
        self.kanban_frame = ctk.CTkFrame(kanban_tab, fg_color="transparent")
        self.kanban_frame.pack(fill="both", expand=True, padx=DIMENSIONS["padding_medium"], pady=DIMENSIONS["padding_medium"])
        
        # Dashboard (lazy load on tab switch)
        self.dashboard_frame = None
        self.gantt_frame = None
    
    def _on_tab_changed(self):
        """Обработка переключения вкладок."""
        selected_tab = self.tabview.get()
        if selected_tab == "📈 Аналитика" and self.dashboard_frame is None:
            self.dashboard_frame = DashboardFrame(
                self.tabview.tab("📈 Аналитика"), self.service,
                fg_color="transparent"
            )
            self.dashboard_frame.pack(fill="both", expand=True)
        elif selected_tab == "📅 Диаграмма Ганта" and self.gantt_frame is None:
            from .gantt_view import GanttViewTab
            self.gantt_frame = GanttViewTab(
                self.tabview.tab("📅 Диаграмма Ганта"), self.service,
                fg_color="transparent"
            )
            self.gantt_frame.pack(fill="both", expand=True)
    
    def _refresh_board(self):
        """Обновление Kanban-доски."""
        # Clear kanban
        for widget in self.kanban_frame.winfo_children():
            widget.destroy()
        
        # Configure columns
        for i in range(3):
            self.kanban_frame.grid_columnconfigure(i, weight=1)
        
        # Create columns
        for i, status in enumerate([TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.DONE]):
            tasks = self.service.get_tasks_by_status(status)
            col = KanbanColumn(
                self.kanban_frame, status, tasks,
                on_edit=self._open_edit_task_dialog,
                on_delete=self._confirm_delete_task,
                on_status_change=self._change_task_status
            )
            col.grid(row=0, column=i, padx=DIMENSIONS["padding_medium"], pady=DIMENSIONS["padding_medium"], sticky="nsew")
        
        # Refresh dashboard if exists
        self._refresh_dashboard()
        
        # Refresh gantt if exists
        self._refresh_gantt()
    
    def _change_task_status(self, task_id: str, new_status: TaskStatus):
        """Изменение статуса задачи с обновлением только затронутых колонок."""
        try:
            # Get the task before changing status to know old column
            old_task = self.service.get_task(task_id)
            old_status = old_task.status if old_task else None
            
            self.service.update_task_status(task_id, new_status)
            logger.info(f"Task {task_id} status changed to {new_status.value}")
            
            # Refresh only affected columns instead of entire board
            self._refresh_affected_columns(old_status, new_status)
            
            # Also refresh dashboard and gantt
            self._refresh_dashboard()
            self._refresh_gantt()
        except Exception as e:
            logger.error(f"Error changing task status: {e}")
            messagebox.showerror("⚠️ Ошибка", str(e))
    
    def _refresh_affected_columns(self, old_status: TaskStatus, new_status: TaskStatus):
        """Обновить только затронутые колонки для оптимизации производительности."""
        # Get all columns
        columns = {}
        for widget in self.kanban_frame.winfo_children():
            if isinstance(widget, KanbanColumn):
                columns[widget.status] = widget
        
        # Determine which columns need refresh (old and new status columns)
        statuses_to_refresh = set()
        if old_status:
            statuses_to_refresh.add(old_status)
        statuses_to_refresh.add(new_status)
        
        # Refresh only affected columns
        for status in statuses_to_refresh:
            if status in columns:
                tasks = self.service.get_tasks_by_status(status)
                columns[status].refresh_tasks(tasks)
    
    def _open_new_task_dialog(self):
        """Открытие диалога создания задачи."""
        dialog = TaskDialog(self, on_save=self._save_new_task)
        dialog.grab_set()
    
    def _open_edit_task_dialog(self, task: Task):
        """Открытие диалога редактирования задачи."""
        dialog = TaskDialog(self, task=task, on_save=self._save_edited_task)
        dialog.grab_set()
    
    def _save_new_task(self, data: dict, task_id: str | None = None):
        """Сохранение новой задачи."""
        try:
            self.service.create_task(
                title=data['title'],
                description=data['description'],
                priority=data['priority'],
                due_date=data['due_date']
            )
            # Если есть start_date, обновить задачу
            if 'start_date' in data and data['start_date']:
                # Получить только что созданную задачу и обновить start_date
                tasks = self.service.get_all_tasks()
                for task in tasks:
                    if task.title == data['title']:
                        self.service.update_task(task.id, start_date=data['start_date'])
                        break
            
            logger.info(f"Task created: {data['title']}")
            self._refresh_board()
        except Exception as e:
            logger.error(f"Error creating task: {e}")
            messagebox.showerror("⚠️ Ошибка", str(e))
    
    def _save_edited_task(self, data: dict, task_id: str):
        """Сохранение изменений задачи."""
        try:
            update_kwargs = {
                'task_id': task_id,
                'title': data['title'],
                'description': data['description'],
                'priority': data['priority'],
                'due_date': data['due_date'],
                'time_spent': data['time_spent']
            }
            
            # Добавить статус если есть
            if 'status' in data and data['status']:
                update_kwargs['status'] = data['status']
            
            # Добавить start_date если есть
            if 'start_date' in data:
                update_kwargs['start_date'] = data['start_date']
            
            self.service.update_task(**update_kwargs)
            logger.info(f"Task updated: {data['title']}")
            self._refresh_board()
        except Exception as e:
            logger.error(f"Error updating task: {e}")
            messagebox.showerror("⚠️ Ошибка", str(e))
    
    def _confirm_delete_task(self, task_id: str):
        """Подтверждение удаления задачи."""
        if messagebox.askyesno("🗑️ Удаление", "Вы уверены, что хотите удалить эту задачу?"):
            self.service.delete_task(task_id)
            logger.info(f"Task deleted: {task_id}")
            self._refresh_board()
    
    def _refresh_dashboard(self):
        """Обновление дашборда (если создан)."""
        if self.dashboard_frame is not None:
            self.dashboard_frame._refresh()
    
    def _refresh_gantt(self):
        """Обновление диаграммы Ганта (если создана)."""
        if self.gantt_frame is not None:
            self.gantt_frame.refresh()


def run_app():
    """Точка входа приложения."""
    logger.info("Starting Task Manager Application")
    app = TaskManagerApp()
    app.mainloop()
    logger.info("Application closed")


if __name__ == "__main__":
    run_app()
