"""Proxy pools bridge for QML."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from PyQt6.QtCore import QObject, pyqtProperty, pyqtSignal, pyqtSlot

from app.storage.db import db_get_setting, db_set_setting
from app.ui.bridge.models import DictListModel


class ProxiesBridge(QObject):
    modelChanged = pyqtSignal()
    statsChanged = pyqtSignal()
    message = pyqtSignal(str)

    def __init__(self, app_state=None, parent=None) -> None:
        super().__init__(parent)
        self._app_state = app_state
        self._model = DictListModel(["pool", "name", "location", "address", "type", "latency", "status", "accent", "index", "selected"], parent=self)
        self._pools_model = DictListModel(["name", "total", "used", "selected"], parent=self)
        self._selected_pool = ""
        self._selected: set[tuple[str, int]] = set()
        self._active = 0
        self._checking = 0
        self._failed = 0
        self._locations = 0
        if app_state is not None:
            app_state.refreshRequested.connect(self.refresh)
        self.refresh()

    @pyqtProperty(QObject, constant=True)
    def model(self) -> QObject:
        return self._model

    @pyqtProperty(QObject, constant=True)
    def poolsModel(self) -> QObject:  # noqa: N802
        return self._pools_model

    @pyqtProperty(str, notify=modelChanged)
    def selectedPool(self) -> str:  # noqa: N802
        return self._selected_pool

    @pyqtProperty(int, notify=statsChanged)
    def active(self) -> int:
        return self._active

    @pyqtProperty(int, notify=statsChanged)
    def checking(self) -> int:
        return self._checking

    @pyqtProperty(int, notify=statsChanged)
    def failed(self) -> int:
        return self._failed

    @pyqtProperty(int, notify=statsChanged)
    def locations(self) -> int:
        return self._locations

    def _load(self) -> Dict[str, Dict[str, Any]]:
        try:
            data = json.loads(db_get_setting("proxy_pools") or "{}")
            data = data if isinstance(data, dict) else {}
            # Ensure the "All" pool always exists
            if "All" not in data:
                data["All"] = {"proxies": []}
            return data
        except Exception:
            return {"All": {"proxies": []}}

    def _save(self, pools: Dict[str, Dict[str, Any]]) -> None:
        db_set_setting("proxy_pools", json.dumps(pools, ensure_ascii=False))

    def _emit_message(self, text: str) -> None:
        self.message.emit(text)
        if self._app_state is not None:
            self._app_state.notify(text)

    @pyqtSlot()
    def refresh(self) -> None:
        pools = self._load()
        pool_rows: List[Dict[str, Any]] = []
        total_all = 0
        used_all = 0
        for pool_name, pool in sorted(pools.items()):
            proxies = pool.get("proxies", []) if isinstance(pool, dict) else []
            total = len(proxies)
            used = sum(1 for item in proxies if isinstance(item, dict) and item.get("assigned_to"))
            total_all += total
            used_all += used
            pool_rows.append({"name": pool_name, "total": total, "used": used, "selected": self._selected_pool == pool_name})
        self._pools_model.set_rows(pool_rows)
        rows: List[Dict[str, Any]] = []
        active = checking = failed = 0
        locations = set()
        for pool_name, pool in sorted(pools.items()):
            if self._selected_pool and pool_name != self._selected_pool:
                continue
            for pool_index, entry in enumerate(pool.get("proxies", []) if isinstance(pool, dict) else []):
                value = entry.get("value") if isinstance(entry, dict) else str(entry)
                value = str(value or "").strip()
                if not value:
                    continue
                check = entry.get("last_check") if isinstance(entry, dict) else {}
                status_raw = str(check.get("status") or "active").lower() if isinstance(check, dict) else "active"
                status = "Active" if status_raw in {"ok", "active"} else "Checking" if status_raw == "checking" else "Failed"
                if status == "Active":
                    active += 1
                elif status == "Checking":
                    checking += 1
                else:
                    failed += 1
                country = str(check.get("country") or "") if isinstance(check, dict) else ""
                city = str(check.get("city") or "") if isinstance(check, dict) else ""
                location = ", ".join(p for p in [city, country] if p) or pool_name
                locations.add(location)
                type_label = "SOCKS5" if "socks" in value.lower() else "HTTP"
                latency = check.get("ms") if isinstance(check, dict) else None
                rows.append({
                    "pool": pool_name,
                    "name": str(entry.get("name") or f"{pool_name}-{pool_index + 1:02d}") if isinstance(entry, dict) else f"{pool_name}-{pool_index + 1:02d}",
                    "location": location,
                    "address": value,
                    "type": type_label,
                    "latency": f"{latency}ms" if isinstance(latency, int) else "?",
                    "status": status,
                    "accent": "#06b6d4" if status == "Active" else "#f59e0b" if status == "Checking" else "#ef4444",
                    "index": pool_index,
                    "selected": (pool_name, pool_index) in self._selected,
                })
        self._active, self._checking, self._failed, self._locations = active, checking, failed, len(locations)
        self._model.set_rows(rows)
        self.modelChanged.emit()
        self.statsChanged.emit()

    @pyqtSlot(str)
    def selectPool(self, name: str) -> None:  # noqa: N802
        name = str(name or "")
        self._selected_pool = name
        self._selected.clear()
        self.refresh()


    @pyqtSlot(str)
    def createPool(self, name: str) -> None:  # noqa: N802
        name = str(name or "").strip()
        if not name:
            self._emit_message("Pool name is empty")
            return
        if name == "All":
            self._emit_message("Cannot create a pool named 'All' (reserved)")
            return
        pools = self._load()
        if name in pools:
            self._emit_message("Proxy pool already exists")
            return
        pools[name] = {"proxies": []}
        self._selected_pool = name
        self._save(pools)
        self._emit_message(f"Proxy pool {name} created")
        self.refresh()

    @pyqtSlot(str)
    def renameSelectedPool(self, name: str) -> None:  # noqa: N802
        old_name = self._selected_pool
        new_name = str(name or "").strip()
        if not old_name:
            self._emit_message("Select proxy pool first")
            return
        if old_name == "All":
            self._emit_message("Cannot rename the 'All' pool")
            return
        if not new_name or new_name == old_name:
            return
        pools = self._load()
        if old_name not in pools:
            self._emit_message("Selected proxy pool not found")
            return
        if new_name in pools:
            self._emit_message("Proxy pool already exists")
            return
        pools[new_name] = pools.pop(old_name)
        self._selected_pool = new_name
        self._save(pools)
        self._emit_message(f"Proxy pool renamed to {new_name}")
        self.refresh()

    @pyqtSlot()
    def deleteSelectedPool(self) -> None:  # noqa: N802
        name = self._selected_pool
        if not name:
            self._emit_message("Select proxy pool first")
            return
        if name == "All":
            self._emit_message("Cannot delete the 'All' pool")
            return
        pools = self._load()
        if name not in pools:
            return
        pools.pop(name, None)
        self._selected_pool = ""
        self._save(pools)
        self._emit_message(f"Proxy pool {name} deleted")
        self.refresh()

    @pyqtSlot(str)
    def addProxies(self, values: str) -> None:  # noqa: N802
        lines = [line.strip() for line in str(values or "").replace("\r", "\n").split("\n") if line.strip()]
        if not lines:
            self._emit_message("Proxy list is empty")
            return
        pools = self._load()
        pool_name = self._selected_pool or "All"
        pool = pools.setdefault(pool_name, {"proxies": []})
        proxies = pool.setdefault("proxies", [])
        existing = {str(item.get("value") or "") for item in proxies if isinstance(item, dict)}
        added = 0
        for value in lines:
            if value in existing:
                continue
            proxies.append({"value": value, "assigned_to": ""})
            existing.add(value)
            added += 1
        self._selected_pool = pool_name
        self._save(pools)
        self._emit_message(f"Added {added} proxies to {pool_name}")
        self.refresh()

    @pyqtSlot(str)
    def addProxy(self, value: str) -> None:  # noqa: N802
        value = str(value or "").strip()
        if not value:
            self._emit_message("Proxy value is empty")
            return
        pools = self._load()
        pool_name = self._selected_pool or "All"
        self._save(pools)
        self._emit_message("Proxy added")
        self.refresh()

    @pyqtSlot(str, int, result="QVariant")
    def getProxy(self, pool_name: str, index: int) -> Dict[str, Any]:  # noqa: N802
        pool_name = str(pool_name or "").strip()
        try:
            index = int(index)
        except Exception:
            return {}
        pool = self._load().get(pool_name)
        if not isinstance(pool, dict):
            return {}
        proxies = pool.get("proxies", [])
        if not (0 <= index < len(proxies)) or not isinstance(proxies[index], dict):
            return {}
        entry = proxies[index]
        return {
            "pool": pool_name,
            "index": index,
            "name": str(entry.get("name") or ""),
            "value": str(entry.get("value") or ""),
            "assigned_to": str(entry.get("assigned_to") or ""),
        }

    @pyqtSlot(str, int, str, str)
    def saveProxy(self, pool_name: str, index: int, name: str, value: str) -> None:  # noqa: N802
        pool_name = str(pool_name or "").strip()
        value = str(value or "").strip()
        if not value:
            self._emit_message("Proxy value is empty")
            return
        try:
            index = int(index)
        except Exception:
            self._emit_message("Proxy not found")
            return
        pools = self._load()
        pool = pools.get(pool_name)
        if not isinstance(pool, dict):
            self._emit_message("Proxy pool not found")
            return
        proxies = pool.get("proxies", [])
        if not (0 <= index < len(proxies)) or not isinstance(proxies[index], dict):
            self._emit_message("Proxy not found")
            return
        proxies[index]["name"] = str(name or "").strip()
        proxies[index]["value"] = value
        self._save(pools)
        self._emit_message("Proxy saved")
        self.refresh()

    @pyqtSlot(str, int)
    def deleteProxy(self, pool_name: str, index: int) -> None:  # noqa: N802
        pool_name = str(pool_name or "").strip()
        try:
            index = int(index)
        except Exception:
            return
        pools = self._load()
        pool = pools.get(pool_name)
        proxies = pool.get("proxies", []) if isinstance(pool, dict) else []
        if not (0 <= index < len(proxies)):
            return
        proxies.pop(index)
        self._selected = {
            (p, i if p != pool_name or i < index else i - 1)
            for p, i in self._selected
            if not (p == pool_name and i == index)
        }
        self._save(pools)
        self._emit_message("Proxy deleted")
        self.refresh()

    @pyqtSlot(str, int, bool)
    def setProxySelected(self, pool_name: str, index: int, selected: bool) -> None:  # noqa: N802
        key = (str(pool_name or "").strip(), int(index))
        if selected:
            self._selected.add(key)
        else:
            self._selected.discard(key)
        self.refresh()

    @pyqtSlot()
    def clearSelection(self) -> None:  # noqa: N802
        self._selected.clear()
        self.refresh()

    @pyqtSlot()
    def releaseSelected(self) -> None:  # noqa: N802
        if not self._selected:
            self._emit_message("No selected proxies")
            return
        pools = self._load()
        released = 0
        assigned_names: set[str] = set()
        for pool_name, index in list(self._selected):
            proxies = pools.get(pool_name, {}).get("proxies", []) if isinstance(pools.get(pool_name), dict) else []
            if 0 <= index < len(proxies) and isinstance(proxies[index], dict):
                assigned = str(proxies[index].get("assigned_to") or "").strip()
                if assigned:
                    assigned_names.add(assigned)
                proxies[index]["assigned_to"] = ""
                released += 1
        self._save(pools)
        if assigned_names:
            try:
                from app.storage.db import db_get_accounts, db_update_account

                for acc in db_get_accounts():
                    name = str(acc.get("name") or "")
                    if name in assigned_names:
                        db_update_account(name, {
                            "proxy_host": "",
                            "proxy_port": None,
                            "proxy_user": "",
                            "proxy_password": "",
                            "proxy_scheme": "",
                            "proxy_pool": "",
                        })
            except Exception:
                pass
        self._emit_message(f"Released {released} proxy(s)")
        self.refresh()

    @pyqtSlot()
    def removeSelected(self) -> None:  # noqa: N802
        if not self._selected:
            self._emit_message("No selected proxies")
            return
        pools = self._load()
        removed = 0
        for pool_name in sorted({pool for pool, _ in self._selected}):
            pool = pools.get(pool_name)
            proxies = pool.get("proxies", []) if isinstance(pool, dict) else []
            indices = sorted([idx for pool, idx in self._selected if pool == pool_name], reverse=True)
            for index in indices:
                if 0 <= index < len(proxies):
                    proxies.pop(index)
                    removed += 1
        self._selected.clear()
        self._save(pools)
        self._emit_message(f"Removed {removed} proxy(s)")
        self.refresh()

    @pyqtSlot()
    def selectAll(self) -> None:  # noqa: N802
        pools = self._load()
        self._selected.clear()
        for pool_name, pool in pools.items():
            if not isinstance(pool, dict):
                continue
            for index in range(len(pool.get("proxies", []))):
                self._selected.add((pool_name, index))
        self.refresh()

    @pyqtSlot()
    def deselectAll(self) -> None:  # noqa: N802
        self.clearSelection()

    @pyqtSlot()
    def removeAll(self) -> None:  # noqa: N802
        pools = self._load()
        for pool in pools.values():
            if isinstance(pool, dict):
                pool["proxies"] = []
        self._selected.clear()
        self._save(pools)
        self._emit_message("Removed all proxies")
        self.refresh()

    @pyqtSlot()
    def cleanDerivedPools(self) -> None:
        """Remove all derived pools (both marked and orphan duplicates)."""
        pools = self._load()

        # Collect source pool values
        source_names = set()
        source_values = set()
        for pn, pool in pools.items():
            if not isinstance(pool, dict):
                continue
            if pool.get("_derived_mode"):
                continue
            source_names.add(pn)
            for entry in pool.get("proxies", []):
                if isinstance(entry, dict):
                    val = str(entry.get("value") or "").strip()
                    if val:
                        source_values.add(val)

        # Find pools to remove: marked derived + orphan duplicates
        to_remove = []
        for pn, pool in pools.items():
            if not isinstance(pool, dict):
                continue
            if pn in source_names:
                continue
            if pool.get("_derived_mode"):
                to_remove.append(pn)
                continue
            # Orphan detection
            proxy_list = pool.get("proxies", [])
            if not proxy_list:
                continue
            pool_values = {str(e.get("value") or "").strip() for e in proxy_list if isinstance(e, dict)}
            if pool_values and pool_values.issubset(source_values):
                to_remove.append(pn)

        for pn in to_remove:
            pools.pop(pn, None)

        if to_remove:
            self._save(pools)
            self._emit_message(f"Cleaned {len(to_remove)} derived group(s)")
        else:
            self._emit_message("No derived groups to clean")
        self.refresh()


    @pyqtSlot(str, int)
    def checkProxy(self, pool_name: str, index: int) -> None:  # noqa: N802
        pool_name = str(pool_name or "").strip()
        index = int(index)
        pools = self._load()
        pool = pools.get(pool_name)
        if not isinstance(pool, dict):
            self._emit_message("Proxy pool not found")
            return
        proxies = pool.get("proxies", [])
        if not (0 <= index < len(proxies)) or not isinstance(proxies[index], dict):
            self._emit_message("Proxy not found")
            return
        proxies[index]["last_check"] = {"status": "checking"}
        self._save(pools)
        self.refresh()

        def worker() -> None:
            try:
                from app.ui.main_window.proxy_mixin import ProxyPoolMixin
                data = self._load()
                entry = data.get(pool_name, {}).get("proxies", [])[index]
                ok, ms, err, meta = ProxyPoolMixin._probe_proxy_endpoint_value(str(entry.get("value") or ""), timeout_s=5.0)
                result = dict(meta or {})
                result["status"] = "ok" if ok else "fail"
                result["ms"] = ms
                if err:
                    result["error"] = err
                entry["last_check"] = result
                self._save(data)
                self._emit_message("Proxy check finished")
            except Exception as exc:
                self._emit_message(f"Proxy check failed: {exc}")
            finally:
                self.refresh()

        threading.Thread(target=worker, daemon=True).start()

    @pyqtSlot()
    def checkAll(self) -> None:  # noqa: N802
        pools = self._load()
        # Collect all proxy locations across pools
        tasks: List[tuple[str, str, int]] = []  # (pool_name, proxy_key, index)
        for pool_name, pool in pools.items():
            if not isinstance(pool, dict):
                continue
            for idx, entry in enumerate(pool.get("proxies", [])):
                if isinstance(entry, dict):
                    entry["last_check"] = {"status": "checking"}
                    value = str(entry.get("value") or "").strip()
                    if value:
                        tasks.append((pool_name, value, idx))
        self._save(pools)
        self.refresh()
        self._emit_message(f"Checking {len(tasks)} proxies...")

        if not tasks:
            self._emit_message("No proxies to check")
            return

        self._check_token = getattr(self, "_check_token", 0) + 1
        token = self._check_token

        def worker() -> None:
            from app.ui.main_window.proxy_mixin import ProxyPoolMixin

            total = len(tasks)
            done = 0
            ok_count = 0
            fail_count = 0
            last_ui_update = 0.0

            def probe(value: str):
                try:
                    return ProxyPoolMixin._probe_proxy_endpoint_value(value, timeout_s=5.0)
                except Exception as exc:
                    return False, None, str(exc), {}

            max_workers = min(12, max(1, total))
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                future_map = {ex.submit(probe, value): (pool_name, idx) for pool_name, value, idx in tasks}

                pending_results: List[tuple] = []  # (pool_name, idx, result_dict)
                flush_threshold = max(1, max_workers)  # batch writes

                for fut in as_completed(future_map):
                    if getattr(self, "_check_token", 0) != token:
                        return  # newer check started, abort
                    pool_name, idx = future_map[fut]
                    try:
                        ok, ms, err, meta = fut.result()
                    except Exception as exc:
                        ok, ms, err, meta = False, None, str(exc), {}

                    result = dict(meta or {})
                    result["status"] = "ok" if ok else "fail"
                    result["ms"] = ms
                    if err:
                        result["error"] = err
                    pending_results.append((pool_name, idx, result))

                    done += 1
                    if ok:
                        ok_count += 1
                    else:
                        fail_count += 1

                    # Batch-write results to avoid concurrent PermissionError
                    now_perf = time.perf_counter()
                    should_flush = len(pending_results) >= flush_threshold or (now_perf - last_ui_update) >= 0.2 or done == total
                    if should_flush and pending_results:
                        data = self._load()
                        for pn, idx2, res in pending_results:
                            pool = data.get(pn)
                            if isinstance(pool, dict):
                                proxies = pool.get("proxies", [])
                                if 0 <= idx2 < len(proxies) and isinstance(proxies[idx2], dict):
                                    proxies[idx2]["last_check"] = res
                        self._save(data)
                        pending_results.clear()
                        last_ui_update = now_perf
                        self.refresh()
                        if done < total:
                            self._emit_message(f"Checking... {done}/{total}")
                        else:
                            self._emit_message(f"Check finished: {ok_count} OK, {fail_count} failed")

            # Final refresh
            self.refresh()

        threading.Thread(target=worker, daemon=True).start()

    @pyqtSlot(str)
    def autoUpsertGroup(self, mode: str) -> None:  # noqa: N802
        """Check selected pool's proxies (or all pools) and copy them into derived groups.

        mode == "location": group by "City, CC" (fall back to "Unknown")
        mode == "schema":   group by lowercase scheme (http, socks5, ...)
        """
        mode = str(mode or "").strip().lower()
        if mode not in {"location", "schema"}:
            self._emit_message("Invalid upsert mode")
            return

        pools = self._load()
        pool_name = self._selected_pool  # may be "" for all pools

        # Collect tasks: (pool_name, idx, value) across selected pool or all pools
        tasks: List[tuple[str, int, str]] = []
        for pn, pool in pools.items():
            if not isinstance(pool, dict):
                continue
            if pool.get("_derived_mode"):  # skip derived pools
                continue
            if pool_name and pn != pool_name:
                continue
            for idx, entry in enumerate(pool.get("proxies", [])):
                if isinstance(entry, dict):
                    entry["last_check"] = {"status": "checking"}
                    value = str(entry.get("value") or "").strip()
                    if value:
                        tasks.append((pn, idx, value))

        if not tasks:
            self._emit_message("No proxies to check")
            return

        self._save(pools)
        self.refresh()
        self._emit_message(f"Auto-upsert: checking {len(tasks)} proxies...")

        self._upsert_token = getattr(self, "_upsert_token", 0) + 1
        token = self._upsert_token

        def worker() -> None:
            try:
                from urllib.parse import urlparse
                from app.ui.main_window.proxy_mixin import ProxyPoolMixin

                total = len(tasks)
                done = 0
                ok_count = 0
                last_ui = 0.0

                def probe(value: str):
                    try:
                        return ProxyPoolMixin._probe_proxy_endpoint_value(value, timeout_s=5.0)
                    except Exception as exc:
                        return False, None, str(exc), {}

                max_workers = min(12, max(1, total))
                with ThreadPoolExecutor(max_workers=max_workers) as ex:
                    future_map = {ex.submit(probe, value): (pn, idx) for pn, idx, value in tasks}

                    pending_results: List[tuple] = []
                    flush_threshold = max(1, max_workers)

                    for fut in as_completed(future_map):
                        if getattr(self, "_upsert_token", 0) != token:
                            return
                        pn, idx = future_map[fut]
                        try:
                            ok, ms, err, meta = fut.result()
                        except Exception as exc:
                            ok, ms, err, meta = False, None, str(exc), {}

                        result = dict(meta or {})
                        result["status"] = "ok" if ok else "fail"
                        result["ms"] = ms
                        if err:
                            result["error"] = err
                        pending_results.append((pn, idx, result))

                        done += 1
                        if ok:
                            ok_count += 1
                        now_perf = time.perf_counter()
                        should_flush = len(pending_results) >= flush_threshold or (now_perf - last_ui) >= 0.2 or done == total
                        if should_flush and pending_results:
                            data = self._load()
                            for pn2, idx2, res in pending_results:
                                p = data.get(pn2)
                                if isinstance(p, dict):
                                    plist = p.get("proxies", [])
                                    if 0 <= idx2 < len(plist) and isinstance(plist[idx2], dict):
                                        plist[idx2]["last_check"] = res
                            self._save(data)
                            pending_results.clear()
                            last_ui = now_perf
                            self.refresh()
                            if done < total:
                                self._emit_message(f"Auto-upsert: {done}/{total}")
                            else:
                                self._emit_message(f"Auto-upsert check done: {ok_count} OK")

                if getattr(self, "_upsert_token", 0) != token:
                    return

                # Build derived groups from checked results
                from urllib.parse import urlparse as _urlparse

                data = self._load()

                # Identify source pools (non-derived) and collect their proxy values
                source_pool_names = set()
                all_source_values = set()
                for pn, pool in data.items():
                    if not isinstance(pool, dict):
                        continue
                    if pool.get("_derived_mode"):
                        continue
                    source_pool_names.add(pn)
                    for entry in pool.get("proxies", []):
                        if isinstance(entry, dict):
                            val = str(entry.get("value") or "").strip()
                            if val:
                                all_source_values.add(val)

                # Detect orphan derived pools: pools not in source_pool_names whose
                # ALL proxy values are duplicates of source pool values
                orphan_names = []
                for pn, pool in data.items():
                    if not isinstance(pool, dict):
                        continue
                    if pn in source_pool_names:
                        continue
                    if pool.get("_derived_mode"):
                        continue  # will be handled by normal cleanup
                    proxy_list = pool.get("proxies", [])
                    if not proxy_list:
                        continue
                    pool_values = {str(e.get("value") or "").strip() for e in proxy_list if isinstance(e, dict)}
                    # If every value in this pool exists in source values, it's an orphan derived pool
                    if pool_values and pool_values.issubset(all_source_values):
                        orphan_names.append(pn)

                # Remove orphans and ALL derived pools (any mode), not just current mode.
                # Otherwise upsert location then schema would keep location-derived pools inflating count.
                to_remove = orphan_names + [
                    pn for pn, pool in data.items()
                    if isinstance(pool, dict) and pool.get("_derived_mode")
                ]
                for pn in to_remove:
                    data.pop(pn, None)

                groups: Dict[str, List[Dict[str, Any]]] = {}

                for pn, pool in data.items():
                    if not isinstance(pool, dict):
                        continue
                    if pool.get("_derived_mode"):  # skip ALL derived pools (any mode)
                        continue
                    if pool_name and pn != pool_name:
                        continue
                    for entry in pool.get("proxies", []):
                        if not isinstance(entry, dict):
                            continue
                        value = str(entry.get("value") or "").strip()
                        if not value:
                            continue
                        check = entry.get("last_check") if isinstance(entry.get("last_check"), dict) else {}
                        if mode == "location":
                            city = str(check.get("city") or "").strip()
                            cc = str(check.get("country") or check.get("country_code") or "").strip()
                            if city and cc:
                                group_name = f"{city}, {cc}"
                            elif cc:
                                group_name = cc
                            else:
                                group_name = "Unknown"
                        else:
                            parsed = _urlparse(value)
                            scheme = (parsed.scheme or "unknown").lower()
                            group_name = scheme
                        groups.setdefault(group_name, []).append({"value": value, "assigned_to": ""})

                added_total = 0
                for group_name, entries in groups.items():
                    target_pool = data.setdefault(group_name, {"proxies": [], "_derived_mode": mode})
                    existing_values = {str(p.get("value") or "") for p in target_pool.get("proxies", []) if isinstance(p, dict)}
                    added = 0
                    for entry in entries:
                        if entry["value"] in existing_values:
                            continue
                        target_pool.setdefault("proxies", []).append(entry)
                        existing_values.add(entry["value"])
                        added += 1
                    added_total += added

                self._save(data)
                self._emit_message(f"Auto-upsert: created/updated {len(groups)} groups, {added_total} proxies copied")
                self.refresh()
            except Exception as exc:
                self._emit_message(f"Auto-upsert error: {exc}")

        threading.Thread(target=worker, daemon=True).start()
