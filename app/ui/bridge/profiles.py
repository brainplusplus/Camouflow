"""Profiles bridge for QML."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from PyQt6.QtCore import QObject, QTimer, pyqtProperty, pyqtSignal, pyqtSlot

from app.core.browser_interface import BrowserInterface
from app.storage.db import (
    db_add_account,
    db_delete_account,
    db_get_accounts,
    db_get_setting,
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

    def __init__(self, app_state=None, parent=None) -> None:
        super().__init__(parent)
        self._model = DictListModel([
            "name", "id", "browser", "proxy", "lastActive", "status", "stage", "tags", "running"
        ], parent=self)
        self._stages_model = DictListModel(["name", "count", "selected"], parent=self)
        self._selected_stage = ""
        self._live_browsers: Dict[str, BrowserInterface] = {}
        self._app_state = app_state
        if app_state is not None:
            app_state.refreshRequested.connect(self.refresh)
        self.refresh()

    @pyqtProperty(QObject, constant=True)
    def model(self) -> QObject:
        return self._model

    @pyqtProperty(QObject, constant=True)
    def stagesModel(self) -> QObject:  # noqa: N802
        return self._stages_model

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

    def _emit_message(self, text: str) -> None:
        self.message.emit(text)
        if self._app_state is not None:
            self._app_state.notify(text)

    def _proxy_label(self, acc: Dict[str, Any]) -> str:
        host = str(acc.get("proxy_host") or "")
        port = acc.get("proxy_port")
        if host and port:
            return f"{host}:{port}"
        return str(acc.get("proxy_pool") or "None")

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
        stage_counts: Dict[str, int] = {}
        for acc in accounts:
            stage_counts[str(acc.get("stage") or "No tag")] = stage_counts.get(str(acc.get("stage") or "No tag"), 0) + 1
        try:
            configured_stages = json.loads(db_get_setting("stages_json") or "[]")
        except Exception:
            configured_stages = []
        for stage in configured_stages if isinstance(configured_stages, list) else []:
            clean_stage = str(stage or "").strip()
            if clean_stage:
                stage_counts.setdefault(clean_stage, 0)
        self._stages_model.set_rows(
            [{"name": "All tags", "count": len(accounts), "selected": not self._selected_stage}]
            + [
                {"name": stage, "count": count, "selected": self._selected_stage == stage}
                for stage, count in sorted(stage_counts.items(), key=lambda item: item[0].lower())
            ]
        )
        sorted_accounts = sorted(accounts, key=lambda a: (str(a.get("stage") or "No tag").lower(), str(a.get("name") or "").lower()))
        for index, acc in enumerate(sorted_accounts, start=1):
            name = str(acc.get("name") or f"profile{index}")
            stage = str(acc.get("stage") or "")
            stage_label = stage or "No tag"
            if self._selected_stage and self._selected_stage != stage_label:
                continue
            running = name in self._live_browsers
            tags = []
            if stage:
                tags.append(stage)
            for key in ("tag", "type"):
                val = str(acc.get(key) or "")
                if val and val not in tags:
                    tags.append(val)
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
                "stage": stage or "No tag",
                "tags": "  ".join(f"#{tag}" for tag in tags) if tags else "#profile",
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
                QTimer.singleShot(0, lambda: self._emit_message(f"Cookies saved for {target}"))
            except Exception as exc:
                LOGGER.exception("Cannot save cookies for %s", target)
                QTimer.singleShot(0, lambda exc=exc: self._emit_message(f"Cannot save cookies: {exc}"))
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
        proxy = self._proxy_for(acc)
        engine = str(acc.get("_browser_engine") or acc.get("browser_engine") or "camoufox")
        settings = self._settings_dict(acc.get("cloakbrowser_settings") if engine == "cloakbrowser" else acc.get("camoufox_settings"))
        browser = BrowserInterface(
            profile_name=name,
            proxy=proxy,
            keep_browser_open=True,
            browser_engine=engine,
            browser_settings=settings,
        )
        browser.add_close_callback(lambda: QTimer.singleShot(0, lambda: self._on_browser_closed(name, browser)))
        self._live_browsers[name] = browser
        self._emit_message(f"Starting browser for {name}")
        self.refresh()

        def worker() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(browser.start())
            except Exception as exc:
                LOGGER.exception("Browser start failed for %s", name)
                QTimer.singleShot(0, lambda exc=exc: self._on_browser_failed(name, browser, exc))
            finally:
                try:
                    loop.close()
                except Exception:
                    pass

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
        self._emit_message(f"Browser closed for {name}")
        self.refresh()

    @pyqtSlot(str)
    def stopProfile(self, name: str) -> None:  # noqa: N802
        name = str(name or "").strip()
        browser = self._live_browsers.pop(name, None)
        if browser is None:
            self.refresh()
            return

        def worker() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(browser.close(force=True))
            except Exception:
                LOGGER.exception("Browser stop failed for %s", name)
            finally:
                loop.close()
                QTimer.singleShot(0, self.refresh)

        threading.Thread(target=worker, daemon=True).start()
        self._emit_message(f"Stopping browser for {name}")
        self.refresh()

    @pyqtSlot(str, str)
    def setStage(self, name: str, stage: str) -> None:  # noqa: N802
        try:
            db_update_account(str(name), {"stage": str(stage or "")})
            self.refresh()
        except Exception as exc:
            self._emit_message(f"Cannot update profile: {exc}")
