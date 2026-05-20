"""Scenarios bridge for QML."""

from __future__ import annotations

import copy
import json
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

from app.services.scenario_engine import run_scenario
from app.storage.db import (
    Scenario,
    db_delete_scenario,
    db_get_accounts,
    db_get_scenario,
    db_get_scenario_path,
    db_get_scenarios,
    db_save_scenario,
)
from app.ui.bridge.models import DictListModel

LOGGER = logging.getLogger(__name__)

ACTION_OPTIONS: List[Tuple[str, str]] = [
    ("Start scenario", "start"),
    ("Open URL", "goto"),
    ("HTTP request", "http_request"),
    ("Wait for element", "wait_element"),
    ("Wait for page load", "wait_for_load_state"),
    ("Sleep", "sleep"),
    ("Click element", "click"),
    ("Type text", "type"),
    ("Set variable", "set_var"),
    ("Parse variable", "parse_var"),
    ("Pop from shared", "pop_shared"),
    ("Extract text", "extract_text"),
    ("Write to file", "write_file"),
    ("Compare / if", "compare"),
    ("Open new tab", "new_tab"),
    ("Switch tab", "switch_tab"),
    ("Close tab", "close_tab"),
    ("Set tag", "set_tag"),
    ("Close browser", "end"),
    ("Run another scenario", "run_scenario"),
    ("Log / message", "log"),
]
ACTION_LABELS = {value: label for label, value in ACTION_OPTIONS}
ACTION_CATEGORY_PRESETS: List[Tuple[str, List[str]]] = [
    ("Navigation & interaction", ["goto", "wait_for_load_state", "wait_element", "sleep", "click", "type"]),
    ("Variables", ["set_var", "parse_var", "pop_shared", "extract_text", "write_file"]),
    ("Network", ["http_request"]),
    ("Browser tabs", ["new_tab", "switch_tab", "close_tab"]),
    ("Flow & logging", ["start", "end", "run_scenario", "log", "set_tag", "compare"]),
]
ACTION_TO_CATEGORY = {action: category for category, actions in ACTION_CATEGORY_PRESETS for action in actions}


def _deepcopy_steps(steps: object) -> List[Dict[str, Any]]:
    if not isinstance(steps, list):
        return []
    try:
        return json.loads(json.dumps(steps, ensure_ascii=False))
    except Exception:
        return [dict(item) for item in steps if isinstance(item, dict)]


class ScenariosBridge(QObject):
    modelChanged = pyqtSignal()
    selectedChanged = pyqtSignal()
    categoryChanged = pyqtSignal()
    selectedStepChanged = pyqtSignal()
    runProfileChanged = pyqtSignal()
    message = pyqtSignal(str)

    def __init__(self, profiles_bridge=None, app_state=None, parent=None) -> None:
        super().__init__(parent)
        self._profiles_bridge = profiles_bridge
        self._app_state = app_state
        self._model = DictListModel(["name", "description", "steps"], parent=self)
        self._steps_model = DictListModel([
            "row", "index", "title", "subtitle", "action", "tag", "nextOk", "nextErr", "x", "y", "accent", "selected"
        ], parent=self)
        self._categories_model = DictListModel(["name", "count", "selected"], parent=self)
        self._templates_model = DictListModel(["title", "subtitle", "action", "category"], parent=self)
        self._actions_model = DictListModel(["label", "value", "category"], parent=self)
        self._selected_name = ""
        self._selected_description = ""
        self._selected_category = ACTION_CATEGORY_PRESETS[0][0]
        self._selected_step_index = -1
        self._run_profile = ""
        self._current_steps: List[Dict[str, Any]] = []
        if app_state is not None:
            app_state.refreshRequested.connect(self.refresh)
        self._refresh_static_models()
        self.refresh()

    @pyqtProperty(QObject, constant=True)
    def model(self) -> QObject:
        return self._model

    @pyqtProperty(QObject, constant=True)
    def stepsModel(self) -> QObject:  # noqa: N802
        return self._steps_model

    @pyqtProperty(QObject, constant=True)
    def categoriesModel(self) -> QObject:  # noqa: N802
        return self._categories_model

    @pyqtProperty(QObject, constant=True)
    def templatesModel(self) -> QObject:  # noqa: N802
        return self._templates_model

    @pyqtProperty(QObject, constant=True)
    def actionsModel(self) -> QObject:  # noqa: N802
        return self._actions_model

    @pyqtProperty(QObject, constant=True)
    def profilesModel(self) -> QObject:  # noqa: N802
        return self._profiles_bridge.model if self._profiles_bridge is not None else DictListModel(["name"], parent=self)

    @pyqtProperty(str, notify=selectedChanged)
    def selectedName(self) -> str:  # noqa: N802
        return self._selected_name

    @pyqtProperty(str, notify=selectedChanged)
    def selectedDescription(self) -> str:  # noqa: N802
        return self._selected_description

    @pyqtProperty(str, notify=categoryChanged)
    def selectedCategory(self) -> str:  # noqa: N802
        return self._selected_category

    @pyqtProperty(int, notify=selectedStepChanged)
    def selectedStepIndex(self) -> int:  # noqa: N802
        return self._selected_step_index

    @pyqtProperty(str, notify=selectedStepChanged)
    def selectedStepJson(self) -> str:  # noqa: N802
        step = self._selected_step()
        return json.dumps(step or {}, ensure_ascii=False, indent=2)

    @pyqtProperty(str, notify=runProfileChanged)
    def runProfile(self) -> str:  # noqa: N802
        return self._run_profile

    @pyqtProperty(int, notify=modelChanged)
    def total(self) -> int:
        return self._model.rowCount()

    def _emit_message(self, text: str) -> None:
        self.message.emit(text)
        if self._app_state is not None:
            self._app_state.notify(text)

    def _refresh_static_models(self) -> None:
        self._categories_model.set_rows([
            {"name": name, "count": len(actions), "selected": name == self._selected_category}
            for name, actions in ACTION_CATEGORY_PRESETS
        ])
        self._templates_model.set_rows([
            {
                "title": ACTION_LABELS.get(action, action),
                "subtitle": f"{action}()",
                "action": action,
                "category": self._selected_category,
            }
            for category, actions in ACTION_CATEGORY_PRESETS
            if category == self._selected_category
            for action in actions
        ])
        self._actions_model.set_rows([
            {"label": label, "value": value, "category": ACTION_TO_CATEGORY.get(value, "Other")}
            for label, value in ACTION_OPTIONS
        ])

    @pyqtSlot()
    def refresh(self) -> None:
        scenarios = db_get_scenarios()
        self._model.set_rows([
            {"name": s.name, "description": s.description or "", "steps": len(s.steps or [])}
            for s in scenarios
        ])
        if not self._selected_name and scenarios:
            self._set_selected(scenarios[0])
        elif self._selected_name:
            loaded = db_get_scenario(self._selected_name)
            if loaded:
                self._set_selected(loaded)
            elif scenarios:
                self._set_selected(scenarios[0])
        self.modelChanged.emit()

    def _set_selected(self, scenario: Scenario) -> None:
        self._selected_name = scenario.name
        self._selected_description = scenario.description or ""
        self._current_steps = _deepcopy_steps(scenario.steps or [])
        self._ensure_start_step()
        self._ensure_step_tags()
        if self._selected_step_index >= len(self._current_steps):
            self._selected_step_index = len(self._current_steps) - 1
        if self._selected_step_index < 0 and self._current_steps:
            self._selected_step_index = 0
        self._rebuild_steps_model()
        self.selectedChanged.emit()
        self.selectedStepChanged.emit()

    def _ensure_start_step(self) -> None:
        if self._current_steps and str(self._current_steps[0].get("action") or "").lower() == "start":
            self._current_steps[0].setdefault("tag", "Start")
            return
        first_tag = str(self._current_steps[0].get("tag") or "") if self._current_steps else ""
        start: Dict[str, Any] = {"action": "start", "tag": "Start"}
        if first_tag:
            start["next_success_step"] = first_tag
        self._current_steps.insert(0, start)

    def _ensure_step_tags(self) -> None:
        seen: set[str] = set()
        counter = 1
        for index, step in enumerate(self._current_steps):
            tag = str(step.get("tag") or "").strip()
            if index == 0:
                tag = tag or "Start"
            if not tag or tag in seen:
                while f"Step{counter}" in seen:
                    counter += 1
                tag = f"Step{counter}"
            step["tag"] = tag
            seen.add(tag)

    def _rebuild_steps_model(self) -> None:
        rows = []
        for index, step in enumerate(self._current_steps):
            action = str(step.get("action") or "start")
            pos = step.get("_pos") if isinstance(step.get("_pos"), dict) else {}
            x = self._float_or(pos.get("x"), 48 + index * 290)
            y = self._float_or(pos.get("y"), 170 + (1 if self._is_error_target(index) else 0) * 110)
            rows.append({
                "row": index,
                "index": index + 1,
                "title": self._title_for_step(step, index),
                "subtitle": self._subtitle_for_step(step),
                "action": action,
                "tag": str(step.get("tag") or ""),
                "nextOk": str(step.get("next_success_step") or ""),
                "nextErr": str(step.get("next_error_step") or ""),
                "x": x,
                "y": y,
                "accent": "#06b6d4" if index == 0 else "#ef4444" if self._is_error_target(index) else "#8b5cf6",
                "selected": index == self._selected_step_index,
            })
        self._steps_model.set_rows(rows)
        self.selectedStepChanged.emit()

    @staticmethod
    def _float_or(value: Any, default: float) -> float:
        try:
            return float(value)
        except Exception:
            return float(default)

    def _is_error_target(self, index: int) -> bool:
        tag = str(self._current_steps[index].get("tag") or "") if 0 <= index < len(self._current_steps) else ""
        return bool(tag and any(str(step.get("next_error_step") or "") == tag for step in self._current_steps))

    def _title_for_step(self, step: Dict[str, Any], index: int) -> str:
        action = str(step.get("action") or "start")
        return ACTION_LABELS.get(action, str(step.get("label") or step.get("description") or action.replace("_", " ").title() or f"Step {index + 1}"))

    def _subtitle_for_step(self, step: Dict[str, Any]) -> str:
        for key in ("url", "value", "selector", "text", "message", "name", "to_var", "scenario", "pattern"):
            value = step.get(key)
            if value not in (None, ""):
                return str(value)
        ok = step.get("next_success_step")
        err = step.get("next_error_step")
        if ok or err:
            return " / ".join(part for part in [f"ok?{ok}" if ok else "", f"err?{err}" if err else ""] if part)
        return ""

    def _selected_step(self) -> Optional[Dict[str, Any]]:
        if 0 <= self._selected_step_index < len(self._current_steps):
            return self._current_steps[self._selected_step_index]
        return None

    def _save_current(self) -> None:
        if not self._selected_name:
            return
        self._ensure_start_step()
        self._ensure_step_tags()
        db_save_scenario(self._selected_name, self._current_steps, self._selected_description)
        self._rebuild_steps_model()
        self.refresh()

    @pyqtSlot(str)
    def setCategory(self, name: str) -> None:  # noqa: N802
        name = str(name or "")
        if name not in {category for category, _ in ACTION_CATEGORY_PRESETS}:
            return
        self._selected_category = name
        self._refresh_static_models()
        self.categoryChanged.emit()

    @pyqtSlot(str)
    def selectScenario(self, name: str) -> None:  # noqa: N802
        scenario = db_get_scenario(str(name or ""))
        if scenario:
            self._selected_step_index = 0
            self._set_selected(scenario)

    @pyqtSlot()
    def createScenario(self) -> None:  # noqa: N802
        base = "New scenario"
        existing = {s.name.lower() for s in db_get_scenarios()}
        name = base
        index = 2
        while name.lower() in existing:
            name = f"{base} {index}"
            index += 1
        db_save_scenario(name, [{"action": "start", "tag": "Start"}], "")
        self._selected_name = name
        self._selected_description = ""
        self._selected_step_index = 0
        self.refresh()
        self._emit_message(f"Scenario {name} created")

    @pyqtSlot(str, str)
    def saveSelected(self, name: str, description: str) -> None:  # noqa: N802
        target = str(name or self._selected_name or "Scenario").strip() or "Scenario"
        old = self._selected_name
        self._selected_description = str(description or "")
        self._ensure_start_step()
        self._ensure_step_tags()
        db_save_scenario(target, self._current_steps, self._selected_description)
        if old and old != target:
            db_delete_scenario(old)
        self._selected_name = target
        self.refresh()
        self.selectScenario(target)
        self._emit_message(f"Scenario {target} saved")

    @pyqtSlot()
    def duplicateSelected(self) -> None:  # noqa: N802
        if not self._selected_name:
            return
        base = f"{self._selected_name} copy"
        existing = {s.name.lower() for s in db_get_scenarios()}
        name = base
        index = 2
        while name.lower() in existing:
            name = f"{base} {index}"
            index += 1
        db_save_scenario(name, _deepcopy_steps(self._current_steps), self._selected_description)
        self._selected_name = name
        self.refresh()
        self.selectScenario(name)
        self._emit_message(f"Scenario duplicated as {name}")

    @pyqtSlot()
    def deleteSelected(self) -> None:  # noqa: N802
        if not self._selected_name:
            return
        old = self._selected_name
        db_delete_scenario(old)
        self._selected_name = ""
        self._selected_description = ""
        self._selected_step_index = -1
        self._current_steps = []
        self._steps_model.set_rows([])
        self.refresh()
        self._emit_message(f"Scenario {old} deleted")

    @pyqtSlot(int)
    def selectStep(self, row: int) -> None:  # noqa: N802
        row = int(row)
        if 0 <= row < len(self._current_steps):
            self._selected_step_index = row
            self._rebuild_steps_model()

    @pyqtSlot(str)
    def addAction(self, action: str) -> None:  # noqa: N802
        if not self._selected_name:
            self.createScenario()
        action = str(action or "sleep")
        insert_at = len(self._current_steps)
        step = self._default_step(action)
        self._current_steps.insert(insert_at, step)
        self._selected_step_index = insert_at
        self._save_current()

    @pyqtSlot()
    def duplicateStep(self) -> None:  # noqa: N802
        step = self._selected_step()
        if not step:
            return
        clone = copy.deepcopy(step)
        clone.pop("tag", None)
        clone.pop("_pos", None)
        self._current_steps.insert(self._selected_step_index + 1, clone)
        self._selected_step_index += 1
        self._save_current()

    @pyqtSlot()
    def deleteStep(self) -> None:  # noqa: N802
        idx = self._selected_step_index
        if idx <= 0 or idx >= len(self._current_steps):
            self._emit_message("Start step cannot be deleted")
            return
        removed_tag = str(self._current_steps[idx].get("tag") or "")
        self._current_steps.pop(idx)
        for step in self._current_steps:
            if step.get("next_success_step") == removed_tag:
                step.pop("next_success_step", None)
            if step.get("next_error_step") == removed_tag:
                step.pop("next_error_step", None)
        self._selected_step_index = min(idx, len(self._current_steps) - 1)
        self._save_current()

    @pyqtSlot(int)
    def moveStep(self, delta: int) -> None:  # noqa: N802
        idx = self._selected_step_index
        target = idx + int(delta)
        if idx <= 0 or target <= 0 or idx >= len(self._current_steps) or target >= len(self._current_steps):
            return
        self._current_steps[idx], self._current_steps[target] = self._current_steps[target], self._current_steps[idx]
        self._selected_step_index = target
        self._save_current()

    @pyqtSlot(int, float, float)
    def setStepPosition(self, row: int, x: float, y: float) -> None:  # noqa: N802
        row = int(row)
        if 0 <= row < len(self._current_steps):
            self._current_steps[row]["_pos"] = {"x": round(float(x), 2), "y": round(float(y), 2)}
            self._save_current()

    @pyqtSlot(int, int, str)
    def linkSteps(self, source_row: int, target_row: int, kind: str) -> None:  # noqa: N802
        source_row = int(source_row)
        target_row = int(target_row)
        if not (0 <= source_row < len(self._current_steps) and 0 <= target_row < len(self._current_steps)):
            return
        target_tag = str(self._current_steps[target_row].get("tag") or "").strip()
        if not target_tag:
            self._ensure_step_tags()
            target_tag = str(self._current_steps[target_row].get("tag") or "").strip()
        key = "next_error_step" if str(kind).lower() == "err" else "next_success_step"
        self._current_steps[source_row][key] = target_tag
        self._selected_step_index = source_row
        self._save_current()
        self._emit_message(f"Linked {self._current_steps[source_row].get('tag')} -> {target_tag}")

    @pyqtSlot(int, int, str)
    def deleteLink(self, source_row: int, target_row: int, kind: str) -> None:  # noqa: N802
        source_row = int(source_row)
        target_row = int(target_row)
        if not (0 <= source_row < len(self._current_steps) and 0 <= target_row < len(self._current_steps)):
            return
        key = "next_error_step" if str(kind).lower() == "err" else "next_success_step"
        target_tag = str(self._current_steps[target_row].get("tag") or "")
        if str(self._current_steps[source_row].get(key) or "") != target_tag:
            return
        self._current_steps[source_row].pop(key, None)
        self._selected_step_index = source_row
        self._save_current()
        self._emit_message("Link deleted")

    @pyqtSlot(str)
    def setRunProfile(self, name: str) -> None:  # noqa: N802
        self._run_profile = str(name or "").strip()
        self.runProfileChanged.emit()

    @pyqtSlot(str, result="QVariant")
    def selectedValue(self, key: str) -> Any:  # noqa: N802
        step = self._selected_step() or {}
        return step.get(str(key or ""), "")

    @pyqtSlot(result="QVariant")
    def selectedStep(self) -> Dict[str, Any]:  # noqa: N802
        return dict(self._selected_step() or {})

    @pyqtSlot(str, str, str, str, str, str, str, int, float, str, str, str)
    def saveStep(
        self,
        tag: str,
        action: str,
        selector: str,
        selector_type: str,
        value: str,
        variable: str,
        pattern: str,
        timeout_ms: int,
        seconds: float,
        next_success: str,
        next_error: str,
        extra_json: str,
    ) -> None:  # noqa: N802
        if self._selected_step_index < 0:
            return
        old = dict(self._current_steps[self._selected_step_index])
        action = str(action or old.get("action") or "sleep")
        step: Dict[str, Any] = {"action": action}
        clean_tag = str(tag or old.get("tag") or "").strip()
        if clean_tag:
            step["tag"] = clean_tag
        selector = str(selector or "").strip()
        if selector:
            step["selector"] = selector
            step["selector_type"] = str(selector_type or "css").strip() or "css"
        value = str(value or "").strip()
        variable = str(variable or "").strip()
        pattern = str(pattern or "").strip()
        if value:
            step["value"] = value
        if action == "goto" and value:
            step["url"] = value
        if action == "type" and value:
            step["text"] = value
            step["clear"] = bool(old.get("clear", True))
        if action == "set_var" and variable:
            step["name"] = variable
        if action in {"extract_text", "http_request"} and variable:
            step["to_var"] = variable
        if action == "parse_var":
            if variable:
                step["from_var"] = variable
            if pattern:
                step["pattern"] = pattern
                step["targets_string"] = pattern
        if action == "pop_shared" and pattern:
            step["pattern"] = pattern
            step["targets_string"] = pattern
        if timeout_ms:
            step["timeout_ms"] = int(timeout_ms)
        if seconds:
            step["seconds"] = float(seconds)
        if next_success:
            step["next_success_step"] = str(next_success).strip()
        if next_error:
            step["next_error_step"] = str(next_error).strip()
        if isinstance(old.get("_pos"), dict):
            step["_pos"] = old["_pos"]
        extra_json = str(extra_json or "").strip()
        if extra_json:
            try:
                extra = json.loads(extra_json)
                if isinstance(extra, dict):
                    step.update(extra)
            except Exception as exc:
                self._emit_message(f"Extra JSON error: {exc}")
                return
        if self._selected_step_index == 0:
            step["action"] = "start"
            step["tag"] = "Start"
        self._current_steps[self._selected_step_index] = step
        self._save_current()
        self._emit_message("Step saved")

    def _default_step(self, action: str) -> Dict[str, Any]:
        if action == "start":
            return {"action": "start", "tag": "Start"}
        if action == "goto":
            return {"action": "goto", "url": "https://example.com", "value": "https://example.com"}
        if action == "wait_for_load_state":
            return {"action": action, "state": "load", "timeout_ms": 60000}
        if action == "wait_element":
            return {"action": action, "selector": "body", "selector_type": "css", "timeout_ms": 10000}
        if action == "sleep":
            return {"action": action, "seconds": 1.0}
        if action == "click":
            return {"action": action, "selector": "button", "selector_type": "css"}
        if action == "type":
            return {"action": action, "selector": "input", "selector_type": "css", "text": "text", "value": "text", "clear": True}
        if action == "set_var":
            return {"action": action, "name": "variable", "value": "value"}
        if action == "parse_var":
            return {"action": action, "from_var": "variable", "pattern": "{{value}}", "targets_string": "{{value}}"}
        if action == "extract_text":
            return {"action": action, "selector": "body", "selector_type": "css", "to_var": "text"}
        if action == "http_request":
            return {"action": action, "method": "GET", "value": "https://example.com", "response_var": "response"}
        if action == "compare":
            return {"action": action, "left_var": "variable", "op": "equals", "value": "value"}
        if action == "new_tab":
            return {"action": action, "value": "https://example.com"}
        if action in {"switch_tab", "close_tab"}:
            return {"action": action, "tab_index": 0}
        if action == "set_tag":
            return {"action": action, "value": "tag"}
        if action == "run_scenario":
            return {"action": action, "scenario": ""}
        if action == "log":
            return {"action": action, "message": "message", "value": "message"}
        if action == "write_file":
            return {"action": action, "filename": "output.txt", "value": "{{variable}}"}
        return {"action": action}

    @pyqtSlot()
    def runSelected(self) -> None:  # noqa: N802
        if not self._selected_name:
            self._emit_message("Select scenario first")
            return
        self._save_current()
        scenario = db_get_scenario(self._selected_name)
        if not scenario:
            self._emit_message("Select scenario first")
            return
        all_accounts = db_get_accounts()
        if self._run_profile:
            accounts = [acc for acc in all_accounts if str(acc.get("name") or "") == self._run_profile]
        else:
            accounts = all_accounts[:1]
        if not accounts:
            self._emit_message("Select profile to run")
            return

        def worker() -> None:
            try:
                processed = run_scenario(accounts, scenario, max_accounts=1, scenario_path=db_get_scenario_path(scenario.name))
                self._emit_message(f"Scenario finished: {len(processed)} profile(s)")
            except Exception as exc:
                LOGGER.exception("Scenario run failed")
                self._emit_message(f"Scenario failed: {exc}")

        self._emit_message(f"Running {scenario.name}")
        threading.Thread(target=worker, daemon=True).start()

    @pyqtSlot(str, str, int)
    def runForTag(self, tag: str, scenario_name: str, max_accounts: int) -> None:  # noqa: N802
        tag = str(tag or "").strip()
        scenario_name = str(scenario_name or self._selected_name or "").strip()
        if tag == "All tags":
            tag = ""
        if not scenario_name:
            self._emit_message("Select scenario first")
            return
        scenario = db_get_scenario(scenario_name)
        if not scenario:
            self._emit_message("Scenario not found")
            return
        try:
            limit = max(1, int(max_accounts or 1))
        except Exception:
            limit = 1
        all_accounts = db_get_accounts()
        accounts = [
            acc for acc in all_accounts
            if not tag or str(acc.get("stage") or "No tag") == tag
        ]
        if not accounts:
            self._emit_message("No profiles for selected tag")
            return

        def worker() -> None:
            try:
                processed = run_scenario(
                    accounts,
                    scenario,
                    max_accounts=limit,
                    scenario_path=db_get_scenario_path(scenario.name),
                )
                self._emit_message(f"Scenario finished: {len(processed)} profile(s)")
            except Exception as exc:
                LOGGER.exception("Scenario batch run failed")
                self._emit_message(f"Scenario failed: {exc}")

        self._emit_message(f"Running {scenario.name} for {tag or 'all tags'}")
        threading.Thread(target=worker, daemon=True).start()
