"""
Task Manager - Modern Kanban Board
GUI Components: Main Window, Kanban Board, Dashboard with Charts
"""
import customtkinter as ctk
from tkinter import messagebox
from typing import Callable, Optional
from datetime import datetime

from ..core import Task, TaskStatus, Priority, TaskService


class TaskDialog(ctk.CTKToplevel):
    """Диалог создания/редактирования задачи."""
    
    def __init__(self, parent, task: Optional[Task] = None, on_save: Callable = None):
        super().__init__(parent)
        
        self.task = task
        self.on_save = on_save
        self.title("Редактирование задачи" if task else "Новая задача")
        self.geometry("500x450")
        self.resizable(False, False)
        
        # Center window
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 500) // 2
        y = (self.winfo_screenheight() - 450) // 2
        self.geometry(f"+{x}+{y}")
        
        self._create_widgets()
        
        if task:
            self._fill_data(task)
    
    def _create_widgets(self):
        """Создание виджетов диалога."""
        padding = 20
        
        # Title
        ctk.CTkLabel(self, text="Заголовок *", font=("Arial", 12, "bold")).pack(
            anchor="w", padx=padding, pady=(padding, 5))
        self.title_entry = ctk.CTkEntry(self, width=460, height=35)
        self.title_entry.pack(padx=padding, pady=(0, 15))
        
        # Description
        ctk.CTkLabel(self, text="Описание", font=("Arial", 12, "bold")).pack(
            anchor="w", padx=padding, pady=(0, 5))
        self.desc_text = ctk.CTkTextbox(self, width=460, height=100)
        self.desc_text.pack(padx=padding, pady=(0, 15))
        
        # Priority
        ctk.CTkLabel(self, text="Приоритет", font=("Arial", 12, "bold")).pack(
            anchor="w", padx=padding, pady=(0, 5))
        self.priority_var = ctk.StringVar(value="Medium")
        priority_frame = ctk.CTkFrame(self)
        priority_frame.pack(anchor="w", padx=padding, pady=(0, 15), fill="x")
        
        for i, prio in enumerate(["Low", "Medium", "High"]):
            radio = ctk.CTkRadioButton(
                priority_frame, text=prio, variable=self.priority_var, value=prio,
                command=lambda p=prio: self._update_priority_color(p)
            )
            radio.grid(row=0, column=i, padx=20, sticky="w")
        self._update_priority_color(self.priority_var.get())
        
        # Due Date
        ctk.CTkLabel(self, text="Дедлайн (YYYY-MM-DD)", font=("Arial", 12, "bold")).pack(
            anchor="w", padx=padding, pady=(0, 5))
        self.due_entry = ctk.CTkEntry(self, width=200, height=35, placeholder_text="2025-12-31")
        self.due_entry.pack(anchor="w", padx=padding, pady=(0, 15))
        
        # Time Spent (hours)
        ctk.CTkLabel(self, text="Затрачено времени (часы)", font=("Arial", 12, "bold")).pack(
            anchor="w", padx=padding, pady=(0, 5))
        self.time_entry = ctk.CTkEntry(self, width=200, height=35, placeholder_text="0.0")
        self.time_entry.pack(anchor="w", padx=padding, pady=(0, 15))
        
        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=padding, pady=padding)
        
        ctk.CTkButton(btn_frame, text="Отмена", command=self.destroy, 
                      width=120, fg_color="#666666").pack(side="left")
        ctk.CTkButton(btn_frame, text="Сохранить", command=self._save, 
                      width=120).pack(side="right")
    
    def _update_priority_color(self, priority: str):
        """Обновление цвета в зависимости от приоритета."""
        colors = {"Low": "#4CAF50", "Medium": "#FF9800", "High": "#F44336"}
        self.configure(fg_color=colors.get(priority, "#2b2b2b"))
    
    def _fill_data(self, task: Task):
        """Заполнение данными существующей задачи."""
        self.title_entry.insert(0, task.title)
        self.desc_text.insert("0.0", task.description)
        self.priority_var.set(task.priority.value)
        if task.due_date:
            self.due_entry.insert(0, task.due_date)
        if task.time_spent:
            self.time_entry.insert(0, str(task.time_spent))
        self._update_priority_color(task.priority.value)
    
    def _save(self):
        """Сохранение задачи."""
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showerror("Ошибка", "Заголовок обязателен!", parent=self)
            return
        
        try:
            time_spent = float(self.time_entry.get()) if self.time_entry.get() else 0.0
        except ValueError:
            messagebox.showerror("Ошибка", "Некорректное время!", parent=self)
            return
        
        priority_map = {"Low": Priority.LOW, "Medium": Priority.MEDIUM, "High": Priority.HIGH}
        
        task_data = {
            'title': title,
            'description': self.desc_text.get("0.0", "end-1c").strip(),
            'priority': priority_map[self.priority_var.get()],
            'due_date': self.due_entry.get().strip() or None,
            'time_spent': time_spent
        }
        
        if self.on_save:
            self.on_save(task_data, self.task.id if self.task else None)
        self.destroy()


class TaskCard(ctk.CTkFrame):
    """Карточка задачи для Kanban-доски."""
    
    def __init__(self, parent, task: Task, on_edit: Callable, on_delete: Callable, **kwargs):
        super().__init__(parent, **kwargs)
        self.task = task
        self.on_edit = on_edit
        self.on_delete = on_delete
        
        self._render()
    
    def _render(self):
        """Отрисовка карточки."""
        self.configure(fg_color="#3a3a3a", corner_radius=8)
        self.pack(fill="x", padx=10, pady=8)
        
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(12, 8))
        
        # Priority indicator
        prio_color = self.task.priority.color
        prio_dot = ctk.CTkLabel(header, text="●", text_color=prio_color, 
                                font=("Arial", 16, "bold"))
        prio_dot.pack(side="left")
        
        # Title
        title_label = ctk.CTkLabel(header, text=self.task.title[:40], 
                                   font=("Arial", 13, "bold"), anchor="w")
        title_label.pack(side="left", padx=8, fill="x", expand=True)
        
        # Actions
        edit_btn = ctk.CTkButton(header, text="✎", width=30, height=25, 
                                 fg_color="#444444", command=lambda: self.on_edit(self.task))
        edit_btn.pack(side="right", padx=2)
        
        del_btn = ctk.CTkButton(header, text="🗑", width=30, height=25, 
                                fg_color="#d32f2f", command=lambda: self.on_delete(self.task.id))
        del_btn.pack(side="right", padx=2)
        
        # Description preview
        if self.task.description:
            desc_label = ctk.CTkLabel(self, text=self.task.description[:60] + "...", 
                                      text_color="#aaaaaa", font=("Arial", 11), 
                                      justify="left", wraplength=250)
            desc_label.pack(anchor="w", padx=12, pady=(0, 8))
        
        # Meta info
        meta = ctk.CTkFrame(self, fg_color="transparent")
        meta.pack(fill="x", padx=12, pady=(0, 12))
        
        # Due date badge
        if self.task.due_date:
            days = self.task.days_until_due()
            if days is not None:
                color = "#F44336" if days < 0 else "#FF9800" if days <= 3 else "#4CAF50"
                badge_text = f"📅 {self.task.due_date}"
                if days < 0:
                    badge_text += f" (-{abs(days)} дн.)"
                elif days == 0:
                    badge_text += " (сегодня!)"
                else:
                    badge_text += f" ({days} дн.)"
                
                due_label = ctk.CTkLabel(meta, text=badge_text, text_color=color, 
                                         font=("Arial", 10, "bold"))
                due_label.pack(side="left")
        
        # Time spent
        if self.task.time_spent > 0:
            time_label = ctk.CTkLabel(meta, text=f"⏱ {self.task.time_spent}ч", 
                                      text_color="#888888", font=("Arial", 10))
            time_label.pack(side="right")
        
        # ID badge
        id_label = ctk.CTkLabel(meta, text=f"#{self.task.id}", text_color="#555555", 
                                font=("Arial", 9))
        id_label.pack(side="right", padx=10)


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
        wedges, texts = ax.pie(values, labels=labels, colors=colors, autopct='%1.0f%%',
                               textprops={'color': 'white', 'fontsize': 10})
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
    """Колонка Kanban-доски."""
    
    def __init__(self, parent, status: TaskStatus, tasks: list, 
                 on_edit: Callable, on_delete: Callable, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.status = status
        self.configure(fg_color="#2d2d2d", corner_radius=8)
        
        # Header
        status_colors = {
            TaskStatus.TODO: "#9E9E9E",
            TaskStatus.IN_PROGRESS: "#FF9800",
            TaskStatus.DONE: "#4CAF50"
        }
        
        header = ctk.CTkFrame(self, fg_color=status_colors[status], corner_radius=5, height=40)
        header.pack(fill="x", padx=5, pady=5)
        
        count = len(tasks)
        ctk.CTkLabel(header, text=f"{status.value} ({count})", 
                     font=("Arial", 14, "bold"), text_color="black").pack(
                         side="left", padx=10, pady=5)
        
        # Tasks
        for task in tasks:
            TaskCard(self, task, on_edit, on_delete, fg_color="#2d2d2d")


class TaskManagerApp(ctk.CTk):
    """Главное приложение Task Manager."""
    
    def __init__(self):
        super().__init__()
        
        self.title("Task Manager - Kanban Board")
        self.geometry("1400x800")
        
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
        main.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Header
        header = ctk.CTkFrame(main, fg_color="#2d2d2d", corner_radius=10, height=60)
        header.pack(fill="x", pady=(0, 10))
        header.pack_propagate(False)
        
        title = ctk.CTkLabel(header, text="📋 Task Manager", font=("Arial", 20, "bold"))
        title.pack(side="left", padx=20, pady=15)
        
        # Action buttons
        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right", padx=20, pady=10)
        
        ctk.CTkButton(btn_frame, text="🔄 Обновить", command=self._refresh_board,
                      width=100, fg_color="#444444").pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="➕ Новая задача", command=self._open_new_task_dialog,
                      width=140).pack(side="left", padx=5)
        
        # Tab view: Kanban vs Dashboard
        self.tabview = ctk.CTkTabview(main, fg_color="#2d2d2d")
        self.tabview.pack(fill="both", expand=True)
        
        kanban_tab = self.tabview.add("Kanban Доска")
        dashboard_tab = self.tabview.add("Дашборд")
        
        # Kanban board
        self.kanban_frame = ctk.CTkFrame(kanban_tab, fg_color="transparent")
        self.kanban_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Dashboard
        self.dashboard_frame = DashboardFrame(dashboard_tab, self.service, 
                                              fg_color="transparent")
        self.dashboard_frame.pack(fill="both", expand=True)
    
    def _refresh_board(self):
        """Обновление Kanban-доски."""
        # Clear kanban
        for widget in self.kanban_frame.winfo_children():
            widget.destroy()
        
        # Configure columns
        self.kanban_frame.grid_columnconfigure(0, weight=1)
        self.kanban_frame.grid_columnconfigure(1, weight=1)
        self.kanban_frame.grid_columnconfigure(2, weight=1)
        
        # Create columns
        for i, status in enumerate([TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.DONE]):
            tasks = self.service.get_tasks_by_status(status)
            col = KanbanColumn(
                self.kanban_frame, status, tasks,
                on_edit=self._open_edit_task_dialog,
                on_delete=self._confirm_delete_task
            )
            col.grid(row=0, column=i, padx=10, pady=10, sticky="nsew")
    
    def _open_new_task_dialog(self):
        """Открытие диалога создания задачи."""
        dialog = TaskDialog(self, on_save=self._save_new_task)
        dialog.grab_set()
    
    def _open_edit_task_dialog(self, task: Task):
        """Открытие диалога редактирования задачи."""
        dialog = TaskDialog(self, task=task, on_save=self._save_edited_task)
        dialog.grab_set()
    
    def _save_new_task(self, data: dict, task_id: Optional[str] = None):
        """Сохранение новой задачи."""
        try:
            self.service.create_task(
                title=data['title'],
                description=data['description'],
                priority=data['priority'],
                due_date=data['due_date']
            )
            self._refresh_board()
            self._refresh_dashboard()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
    
    def _save_edited_task(self, data: dict, task_id: str):
        """Сохранение изменений задачи."""
        try:
            self.service.update_task(
                task_id=task_id,
                title=data['title'],
                description=data['description'],
                priority=data['priority'],
                due_date=data['due_date'],
                time_spent=data['time_spent']
            )
            self._refresh_board()
            self._refresh_dashboard()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
    
    def _confirm_delete_task(self, task_id: str):
        """Подтверждение удаления задачи."""
        if messagebox.askyesno("Удаление", "Удалить эту задачу?"):
            self.service.delete_task(task_id)
            self._refresh_board()
            self._refresh_dashboard()
    
    def _refresh_dashboard(self):
        """Обновление дашборда."""
        if hasattr(self, 'dashboard_frame'):
            self.dashboard_frame._refresh()


def run_app():
    """Точка входа приложения."""
    app = TaskManagerApp()
    app.mainloop()


if __name__ == "__main__":
    run_app()
