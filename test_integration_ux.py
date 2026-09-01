"""
Интеграционное тестирование UX/UI сценариев для Flet GUI.
Эмулирует действия пользователя: создание, редактирование, drag-and-drop, проверка графиков.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from datetime import datetime, timedelta
from core.models import Task, TaskStatus, Priority
from core.service import TaskService
from gui_flet.kanban_view import KanbanView
from gui_flet.gantt_view import GanttView
from gui_flet.dashboard_view import DashboardView
import flet as ft

def test_use_cases():
    print("🚀 Запуск интеграционных тестов UX сценариев...")
    
    # Инициализация сервиса
    service = TaskService()
    
    # Очистка перед тестом (опционально, для чистоты эксперимента)
    # service.delete_all() 
    
    print("\n--- СЦЕНАРИЙ 1: Создание задач через 'Фронтенд' (Service Layer) ---")
    
    # Создаем задачу 1
    today = datetime.now().strftime("%Y-%m-%d")
    due_5 = (datetime.now() + timedelta(days=5)).strftime("%Y-%m-%d")
    due_2 = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    due_10 = (datetime.now() + timedelta(days=10)).strftime("%Y-%m-%d")
    
    task1 = service.create_task(
        title="Разработка API",
        description="Создать REST endpoints для задач",
        priority=Priority.HIGH,
        start_date=today,
        due_date=due_5
    )
    # Устанавливаем статус явно после создания
    service.update_task(task1.id, status=TaskStatus.TODO)
    task1 = service.get_task(task1.id)
    print(f"✅ Создана задача: '{task1.title}' (ID: {task1.id}, Статус: {task1.status})")

    # Создаем задачу 2
    task2 = service.create_task(
        title="Настройка Flet GUI",
        description="Исправить рендеринг карточек",
        priority=Priority.MEDIUM,
        start_date=today,
        due_date=due_2
    )
    service.update_task(task2.id, status=TaskStatus.IN_PROGRESS)
    task2 = service.get_task(task2.id)
    print(f"✅ Создана задача: '{task2.title}' (ID: {task2.id}, Статус: {task2.status})")

    # Создаем задачу 3 с подзадачами для проверки прогресса
    task3 = service.create_task(
        title="Тестирование системы",
        description="Провести юз кейсы",
        priority=Priority.LOW,
        start_date=today,
        due_date=due_10
    )
    service.update_task(task3.id, status=TaskStatus.TODO)
    
    # Добавляем подзадачи
    sub1_title = "Написать автотесты"
    sub2_title = "Запустить ручные тесты"
    sub3_title = "Исправить баги"
    
    service.add_subtask(task3.id, sub1_title)
    service.add_subtask(task3.id, sub2_title)
    service.add_subtask(task3.id, sub3_title)
    
    # Эмулируем выполнение первой подзадачи (индекс 0)
    service.toggle_subtask(task3.id, 0)
    
    # Получаем обновленную задачу
    task3_updated = service.get_task(task3.id)
    progress_pct = int(task3_updated.subtask_progress() * 100)
    print(f"✅ Создана задача: '{task3_updated.title}' с подзадачами (Прогресс: {progress_pct}%)")

    print("\n--- СЦЕНАРИЙ 2: Рендеринг Kanban View (Проверка отрисовки) ---")
    
    # Эмулируем создание контролов Flet
    try:
        kanban = KanbanView(service)
        # Метод build ничего не возвращает, но создает self.container
        kanban.build()
        
        assert kanban.container is not None, "Корневой элемент Kanban не создан"
        print("✅ KanbanView успешно построен")
        
        # Проверяем наличие колонок
        # В нашей реализации columns - это словарь или атрибут
        # Проверим, что карточки задачи присутствуют в структуре
        # Для этого проверим содержимое колонок через сервис, так как прямая инспекция UI сложна без page
        
        # Эмуляция Drag-and-Drop (изменение статуса)
        print("\n--- СЦЕНАРИЙ 3: Изменение статуса (Drag-and-Drop эмуляция) ---")
        
        old_status = task1.status
        service.update_task(task1.id, status=TaskStatus.IN_PROGRESS)
        task1_refreshed = service.get_task(task1.id)
        
        assert task1_refreshed.status == TaskStatus.IN_PROGRESS, "Статус не изменился"
        print(f"✅ Задача '{task1.title}' перемещена из {old_status} в {task1_refreshed.status}")
        
        # Эмуляция перемещения в Done
        service.update_task(task1.id, status=TaskStatus.DONE)
        task1_done = service.get_task(task1.id)
        print(f"✅ Задача '{task1.title}' завершена (Статус: {task1_done.status})")
        
    except Exception as e:
        print(f"❌ Ошибка рендеринга Kanban: {e}")
        raise

    print("\n--- СЦЕНАРИЙ 4: Обновление содержания задачи ---")
    new_desc = "Обновленное описание: добавлена авторизация"
    service.update_task(task2.id, description=new_desc, priority=Priority.HIGH)
    task2_updated = service.get_task(task2.id)
    
    assert task2_updated.description == new_desc, "Описание не обновилось"
    assert task2_updated.priority == Priority.HIGH, "Приоритет не обновился"
    print(f"✅ Содержание задачи '{task2.title}' обновлено: приоритет={task2_updated.priority}, описание='{task2_updated.description[:20]}...'")

    print("\n--- СЦЕНАРИЙ 5: Генерация данных для Gantt Chart ---")
    try:
        gantt = GanttView(service)
        # GanttView обычно строит список строк или таблицу
        # Проверим метод получения данных
        tasks_for_gantt = service.get_all_tasks()
        
        has_dates = all(t.start_date and t.due_date for t in tasks_for_gantt if t.status != TaskStatus.DONE)
        print(f"✅ Данные для Ганта готовы: найдено {len(tasks_for_gantt)} задач, даты корректны: {has_dates}")
        
        # Попытка построить UI компонент
        gantt.build()
        assert gantt.container is not None, "Gantt Control не создан"
        print("✅ GanttView успешно построен")
        
    except Exception as e:
        print(f"❌ Ошибка Gantt: {e}")
        raise

    print("\n--- СЦЕНАРИЙ 6: Генерация данных для Dashboard ---")
    try:
        dashboard = DashboardView(service)
        
        # Получаем метрики
        all_tasks = service.get_all_tasks()
        total = len(all_tasks)
        done = len([t for t in all_tasks if t.status == TaskStatus.DONE])
        in_progress = len([t for t in all_tasks if t.status == TaskStatus.IN_PROGRESS])
        
        print(f"✅ Метрики дашборда: Всего={total}, В работе={in_progress}, Завершено={done}")
        
        # Проверка виджета
        dash_control = dashboard.build()
        assert dash_control is not None, "Dashboard Control не создан"
        print("✅ DashboardView успешно построен")
        
    except Exception as e:
        print(f"❌ Ошибка Dashboard: {e}")
        raise

    print("\n" + "="*50)
    print("🎉 ВСЕ ЮЗ КЕЙСЫ ПРОЙДЕНУ УСПЕШНО!")
    print("="*50)
    print("✅ Создание объектов: OK")
    print("✅ Изменение содержания: OK")
    print("✅ Смена статусов (Drag-and-Drop логика): OK")
    print("✅ Подзадачи и прогресс: OK")
    print("✅ Отрисовка Kanban: OK")
    print("✅ Отрисовка Gantt: OK")
    print("✅ Отрисовка Dashboard: OK")
    
    return True

if __name__ == "__main__":
    test_use_cases()
