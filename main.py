import os
import json
import subprocess
import tempfile
import platform
import shutil

from ulauncher.api.client.Extension import Extension
from ulauncher.api.shared.event import KeywordQueryEvent, ItemEnterEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.HideWindowAction import HideWindowAction
from ulauncher.api.shared.action.OpenAction import OpenAction
from ulauncher.api.shared.action.ExtensionCustomAction import ExtensionCustomAction
from ulauncher.api.client.EventListener import EventListener


class PathLauncherExtension(Extension):

    def __init__(self):
        super(PathLauncherExtension, self).__init__()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())
        self.subscribe(ItemEnterEvent, ItemEnterEventListener())

        self.data_dir = tempfile.gettempdir()
        self.recent_projects_file = os.path.join(
            self.data_dir, "path_launcher", "recent_projects.json"
        )
        self.recent_projects = self._load_recent_projects()

    def _load_recent_projects(self):
        try:
            with open(self.recent_projects_file, "r") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_recent_projects(self):
        try:
            os.makedirs(os.path.dirname(self.recent_projects_file), exist_ok=True)
            with open(self.recent_projects_file, "w") as f:
                json.dump(self.recent_projects, f)
        except Exception as e:
            print(f"Error saving recent projects: {e}")

    def _add_recent_project(self, path):
        path = os.path.abspath(os.path.expanduser(path))
        if path in self.recent_projects:
            self.recent_projects.remove(path)
        self.recent_projects.insert(0, path)
        self.recent_projects = self.recent_projects[:20]
        self._save_recent_projects()


class KeywordQueryEventListener(EventListener):

    def on_event(self, event, extension):
        items = []
        query = event.get_argument()

        if not query:
            for path in extension.recent_projects:
                if os.path.exists(path):
                    is_dir = os.path.isdir(path)
                    icon = 'images/folder.svg' if is_dir else 'images/file.svg'
                    items.append(ExtensionResultItem(
                        icon=icon,
                        name=os.path.basename(path),
                        description=path,
                        on_enter=ExtensionCustomAction({'path': path}, keep_app_open=False)
                    ))
            return RenderResultListAction(items)

        query = os.path.expanduser(query)
        query = os.path.abspath(query)
        dir_path = os.path.dirname(query)
        partial_name = os.path.basename(query)

        if query.endswith(os.sep) and os.path.isdir(query):
            dir_path = query
            partial_name = ''
        elif not os.path.isdir(dir_path):
            original_arg = event.get_argument()
            if '/' not in original_arg and '\\' not in original_arg:
                dir_path = os.path.expanduser("~")
            else:
                dir_path = os.path.dirname(os.path.expanduser(original_arg))
            partial_name = os.path.basename(os.path.expanduser(original_arg))

        try:
            if os.path.isdir(dir_path):
                with os.scandir(dir_path) as entries:
                    for entry in entries:
                        full_path = os.path.join(dir_path, entry.name)
                        if entry.name.lower().startswith(partial_name.lower()):
                            icon = 'images/folder.svg' if entry.is_dir() else 'images/file.svg'
                            items.append(ExtensionResultItem(
                                icon=icon,
                                name=entry.name,
                                description=full_path,
                                on_enter=ExtensionCustomAction({'path': full_path}, keep_app_open=False)
                            ))

            current_query_full_path = os.path.abspath(os.path.expanduser(event.get_argument()))
            if os.path.exists(current_query_full_path):
                is_dir = os.path.isdir(current_query_full_path)
                icon = 'images/folder.svg' if is_dir else 'images/file.svg'
                already_listed = any(item.description == current_query_full_path for item in items)
                if not already_listed:
                    items.insert(0, ExtensionResultItem(
                        icon=icon,
                        name=os.path.basename(current_query_full_path),
                        description=current_query_full_path,
                        on_enter=ExtensionCustomAction({'path': current_query_full_path}, keep_app_open=False)
                    ))

            items.sort(key=lambda x: (not os.path.isdir(x.description), x.name.lower()))
        except Exception as e:
            print(f"Error processing query: {e}")

        return RenderResultListAction(items)

def get_executable(path):
    editor_path = path
    if editor_path and not editor_path.startswith("!"):
        editor_path = os.path.expanduser(editor_path)
        if not os.path.isabs(editor_path):
            resolved_path = shutil.which(editor_path)
            if resolved_path:
                editor_path = resolved_path
    return editor_path

class ItemEnterEventListener(EventListener):

    def on_event(self, event, extension):
        data = event.get_data()
        selected_path = data['path']
        extension._add_recent_project(selected_path)

        editor_path = extension.preferences.get('editor_path', '').strip()

        # Expand ~ and resolve executable in PATH
        if editor_path and not editor_path.startswith("!"):
            editor_path = os.path.expanduser(editor_path)
            if not os.path.isabs(editor_path):
                resolved_path = shutil.which(editor_path)
                if resolved_path:
                    editor_path = resolved_path

        try:
            if editor_path.startswith("!"):
                path = editor_path[1:]
                command = get_executable(path.split(" ")[0])
                args = path.replace("%s", selected_path)[1:]
                args = path.split(" ")
                argsCommand = (command, *args,)
                subprocess.call(argsCommand, shell=True)
            elif editor_path and os.path.isfile(editor_path):
                subprocess.Popen([editor_path, selected_path])
            else:
                if platform.system() == "Darwin":
                    subprocess.call(('open', selected_path))
                elif platform.system() == "Windows":
                    os.startfile(selected_path)
                else:
                    subprocess.call(('xdg-open', selected_path))
        except Exception as e:
            print(f"Error opening {selected_path}: {e}")

        return HideWindowAction()


if __name__ == '__main__':
    PathLauncherExtension().run()
