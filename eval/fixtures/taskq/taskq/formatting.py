def format_task(task):
    box = "[x]" if task.done else "[ ]"
    line = f"{box} #{task.id} {task.title}"
    if task.priority == "high":
        line += " (!)"
    if task.due:
        line += f" due {task.due.isoformat()}"
    return line


def format_list(tasks):
    if not tasks:
        return "No tasks."
    return "\n".join(format_task(t) for t in tasks)
