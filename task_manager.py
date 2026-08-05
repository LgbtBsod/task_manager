"""
Task Manager - Simple Kanban-style task management application.
Local storage, single-user, no network dependencies.

Features:
- Create, edit, delete tasks
- Track status (Todo, In Progress, Done)
- Set due dates and priorities
- Visual Kanban board layout
- Persistent JSON storage
"""

import json
import os
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional
from enum import Enum
import customtkinter as ctk
from tkinter import messagebox

# =============================================================================
# DATA MODELS
# =============================================================================


class TaskStatus(Enum):
    TODO = "Todo"
    IN_PROGRESS = "In Progress"
    DONE = "Done"


class Priority(Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


@dataclass
class Task:
    id: int
    title: str
    description: str
    status: str
    priority: str
    due_date: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        return cls(**data)


# =============================================================================
# STORAGE SERVICE
# =============================================================================


class StorageService:
    """Handles persistence of tasks to JSON file."""

    def __init__(self, filepath: str = "tasks.json"):
        self.filepath = filepath
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not os.path.exists(self.filepath):
            self._save_tasks([])

    def load_tasks(self) -> List[Task]:
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                return [Task.from_dict(task) for task in data]
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def save_tasks(self, tasks: List[Task]):
        self._save_tasks([task.to_dict() for task in tasks])

    def _save_tasks(self, tasks_data: List[dict]):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(tasks_data, f, indent=2, ensure_ascii=False)


# =============================================================================
# TASK SERVICE
# =============================================================================


class TaskService:
    """Business logic for task management."""

    def __init__(self, storage: StorageService):
        self.storage = storage
        self._next_id = self._get_next_id()

    def _get_next_id(self) -> int:
        tasks = self.storage.load_tasks()
        if not tasks:
            return 1
        return max(task.id for task in tasks) + 1

    def get_all_tasks(self) -> List[Task]:
        return self.storage.load_tasks()

    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        tasks = self.get_all_tasks()
        return [t for t in tasks if t.status == status.value]

    def create_task(
        self, title: str, description: str, priority: str, due_date: str
    ) -> Task:
        now = datetime.now().isoformat()
        task = Task(
            id=self._next_id,
            title=title,
            description=description,
            status=TaskStatus.TODO.value,
            priority=priority,
            due_date=due_date,
            created_at=now,
            updated_at=now,
        )
        self._next_id += 1
        self._save_all([task])
        return task

    def update_task(self, task: Task, **kwargs) -> Task:
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        task.updated_at = datetime.now().isoformat()
        self._save_all([task])
        return task

    def delete_task(self, task_id: int):
        tasks = self.get_all_tasks()
        tasks = [t for t in tasks if t.id != task_id]
        self.storage.save_tasks(tasks)

    def _save_all(self, new_or_updated: List[Task]):
        all_tasks = self.get_all_tasks()

        # Remove old versions of updated tasks
        all_tasks = [
            t for t in all_tasks if t.id not in {nt.id for nt in new_or_updated}
        ]
        all_tasks.extend(new_or_updated)
        self.storage.save_tasks(all_tasks)


# =============================================================================
# GUI COMPONENTS
# =============================================================================


class TaskCard(ctk.CTkFrame):
    """Visual card representing a single task."""

    def __init__(self, parent, task: Task, on_edit, on_delete, on_move):
        super().__init__(parent, corner_radius=8, fg_color="gray20")

        self.task = task
        self.on_edit = on_edit
        self.on_delete = on_delete
        self.on_move = on_move

        self._setup_ui()

    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)

        # Title
        title_label = ctk.CTkLabel(
            self,
            text=self.task.title,
            font=ctk.CTkFont(size=14, weight="bold"),
            anchor="w",
        )
        title_label.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")

        # Description
        desc_label = ctk.CTkLabel(
            self,
            text=self.task.description[:50]
            + ("..." if len(self.task.description) > 50 else ""),
            font=ctk.CTkFont(size=11),
            anchor="w",
            justify="left",
        )
        desc_label.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        # Meta info
        meta_frame = ctk.CTkFrame(self, fg_color="transparent")
        meta_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        meta_frame.grid_columnconfigure(0, weight=1)

        priority_colors = {"Low": "green", "Medium": "orange", "High": "red"}
        priority_label = ctk.CTkLabel(
            meta_frame,
            text=f"Priority: {self.task.priority}",
            font=ctk.CTkFont(size=10),
            text_color=priority_colors.get(self.task.priority, "white"),
        )
        priority_label.grid(row=0, column=0, sticky="w")

        if self.task.due_date:
            date_label = ctk.CTkLabel(
                meta_frame, text=f"Due: {self.task.due_date}", font=ctk.CTkFont(size=10)
            )
            date_label.grid(row=0, column=1, padx=10, sticky="e")

        # Actions
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, padx=10, pady=(5, 10), sticky="ew")

        move_btn = ctk.CTkButton(
            btn_frame,
            text="→ Move",
            width=60,
            height=20,
            font=ctk.CTkFont(size=10),
            command=self._on_move,
        )
        move_btn.pack(side="left", padx=(0, 5))

        edit_btn = ctk.CTkButton(
            btn_frame,
            text="Edit",
            width=50,
            height=20,
            font=ctk.CTkFont(size=10),
            command=self._on_edit,
        )
        edit_btn.pack(side="left", padx=(0, 5))

        delete_btn = ctk.CTkButton(
            btn_frame,
            text="Delete",
            width=50,
            height=20,
            font=ctk.CTkFont(size=10),
            fg_color="red",
            hover_color="darkred",
            command=self._on_delete,
        )
        delete_btn.pack(side="left")

    def _on_edit(self):
        self.on_edit(self.task)

    def _on_delete(self):
        if messagebox.askyesno("Confirm", f"Delete task '{self.task.title}'?"):
            self.on_delete(self.task.id)

    def _on_move(self):
        self.on_move(self.task)


class TaskDialog(ctk.CTkToplevel):
    """Dialog for creating/editing tasks."""

    def __init__(self, parent, task_service: TaskService, task: Optional[Task] = None):
        super().__init__(parent)
        self.task_service = task_service
        self.task = task
        self.result = None

        self.title("Edit Task" if task else "New Task")
        self.geometry("400x500")
        self.resizable(False, False)
        self.grab_set()

        self._setup_ui()
        if task:
            self._populate_fields()

    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)

        # Title
        ctk.CTkLabel(self, text="Title:", anchor="w").grid(
            row=0, column=0, padx=20, pady=(20, 5), sticky="ew"
        )
        self.title_entry = ctk.CTkEntry(self)
        self.title_entry.grid(row=1, column=0, padx=20, pady=5, sticky="ew")

        # Description
        ctk.CTkLabel(self, text="Description:", anchor="w").grid(
            row=2, column=0, padx=20, pady=(10, 5), sticky="ew"
        )
        self.desc_text = ctk.CTkTextbox(self, height=100)
        self.desc_text.grid(row=3, column=0, padx=20, pady=5, sticky="ew")

        # Priority
        ctk.CTkLabel(self, text="Priority:", anchor="w").grid(
            row=4, column=0, padx=20, pady=(10, 5), sticky="ew"
        )
        self.priority_var = ctk.StringVar(value="Medium")
        priority_combo = ctk.CTkOptionMenu(
            self, variable=self.priority_var, values=["Low", "Medium", "High"]
        )
        priority_combo.grid(row=5, column=0, padx=20, pady=5, sticky="ew")

        # Due Date
        ctk.CTkLabel(self, text="Due Date (YYYY-MM-DD):", anchor="w").grid(
            row=6, column=0, padx=20, pady=(10, 5), sticky="ew"
        )
        self.date_entry = ctk.CTkEntry(self)
        self.date_entry.grid(row=7, column=0, padx=20, pady=5, sticky="ew")

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=8, column=0, padx=20, pady=20, sticky="ew")

        cancel_btn = ctk.CTkButton(btn_frame, text="Cancel", command=self.destroy)
        cancel_btn.pack(side="left", padx=(0, 10))

        save_btn = ctk.CTkButton(btn_frame, text="Save", command=self._save)
        save_btn.pack(side="right")

    def _populate_fields(self):
        self.title_entry.insert(0, self.task.title)
        self.desc_text.insert("0.0", self.task.description)
        self.priority_var.set(self.task.priority)
        self.date_entry.insert(0, self.task.due_date)

    def _save(self):
        title = self.title_entry.get().strip()
        if not title:
            messagebox.showerror("Error", "Title is required")
            return

        self.result = {
            "title": title,
            "description": self.desc_text.get("0.0", "end-1c").strip(),
            "priority": self.priority_var.get(),
            "due_date": self.date_entry.get().strip(),
        }
        self.destroy()


class KanbanColumn(ctk.CTkScrollableFrame):
    """A column in the Kanban board for a specific status."""

    def __init__(
        self,
        parent,
        status: TaskStatus,
        task_service: TaskService,
        on_edit,
        on_delete,
        on_move,
    ):
        super().__init__(parent, corner_radius=8, fg_color="gray25")

        self.status = status
        self.task_service = task_service
        self.on_edit = on_edit
        self.on_delete = on_delete
        self.on_move = on_move

        self._setup_ui()
        self.refresh()

    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkLabel(
            self, text=self.status.value, font=ctk.CTkFont(size=16, weight="bold")
        )
        header.grid(row=0, column=0, pady=10, sticky="ew")

        self.cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.cards_frame.grid(row=1, column=0, sticky="ew", padx=5, pady=5)
        self.cards_frame.grid_columnconfigure(0, weight=1)

    def refresh(self):
        # Clear existing cards
        for widget in self.cards_frame.winfo_children():
            widget.destroy()

        tasks = self.task_service.get_tasks_by_status(self.status)
        for idx, task in enumerate(tasks):
            card = TaskCard(
                self.cards_frame,
                task,
                on_edit=self.on_edit,
                on_delete=self.on_delete,
                on_move=self.on_move,
            )
            card.grid(row=idx, column=0, sticky="ew", pady=5, padx=5)


class TaskManagerApp(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        self.title("Task Manager - Kanban Board")
        self.geometry("1200x700")
        self.minsize(900, 600)

        # Initialize services
        self.storage = StorageService()
        self.task_service = TaskService(self.storage)

        self._setup_ui()
        self._refresh_board()

    def _setup_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        header = ctk.CTkFrame(self, fg_color="gray20")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        header.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            header, text="📋 Task Manager", font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.grid(row=0, column=0, padx=20, pady=10, sticky="w")

        new_task_btn = ctk.CTkButton(
            header,
            text="+ New Task",
            height=35,
            font=ctk.CTkFont(size=14),
            command=self._create_task,
        )
        new_task_btn.grid(row=0, column=1, padx=20, pady=10)

        # Kanban Board
        board_frame = ctk.CTkFrame(self, fg_color="transparent")
        board_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        board_frame.grid_columnconfigure((0, 1, 2), weight=1)
        board_frame.grid_rowconfigure(0, weight=1)

        self.todo_column = KanbanColumn(
            board_frame,
            TaskStatus.TODO,
            self.task_service,
            on_edit=self._edit_task,
            on_delete=self._delete_task,
            on_move=self._move_task,
        )
        self.todo_column.grid(row=0, column=0, sticky="nsew", padx=5)

        self.in_progress_column = KanbanColumn(
            board_frame,
            TaskStatus.IN_PROGRESS,
            self.task_service,
            on_edit=self._edit_task,
            on_delete=self._delete_task,
            on_move=self._move_task,
        )
        self.in_progress_column.grid(row=0, column=1, sticky="nsew", padx=5)

        self.done_column = KanbanColumn(
            board_frame,
            TaskStatus.DONE,
            self.task_service,
            on_edit=self._edit_task,
            on_delete=self._delete_task,
            on_move=self._move_task,
        )
        self.done_column.grid(row=0, column=2, sticky="nsew", padx=5)

    def _refresh_board(self):
        self.todo_column.refresh()
        self.in_progress_column.refresh()
        self.done_column.refresh()

    def _create_task(self):
        dialog = TaskDialog(self, self.task_service)
        self.wait_window(dialog)

        if dialog.result:
            r = dialog.result
            self.task_service.create_task(
                title=r["title"],
                description=r["description"],
                priority=r["priority"],
                due_date=r["due_date"],
            )
            self._refresh_board()

    def _edit_task(self, task: Task):
        dialog = TaskDialog(self, self.task_service, task)
        self.wait_window(dialog)

        if dialog.result:
            r = dialog.result
            self.task_service.update_task(
                task,
                title=r["title"],
                description=r["description"],
                priority=r["priority"],
                due_date=r["due_date"],
            )
            self._refresh_board()

    def _delete_task(self, task_id: int):
        self.task_service.delete_task(task_id)
        self._refresh_board()

    def _move_task(self, task: Task):
        status_order = [
            TaskStatus.TODO.value,
            TaskStatus.IN_PROGRESS.value,
            TaskStatus.DONE.value,
        ]
        current_idx = status_order.index(task.status)
        next_idx = (current_idx + 1) % len(status_order)
        new_status = status_order[next_idx]

        self.task_service.update_task(task, status=new_status)
        self._refresh_board()


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = TaskManagerApp()
    app.mainloop()
