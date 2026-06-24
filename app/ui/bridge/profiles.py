"""Profiles bridge for QML."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

from app.core.browser_interface import BrowserInterface
from app.storage.db import (
    db_add_account,
    db_delete_account,
    db_get_accounts,
    db_get_all_tags,
    db_get_setting,
    db_resolve_tag_color,
    db_set_setting,
    db_update_account,
    profile_dir_for_email,
)
from app.ui.bridge.models import DictListModel
from app.utils.parsing import DEFAULT_ACCOUNT_TEMPLATE, parse_account_line

LOGGER = logging.getLogger(__name__)


class ProfilesBridge(QObject):
    modelChanged = pyqtSignal()
    countsChanged = pyqtSignal()
    message = pyqtSignal(str)
    _uiCall = pyqtSignal(object)  # thread-safe signal to run callables on the main Qt thread

    def __init__(self, app_state=None, parent=None) -> None:
        super().__init__(parent)
        self._uiCall.connect(self._runUiCall)
        self._model = DictListModel([
            "name", "id", "browser", "proxy", "lastActive", "status", "stage", "tags", "tagsList", "running"
        ], parent=self)
        self._stages_model = DictListModel(["name", "count", "selected"], parent=self)
        self._proxy_pools_model = DictListModel(["name"], parent=self)
        self._available_tags_model = DictListModel(["name", "color"], parent=self)
        self._selected_stage = ""
        self._live_browsers: Dict[str, BrowserInterface] = {}
        self._app_state = app_state
        self._proxy_lock = threading.Lock()
        if app_state is not None:
            app_state.refreshRequested.connect(self.refresh)
        self.refresh()

    @pyqtProperty(QObject, constant=True)
    def model(self) -> QObject:
        return self._model

    @pyqtProperty(QObject, constant=True)
    def stagesModel(self) -> QObject:  # noqa: N802
        return self._stages_model

    @pyqtProperty(QObject, constant=True)
    def proxyPoolsModel(self) -> QObject:  # noqa: N802
        return self._proxy_pools_model

    @pyqtProperty(QObject, constant=True)
    def availableTagsModel(self) -> QObject:  # noqa: N802
        return self._available_tags_model

    @pyqtProperty(str, notify=modelChanged)
    def selectedStage(self) -> str:  # noqa: N802
        return self._selected_stage

    @pyqtProperty(int, notify=countsChanged)
    def total(self) -> int:
        return self._model.rowCount()

    @pyqtProperty(int, notify=countsChanged)
    def running(self) -> int:
        return len(self._live_browsers)

    def live_browsers(self) -> Dict[str, BrowserInterface]:
        return self._live_browsers

    def _runUiCall(self, func: object) -> None:
        if callable(func):
            try:
                func()
            except Exception:
                LOGGER.exception("UI dispatch failed")

    def _invoke_ui(self, func) -> None:
        """Run *func* on the main Qt thread (safe from any thread)."""
        self._uiCall.emit(func)

    def _emit_message(self, text: str) -> None:
        self.message.emit(text)
        if self._app_state is not None:
            self._app_state.notify(text)

    def _proxy_label(self, acc: Dict[str, Any]) -> str:
        mode = str(acc.get("proxy_mode") or "none")
        if mode == "none":
            return "None"
        if mode == "random":
            pool = str(acc.get("proxy_pool") or "").strip()
            return f"Random: {pool}" if pool else "Random"
        host = str(acc.get("proxy_host") or "")
        port = acc.get("proxy_port")
        if host and port:
            return f"{host}:{port}"
        return str(acc.get("proxy_pool") or "Manual")

    @staticmethod
    def _settings_dict(value: Any) -> Optional[Dict[str, Any]]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else None
            except Exception:
                return None
        return None

    @staticmethod
    def _parse_proxy_value(value: str) -> Dict[str, Any]:
        raw = str(value or "").strip()
        if not raw:
            return {}
        scheme = "socks5"
        host = ""
        port: Any = None
        user = ""
        password = ""
        if "://" in raw:
            parsed = urlparse(raw)
            scheme = parsed.scheme or scheme
            if parsed.hostname and parsed.port:
                host = parsed.hostname
                port = parsed.port
                user = parsed.username or ""
                password = parsed.password or ""
            else:
                tail = raw.split("://", 1)[1]
                parts = [p.strip() for p in tail.split(":")]
                if len(parts) >= 2:
                    host, port = parts[0], parts[1]
                if len(parts) >= 4:
                    user, password = parts[2], parts[3]
        elif "@" in raw:
            creds, address = raw.rsplit("@", 1)
            if ":" in creds:
                user, password = creds.split(":", 1)
            if ":" in address:
                host, port = address.rsplit(":", 1)
        else:
            parts = [p.strip() for p in raw.split(":")]
            if len(parts) >= 2:
                host, port = parts[0], parts[1]
            if len(parts) >= 4:
                user, password = parts[2], parts[3]
        if not host or not port:
            return {}
        try:
            port = int(port)
        except Exception:
            return {}
        return {
            "proxy_scheme": scheme,
            "proxy_host": host,
            "proxy_port": port,
            "proxy_user": user,
            "proxy_password": password,
        }

    def _take_proxy_from_pool(self, pool_name: str, profile_name: str) -> Dict[str, Any]:
        pool_name = str(pool_name or "").strip()
        if not pool_name:
            return {}
        try:
            pools = json.loads(db_get_setting("proxy_pools") or "{}")
        except Exception:
            pools = {}
        pool = pools.get(pool_name) if isinstance(pools, dict) else None
        proxies = pool.get("proxies", []) if isinstance(pool, dict) else []
        for entry in proxies:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("assigned_to") or "").strip():
                continue
            details = self._parse_proxy_value(str(entry.get("value") or ""))
            if not details:
                continue
            entry["assigned_to"] = profile_name
            db_set_setting("proxy_pools", json.dumps(pools, ensure_ascii=False))
            details["proxy_pool"] = pool_name
            return details
        return {"proxy_pool": pool_name}

    @pyqtSlot()
    def refresh(self) -> None:
        rows: List[Dict[str, Any]] = []
        accounts = db_get_accounts()
        tag_counts: Dict[str, int] = {}
        all_tags: set[str] = set()
        for acc in accounts:
            acc_tags = acc.get("tags") or []
            if not acc_tags:
                legacy = str(acc.get("stage") or "").strip()
                if legacy:
                    acc_tags = [legacy]
            for t in acc_tags:
                t = str(t).strip()
                if t:
                    tag_counts[t] = tag_counts.get(t, 0) + 1
                    all_tags.add(t)
        try:
            configured_stages = json.loads(db_get_setting("stages_json") or "[]")
        except Exception:
            configured_stages = []
        for stage in configured_stages if isinstance(configured_stages, list) else []:
            clean_stage = str(stage or "").strip()
            if clean_stage:
                tag_counts.setdefault(clean_stage, 0)
                all_tags.add(clean_stage)

        self._stages_model.set_rows(
            [{"name": "All tags", "count": len(accounts), "selected": not self._selected_stage}]
            + [
                {"name": tag, "count": count, "selected": self._selected_stage == tag}
                for tag, count in sorted(tag_counts.items(), key=lambda item: item[0].lower())
            ]
        )

        self._available_tags_model.set_rows([
            {"name": t, "color": db_resolve_tag_color(t)}
            for t in sorted(all_tags)
        ])

        # Populate proxy pools model
        pool_names: List[str] = []
        try:
            pools = json.loads(db_get_setting("proxy_pools") or "{}")
            if isinstance(pools, dict):
                pool_names = sorted(pools.keys())
        except Exception:
            pass
        self._proxy_pools_model.set_rows([{"name": p} for p in pool_names])

        sorted_accounts = sorted(accounts, key=lambda a: (
            ",".join(a.get("tags") or ["~"]).lower(),
            str(a.get("name") or "").lower(),
        ))
        for index, acc in enumerate(sorted_accounts, start=1):
            name = str(acc.get("name") or f"profile{index}")
            acc_tags: List[str] = [str(t).strip() for t in (acc.get("tags") or []) if str(t).strip()]
            if not acc_tags:
                legacy = str(acc.get("stage") or "").strip()
                if legacy:
                    acc_tags = [legacy]
            primary_tag = acc_tags[0] if acc_tags else "No tag"
            if self._selected_stage and self._selected_stage != primary_tag:
                continue
            running = name in self._live_browsers
            engine = str(acc.get("_browser_engine") or acc.get("browser_engine") or "camoufox")
            if engine == "cloakbrowser":
                browser_label = "CloakBrowser"
            else:
                browser_label = "Camoufox"
            rows.append({
                "name": name,
                "id": str(acc.get("id") or f"#{index:04d}"),
                "browser": browser_label,
                "proxy": self._proxy_label(acc),
                "lastActive": str(acc.get("last_active") or "now" if running else acc.get("last_active") or "idle"),
                "status": "Running" if running else "Stopped",
                "stage": primary_tag,
                "tags": "  ".join(f"#{tag}" for tag in acc_tags) if acc_tags else "#profile",
                "tagsList": acc_tags,
                "running": running,
            })
        self._model.set_rows(rows)
        self.modelChanged.emit()
        self.countsChanged.emit()

    @pyqtSlot(str)
    def setStageFilter(self, stage: str) -> None:  # noqa: N802
        stage = str(stage or "")
        if stage == "All tags":
            stage = ""
        self._selected_stage = stage
        self.refresh()

    @pyqtSlot(result=str)
    def getGpuPresets(self) -> str:  # noqa: N802
        """Return JSON of GPU presets for the editor dropdown."""
        from app.storage.db import GPU_PRESETS
        return json.dumps([{ "name": k, "vendor": v["vendor"], "renderer": v["renderer"] } for k, v in GPU_PRESETS.items()], ensure_ascii=False)

    @pyqtSlot(result=str)
    def getScreenResolutionPresets(self) -> str:  # noqa: N802
        """Return JSON of screen resolution presets for the editor dropdown."""
        from app.storage.db import SCREEN_RESOLUTION_PRESETS
        return json.dumps([{ "name": k, "width": v["width"], "height": v["height"] } for k, v in SCREEN_RESOLUTION_PRESETS.items()], ensure_ascii=False)

    @pyqtSlot(result=str)
    def getAllTags(self) -> str:  # noqa: N802
        """Return JSON list of all known tags for the multi-select."""
        return json.dumps(db_get_all_tags(), ensure_ascii=False)

    @pyqtSlot()
    def createProfile(self) -> None:  # noqa: N802
        existing = db_get_accounts()
        next_index = len(existing) + 1
        names = {str(acc.get("name") or "").lower() for acc in existing}
        while f"profile{next_index}".lower() in names:
            next_index += 1
        name = f"profile{next_index}"
        try:
            db_add_account({"name": name, "stage": ""})
        except Exception as exc:
            self._emit_message(f"Cannot create profile: {exc}")
            return
        self._emit_message(f"Profile {name} created")
        self.refresh()

    @pyqtSlot(str, str, str, str)
    def importProfiles(self, lines: str, template: str, default_stage: str, proxy_pool: str) -> None:  # noqa: N802
        raw_lines = [line.strip() for line in str(lines or "").replace("\r", "\n").split("\n") if line.strip()]
        if not raw_lines:
            self._emit_message("Profile import list is empty")
            return
        template = str(template or "").strip() or DEFAULT_ACCOUNT_TEMPLATE
        default_stage = str(default_stage or "").strip()
        proxy_pool = str(proxy_pool or "").strip()
        added = 0
        errors = 0
        for line in raw_lines:
            try:
                parsed = parse_account_line(line, template)
                name = str(parsed.get("name") or parsed.get("email") or "").strip()
                if not name:
                    name = f"profile{len(db_get_accounts()) + 1}"
                account: Dict[str, Any] = {
                    "name": name,
                    "stage": default_stage,
                    "extra_fields": dict(parsed),
                }
                for key, value in parsed.items():
                    account[str(key)] = str(value)
                account.update(self._take_proxy_from_pool(proxy_pool, name))
                db_add_account(account)
                added += 1
            except Exception:
                LOGGER.exception("Profile import failed for line: %s", line)
                errors += 1
        self._emit_message(f"Imported {added} profile(s)" + (f", {errors} failed" if errors else ""))
        self.refresh()

    @pyqtSlot(str, str, result="QVariant")
    def getProfile(self, name: str, engine: str = "camoufox") -> Dict[str, Any]:  # noqa: N802
        target = str(name or "").strip()
        acc = next((item for item in db_get_accounts() if str(item.get("name") or "") == target), None)
        if not acc:
            return {}
        engine = str(engine or "camoufox").lower()
        settings_key = "cloakbrowser_settings" if engine == "cloakbrowser" else "camoufox_settings"
        settings = acc.get(settings_key)
        if isinstance(settings, str):
            try:
                import json

                parsed = json.loads(settings)
                settings = parsed if isinstance(parsed, dict) else {}
            except Exception:
                settings = {}
        if not isinstance(settings, dict):
            settings = {}
        return {
            "name": str(acc.get("name") or ""),
            "stage": str(acc.get("stage") or ""),
            "proxy_host": str(acc.get("proxy_host") or ""),
            "proxy_port": "" if acc.get("proxy_port") in (None, "") else str(acc.get("proxy_port")),
            "proxy_user": str(acc.get("proxy_user") or ""),
            "proxy_password": str(acc.get("proxy_password") or ""),
            "locale": str(settings.get("locale") or ""),
            "timezone": str(settings.get("timezone") or ""),
            "user_agent": str(settings.get("user_agent") or ""),
            "webgl_vendor": str(settings.get("webgl_vendor") or settings.get("gpu_vendor") or ""),
            "hardware_concurrency": "" if settings.get("hardware_concurrency") in (None, "", 0) else str(settings.get("hardware_concurrency")),
        }

    @pyqtSlot(str, result="QVariantMap")
    def getProfileData(self, name: str) -> Dict[str, Any]:  # noqa: N802
        """Load a full profile as a QVariantMap for the editor, including browser_overrides."""
        target = str(name or "").strip()
        acc = next((item for item in db_get_accounts() if str(item.get("name") or "") == target), None)
        if not acc:
            return {}
        engine = str(acc.get("_browser_engine") or acc.get("browser_engine") or "camoufox").lower()

        # Migrate legacy per-engine settings into browser_overrides if needed
        overrides: Dict[str, Any] = dict(acc.get("browser_overrides") or {})
        if not overrides:
            settings_key = "cloakbrowser_settings" if engine == "cloakbrowser" else "camoufox_settings"
            legacy = acc.get(settings_key)
            if isinstance(legacy, str):
                try:
                    legacy = json.loads(legacy)
                except Exception:
                    legacy = {}
            if isinstance(legacy, dict):
                overrides["locale"] = str(legacy.get("locale") or "")
                overrides["timezone"] = str(legacy.get("timezone") or "")
                overrides["user_agent"] = str(legacy.get("user_agent") or "")
                overrides["gpu_vendor"] = str(legacy.get("gpu_vendor") or legacy.get("webgl_vendor") or "")
                overrides["gpu_renderer"] = str(legacy.get("gpu_renderer") or "")
                overrides["hardware_concurrency"] = legacy.get("hardware_concurrency") or 0
                overrides["platform"] = str(legacy.get("platform") or "")
                overrides["humanize"] = bool(legacy.get("humanize", False))
                overrides["human_preset"] = str(legacy.get("human_preset") or "default")
                overrides["geoip"] = bool(legacy.get("geoip", False))
                overrides["block_images"] = bool(legacy.get("block_images", False))
                overrides["screen_width"] = legacy.get("screen_width") or 0
                overrides["screen_height"] = legacy.get("screen_height") or 0
                overrides["launch_args"] = legacy.get("launch_args") or []
                overrides["fingerprint_seed"] = legacy.get("fingerprint_seed") or 0
                overrides["color_scheme"] = str(legacy.get("color_scheme") or "")

        acc_tags = acc.get("tags") or []
        if not acc_tags:
            legacy_stage = str(acc.get("stage") or "").strip()
            if legacy_stage:
                acc_tags = [legacy_stage]

        return {
            "name": str(acc.get("name") or ""),
            "engine": engine,
            "tags": [str(t) for t in acc_tags],
            "notes": str(acc.get("notes") or ""),
            "proxy_mode": str(acc.get("proxy_mode") or "none"),
            "proxy_pool": str(acc.get("proxy_pool") or ""),
            "proxy_host": str(acc.get("proxy_host") or ""),
            "proxy_port": "" if acc.get("proxy_port") in (None, "") else str(acc.get("proxy_port")),
            "proxy_user": str(acc.get("proxy_user") or ""),
            "proxy_password": str(acc.get("proxy_password") or ""),
            "proxy_scheme": str(acc.get("proxy_scheme") or "socks5"),
            "overrides": {
                "locale": str(overrides.get("locale") or ""),
                "timezone": str(overrides.get("timezone") or ""),
                "user_agent": str(overrides.get("user_agent") or ""),
                "gpu_vendor": str(overrides.get("gpu_vendor") or ""),
                "gpu_renderer": str(overrides.get("gpu_renderer") or ""),
                "hardware_concurrency": int(overrides.get("hardware_concurrency") or 0),
                "platform": str(overrides.get("platform") or ""),
                "humanize": bool(overrides.get("humanize", False)),
                "human_preset": str(overrides.get("human_preset") or "default"),
                "geoip": bool(overrides.get("geoip", False)),
                "block_images": bool(overrides.get("block_images", False)),
                "screen_width": int(overrides.get("screen_width") or 0),
                "screen_height": int(overrides.get("screen_height") or 0),
                "launch_args": list(overrides.get("launch_args") or []),
                "fingerprint_seed": int(overrides.get("fingerprint_seed") or 0),
                "color_scheme": str(overrides.get("color_scheme") or ""),
            },
        }

    @pyqtSlot(str, "QVariantMap")
    def saveProfileData(self, original_name: str, data: Dict[str, Any]) -> None:  # noqa: N802
        """Save a full profile from a QVariantMap."""
        original_name = str(original_name or "").strip()
        if not original_name:
            self._emit_message("Profile name is required")
            return
        data = data or {}
        clean_name = str(data.get("name") or "").strip()
        if not clean_name:
            self._emit_message("Profile name is required")
            return

        updates: Dict[str, Any] = {
            "name": clean_name,
            "_browser_engine": str(data.get("engine") or "camoufox").lower(),
            "notes": str(data.get("notes") or ""),
            "proxy_mode": str(data.get("proxy_mode") or "none"),
            "proxy_pool": str(data.get("proxy_pool") or ""),
            "proxy_host": str(data.get("proxy_host") or "").strip(),
            "proxy_user": str(data.get("proxy_user") or "").strip(),
            "proxy_password": str(data.get("proxy_password") or "").strip(),
            "proxy_scheme": str(data.get("proxy_scheme") or "socks5").strip() or "socks5",
        }

        # Tags
        raw_tags = data.get("tags")
        if isinstance(raw_tags, list):
            updates["tags"] = [str(t).strip() for t in raw_tags if str(t).strip()]
        else:
            updates["tags"] = []

        # Proxy port
        port_text = str(data.get("proxy_port") or "").strip()
        if port_text:
            try:
                updates["proxy_port"] = int(port_text)
            except Exception:
                self._emit_message("Proxy port must be a number")
                return
        else:
            updates["proxy_port"] = None

        # If proxy mode is none, clear proxy fields
        if updates["proxy_mode"] == "none":
            updates["proxy_host"] = ""
            updates["proxy_port"] = None
            updates["proxy_user"] = ""
            updates["proxy_password"] = ""
            updates["proxy_pool"] = ""

        # If proxy mode is random, clear manual fields
        if updates["proxy_mode"] == "random":
            updates["proxy_host"] = ""
            updates["proxy_port"] = None
            updates["proxy_user"] = ""
            updates["proxy_password"] = ""

        # Browser overrides
        raw_overrides = data.get("overrides") or {}
        if not isinstance(raw_overrides, dict):
            raw_overrides = {}
        overrides: Dict[str, Any] = {}
        for key in ("locale", "timezone", "user_agent", "gpu_vendor", "gpu_renderer", "platform", "human_preset", "color_scheme"):
            val = str(raw_overrides.get(key) or "").strip()
            if val:
                overrides[key] = val
        for key in ("humanize", "geoip", "block_images"):
            overrides[key] = bool(raw_overrides.get(key, False))
        hc = raw_overrides.get("hardware_concurrency")
        if hc not in (None, "", 0, "0"):
            try:
                overrides["hardware_concurrency"] = int(hc)
            except Exception:
                pass
        for key in ("screen_width", "screen_height", "fingerprint_seed"):
            val = raw_overrides.get(key)
            if val not in (None, "", 0, "0"):
                try:
                    overrides[key] = int(val)
                except Exception:
                    pass
        la = raw_overrides.get("launch_args")
        if isinstance(la, list):
            overrides["launch_args"] = [str(a).strip() for a in la if str(a).strip()]

        updates["browser_overrides"] = overrides
        # Clear legacy per-engine settings dicts
        updates["__delete_keys__"] = ["camoufox_settings", "cloakbrowser_settings"]

        try:
            db_update_account(original_name, updates)
        except Exception as exc:
            self._emit_message(f"Cannot save profile: {exc}")
            return
        self._emit_message(f"Profile {clean_name} saved")
        self.refresh()

    @pyqtSlot(str, result=str)
    def getProxiesForPool(self, pool_name: str) -> str:  # noqa: N802
        """Return JSON list of proxy entries in a pool for the fixed-mode dropdown."""
        pool_name = str(pool_name or "").strip()
        if not pool_name:
            return "[]"
        try:
            pools = json.loads(db_get_setting("proxy_pools") or "{}")
        except Exception:
            pools = {}
        pool = pools.get(pool_name) if isinstance(pools, dict) else None
        proxies = pool.get("proxies", []) if isinstance(pool, dict) else []
        items = []
        for idx, entry in enumerate(proxies):
            if not isinstance(entry, dict):
                continue
            value = str(entry.get("value") or "")
            assigned = str(entry.get("assigned_to") or "")
            items.append({"index": idx, "value": value, "label": value, "assigned": assigned})
        return json.dumps(items, ensure_ascii=False)

    @pyqtSlot(str, str, result="QVariantMap")
    def getProxyFromPool(self, pool_name: str, index: str) -> Dict[str, Any]:  # noqa: N802
        """Return parsed proxy fields for a specific pool entry (for fixed mode)."""
        pool_name = str(pool_name or "").strip()
        try:
            idx = int(index)
        except Exception:
            return {}
        try:
            pools = json.loads(db_get_setting("proxy_pools") or "{}")
        except Exception:
            pools = {}
        pool = pools.get(pool_name) if isinstance(pools, dict) else None
        proxies = pool.get("proxies", []) if isinstance(pool, dict) else []
        if not (0 <= idx < len(proxies)) or not isinstance(proxies[idx], dict):
            return {}
        value = str(proxies[idx].get("value") or "")
        details = self._parse_proxy_value(value)
        if not details:
            details = {"proxy_scheme": "socks5", "proxy_host": "", "proxy_port": "", "proxy_user": "", "proxy_password": ""}
        details["proxy_pool"] = pool_name
        return details

    def _checkout_random_proxy(self, pool_name: str, profile_name: str) -> Optional[str]:
        """Atomically checkout an unassigned proxy from a pool. Returns proxy string or None."""
        with self._proxy_lock:
            try:
                pools = json.loads(db_get_setting("proxy_pools") or "{}")
            except Exception:
                pools = {}
            pool = pools.get(pool_name) if isinstance(pools, dict) else None
            proxies = pool.get("proxies", []) if isinstance(pool, dict) else []
            for entry in proxies:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("assigned_to") or "").strip():
                    continue
                value = str(entry.get("value") or "").strip()
                if not value:
                    continue
                entry["assigned_to"] = profile_name
                db_set_setting("proxy_pools", json.dumps(pools, ensure_ascii=False))
                return value
            return None

    def _release_proxy(self, profile_name: str) -> None:
        """Release any proxy checked out by this profile."""
        with self._proxy_lock:
            try:
                pools = json.loads(db_get_setting("proxy_pools") or "{}")
            except Exception:
                pools = {}
            changed = False
            for pool in pools.values():
                if not isinstance(pool, dict):
                    continue
                for entry in pool.get("proxies", []):
                    if isinstance(entry, dict) and str(entry.get("assigned_to") or "").strip() == profile_name:
                        entry["assigned_to"] = ""
                        changed = True
            if changed:
                db_set_setting("proxy_pools", json.dumps(pools, ensure_ascii=False))

    @pyqtSlot(str, result=str)
    def getProfileVariables(self, name: str) -> str:  # noqa: N802
        target = str(name or "").strip()
        acc = next((item for item in db_get_accounts() if str(item.get("name") or "") == target), None)
        if not acc:
            return "{}"
        hidden = {
            "id",
            "stage",
            "proxy_host",
            "proxy_port",
            "proxy_user",
            "proxy_password",
            "proxy_scheme",
            "proxy_pool",
            "camoufox_settings",
            "cloakbrowser_settings",
            "_browser_engine",
            "browser_engine",
            "last_active",
        }
        variables: Dict[str, Any] = {}
        extra = acc.get("extra_fields")
        if isinstance(extra, dict):
            variables.update(extra)
        for key, value in acc.items():
            if key not in hidden and key != "extra_fields":
                variables[str(key)] = value
        return json.dumps(variables, ensure_ascii=False, indent=2)

    @pyqtSlot(str, str)
    def saveProfileVariables(self, name: str, variables_json: str) -> None:  # noqa: N802
        target = str(name or "").strip()
        if not target:
            return
        try:
            payload = json.loads(str(variables_json or "{}"))
        except Exception as exc:
            self._emit_message(f"Variables JSON error: {exc}")
            return
        if not isinstance(payload, dict):
            self._emit_message("Variables must be a JSON object")
            return
        updates = {"extra_fields": payload}
        for key, value in payload.items():
            if str(key) == "name":
                continue
            updates[str(key)] = value
        try:
            db_update_account(target, updates)
        except Exception as exc:
            self._emit_message(f"Cannot save variables: {exc}")
            return
        self._emit_message(f"Variables saved for {target}")
        self.refresh()

    @staticmethod
    def _read_cookie_rows(profile_name: str) -> List[Dict[str, Any]]:
        import os
        import shutil
        import sqlite3
        import tempfile

        profile_dir = Path(profile_dir_for_email(profile_name))
        if not profile_dir.exists():
            return []

        def read_rows(db_path: Path, query: str) -> List[tuple]:
            tmp_path: Optional[str] = None
            try:
                try:
                    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1.0)
                except Exception:
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".sqlite3")
                    tmp_path = tmp.name
                    tmp.close()
                    shutil.copy2(str(db_path), tmp_path)
                    con = sqlite3.connect(f"file:{tmp_path}?mode=ro", uri=True, timeout=1.0)
                try:
                    cur = con.cursor()
                    cur.execute(query)
                    return list(cur.fetchall())
                finally:
                    con.close()
            finally:
                if tmp_path:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

        rows_out: List[Dict[str, Any]] = []
        candidates = [
            ("firefox", profile_dir / "cookies.sqlite"),
            ("chromium", profile_dir / "Cookies"),
            ("chromium", profile_dir / "Network" / "Cookies"),
            ("chromium", profile_dir / "Default" / "Cookies"),
            ("chromium", profile_dir / "Default" / "Network" / "Cookies"),
        ]
        for source, path in candidates:
            if not path.exists():
                continue
            try:
                if source == "firefox":
                    for host, cookie_name, value, cookie_path, expiry, secure, http_only in read_rows(
                        path,
                        "SELECT host, name, value, path, expiry, isSecure, isHttpOnly FROM moz_cookies",
                    ):
                        rows_out.append({
                            "domain": str(host or ""),
                            "name": str(cookie_name or ""),
                            "value": str(value or ""),
                            "path": str(cookie_path or "/"),
                            "expires": int(expiry or 0),
                            "secure": bool(secure),
                            "httpOnly": bool(http_only),
                        })
                else:
                    for host, cookie_name, value, encrypted, cookie_path, expires_utc, secure, http_only in read_rows(
                        path,
                        "SELECT host_key, name, value, encrypted_value, path, expires_utc, is_secure, is_httponly FROM cookies",
                    ):
                        cookie_value = str(value or "")
                        if not cookie_value and encrypted:
                            cookie_value = "<encrypted>"
                        rows_out.append({
                            "domain": str(host or ""),
                            "name": str(cookie_name or ""),
                            "value": cookie_value,
                            "path": str(cookie_path or "/"),
                            "secure": bool(secure),
                            "httpOnly": bool(http_only),
                        })
            except Exception:
                LOGGER.exception("Cannot read cookies from %s", path)
        return [row for row in rows_out if row.get("domain") and row.get("name")]

    @pyqtSlot(str, result=str)
    def getProfileCookiesJson(self, name: str) -> str:  # noqa: N802
        return json.dumps(self._read_cookie_rows(str(name or "")), ensure_ascii=False, indent=2)

    @pyqtSlot(str, str)
    def saveProfileCookiesJson(self, name: str, cookies_json: str) -> None:  # noqa: N802
        target = str(name or "").strip()
        try:
            cookies = json.loads(str(cookies_json or "[]"))
        except Exception as exc:
            self._emit_message(f"Cookies JSON error: {exc}")
            return
        if not isinstance(cookies, list):
            self._emit_message("Cookies must be a JSON array")
            return
        acc = next((item for item in db_get_accounts() if str(item.get("name") or "") == target), None)
        if not acc:
            self._emit_message("Profile not found")
            return

        def worker() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            engine = str(acc.get("_browser_engine") or acc.get("browser_engine") or "camoufox")
            settings = self._settings_dict(
                acc.get("cloakbrowser_settings")
                if engine == "cloakbrowser"
                else acc.get("camoufox_settings")
            )
            browser = BrowserInterface(
                profile_name=target,
                proxy=self._proxy_for(acc),
                keep_browser_open=False,
                browser_engine=engine,
                browser_settings=settings,
            )
            try:
                async def run() -> None:
                    await browser.start()
                    context = getattr(browser, "context", None)
                    if context is None:
                        raise RuntimeError("Browser context is not initialized")
                    await context.clear_cookies()
                    clean = []
                    for cookie in cookies:
                        if not isinstance(cookie, dict):
                            continue
                        item = {
                            "name": str(cookie.get("name") or "").strip(),
                            "value": str(cookie.get("value") or ""),
                            "domain": str(cookie.get("domain") or "").strip(),
                            "path": str(cookie.get("path") or "/") or "/",
                        }
                        if not item["name"] or not item["domain"]:
                            continue
                        for key in ("expires", "httpOnly", "secure", "sameSite"):
                            if key in cookie:
                                item[key] = cookie[key]
                        clean.append(item)
                    if clean:
                        await context.add_cookies(clean)
                    await browser.close(force=True)

                loop.run_until_complete(run())
                self._invoke_ui(lambda: self._emit_message(f"Cookies saved for {target}"))
            except Exception as exc:
                LOGGER.exception("Cannot save cookies for %s", target)
                self._invoke_ui(lambda exc=exc: self._emit_message(f"Cannot save cookies: {exc}"))
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    @pyqtSlot(str, str, str, str, str, str, str, str, str, str, str, str, str)
    def saveProfile(
        self,
        original_name: str,
        name: str,
        stage: str,
        proxy_host: str,
        proxy_port: str,
        proxy_user: str,
        proxy_password: str,
        engine: str,
        locale: str,
        timezone: str,
        user_agent: str,
        webgl_vendor: str,
        hardware_concurrency: str,
    ) -> None:  # noqa: N802
        original_name = str(original_name or "").strip()
        clean_name = str(name or "").strip()
        if not original_name or not clean_name:
            self._emit_message("Profile name is required")
            return
        updates: Dict[str, Any] = {
            "name": clean_name,
            "stage": str(stage or "").strip(),
            "_browser_engine": str(engine or "camoufox").lower(),
            "proxy_host": str(proxy_host or "").strip(),
            "proxy_user": str(proxy_user or "").strip(),
            "proxy_password": str(proxy_password or "").strip(),
        }
        port_text = str(proxy_port or "").strip()
        if port_text:
            try:
                updates["proxy_port"] = int(port_text)
            except Exception:
                self._emit_message("Proxy port must be a number")
                return
        else:
            updates["proxy_port"] = None

        browser_settings: Dict[str, Any] = {}
        for key, value in {
            "locale": locale,
            "timezone": timezone,
            "user_agent": user_agent,
            "webgl_vendor": webgl_vendor,
            "gpu_vendor": webgl_vendor,
        }.items():
            value = str(value or "").strip()
            if value:
                browser_settings[key] = value
        cpu_text = str(hardware_concurrency or "").strip()
        if cpu_text:
            try:
                browser_settings["hardware_concurrency"] = int(cpu_text)
            except Exception:
                self._emit_message("CPU cores must be a number")
                return
        settings_key = "cloakbrowser_settings" if str(engine or "").lower() == "cloakbrowser" else "camoufox_settings"
        if browser_settings:
            updates[settings_key] = browser_settings
        else:
            updates["__delete_keys__"] = [settings_key]
        try:
            db_update_account(original_name, updates)
        except Exception as exc:
            self._emit_message(f"Cannot save profile: {exc}")
            return
        self._emit_message(f"Profile {clean_name} saved")
        self.refresh()

    @pyqtSlot(str)
    def deleteProfile(self, name: str) -> None:  # noqa: N802
        name = str(name or "").strip()
        if not name:
            return
        self.stopProfile(name)
        db_delete_account(name)
        self._emit_message(f"Profile {name} deleted")
        self.refresh()

    @pyqtSlot(str)
    def startProfile(self, name: str) -> None:  # noqa: N802
        name = str(name or "").strip()
        if not name or name in self._live_browsers:
            return
        acc = next((item for item in db_get_accounts() if str(item.get("name") or "") == name), None)
        if not acc:
            self._emit_message(f"Profile {name} not found")
            return
        engine = str(acc.get("_browser_engine") or acc.get("browser_engine") or "camoufox")

        # --- Resolve proxy based on proxy_mode ---
        proxy_mode = str(acc.get("proxy_mode") or "none")
        proxy = ""
        if proxy_mode == "manual":
            proxy = self._proxy_for(acc)
        elif proxy_mode == "fixed":
            proxy = self._proxy_for(acc)
        elif proxy_mode == "random":
            pool = str(acc.get("proxy_pool") or "").strip()
            if pool:
                checked_out = self._checkout_random_proxy(pool, name)
                if not checked_out:
                    self._emit_message(f"No available proxies in pool {pool}")
                    return
                proxy = checked_out
            else:
                self._emit_message("No proxy pool configured for random mode")
                return

        # --- Get browser_overrides as settings ---
        overrides = acc.get("browser_overrides")
        if not isinstance(overrides, dict):
            overrides = {}
        settings = self._settings_dict(acc.get("cloakbrowser_settings") if engine == "cloakbrowser" else acc.get("camoufox_settings"))
        if settings is None:
            settings = {}
        # Merge browser_overrides on top of legacy settings
        settings = {**settings, **overrides}

        browser = BrowserInterface(
            profile_name=name,
            proxy=proxy,
            keep_browser_open=True,
            browser_engine=engine,
            browser_settings=settings,
        )
        browser.add_close_callback(lambda: self._invoke_ui(lambda: self._on_browser_closed(name, browser)))
        self._live_browsers[name] = browser
        self._emit_message(f"Starting browser for {name}")
        self.refresh()

        def worker() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            # Keep a reference so stopProfile can request shutdown from outside
            browser._stop_requested = False

            async def _run_and_keep_alive() -> None:
                try:
                    await browser.start()
                except Exception as exc:
                    LOGGER.exception("Browser start failed for %s", name)
                    self._invoke_ui(lambda exc=exc: self._on_browser_failed(name, browser, exc))
                    return

                ping_counter = 0
                while not getattr(browser, "_closed_notified", False):
                    if getattr(browser, "_stop_requested", False):
                        break
                    await asyncio.sleep(0.5)
                    ping_counter += 1
                    if ping_counter < 6:
                        continue
                    ping_counter = 0
                    page = getattr(browser, "page", None)
                    if page is None:
                        break
                    try:
                        if getattr(page, "is_closed", None) and page.is_closed():
                            break
                        await page.evaluate("1")
                    except Exception as exc:
                        message = str(exc).lower()
                        transient = any(
                            token in message
                            for token in (
                                "execution context was destroyed",
                                "most likely because of a navigation",
                                "frame was detached",
                                "navigation",
                            )
                        )
                        if transient:
                            continue
                        LOGGER.info("Browser keep-alive ping failed for %s: %s", name, exc)
                        break

                try:
                    await browser.close(force=True)
                except Exception:
                    LOGGER.exception("Failed to close browser for %s", name)

            try:
                loop.run_until_complete(_run_and_keep_alive())
            finally:
                try:
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception:
                    pass
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass
                loop.close()

        threading.Thread(target=worker, daemon=True).start()

    def _proxy_for(self, acc: Dict[str, Any]) -> str:
        scheme = str(acc.get("proxy_scheme") or "socks5").strip() or "socks5"
        host = str(acc.get("proxy_host") or "")
        port = acc.get("proxy_port")
        user = str(acc.get("proxy_user") or "")
        pwd = str(acc.get("proxy_password") or "")
        if not (host and port):
            return ""
        if user and pwd:
            return f"{scheme}://{user}:{pwd}@{host}:{port}"
        return f"{scheme}://{host}:{port}"

    def _on_browser_failed(self, name: str, browser: BrowserInterface, exc: Exception) -> None:
        if self._live_browsers.get(name) is browser:
            self._live_browsers.pop(name, None)
        self._emit_message(f"Cannot start {name}: {exc}")
        self.refresh()

    def _on_browser_closed(self, name: str, browser: BrowserInterface) -> None:
        if self._live_browsers.get(name) is browser:
            self._live_browsers.pop(name, None)
        self._release_proxy(name)
        self._emit_message(f"Browser closed for {name}")
        self.refresh()

    @pyqtSlot(str)
    def stopProfile(self, name: str) -> None:  # noqa: N802
        name = str(name or "").strip()
        browser = self._live_browsers.get(name)
        if browser is None:
            self.refresh()
            return

        # Signal the keep-alive loop to break and close the browser gracefully
        browser._stop_requested = True
        self._emit_message(f"Stopping browser for {name}")
        self.refresh()

    @pyqtSlot(str, str)
    def setStage(self, name: str, stage: str) -> None:  # noqa: N802
        try:
            db_update_account(str(name), {"stage": str(stage or "")})
            self.refresh()
        except Exception as exc:
            self._emit_message(f"Cannot update profile: {exc}")
