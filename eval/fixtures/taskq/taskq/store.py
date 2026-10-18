from taskq.models import Task


class TaskNotFound(KeyError):
    pass


class TaskStore:
    def __init__(self):
        self._tasks: dict[int, Task] = {}
        self._next_id = 1

    def add(self, title, priority="normal", due=None, tags=None):
        task = Task(self._next_id, title, priority, due=due, tags=list(tags or []))
        self._tasks[task.id] = task
        self._next_id += 1
        return task

    def get(self, task_id):
        try:
            return self._tasks[task_id]
        except KeyError:
            raise TaskNotFound(task_id) from None

    def complete(self, task_id):
        task = self.get(task_id)
        task.done = True
        return task

    def delete(self, task_id):
        self.get(task_id)
        del self._tasks[task_id]

    def list(self, include_done=True):
        tasks = sorted(self._tasks.values(), key=lambda t: t.id)
        if not include_done:
            tasks = [t for t in tasks if not t.done]
        return tasks
