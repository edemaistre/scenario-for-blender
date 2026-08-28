# SPDX-FileCopyrightText: 2026 Scenario Inc.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Threaded job manager. Workers never touch bpy; results flow through a queue
that the Blender pump drains on the main thread."""
import datetime as dt
import logging
import queue
import threading
import time
from dataclasses import dataclass

from .. import config
from ..api import assets as assets_api
from ..api import generate as generate_api
from ..api import jobs as jobs_api
from ..api.errors import NetworkError, ScenarioError
from .records import JobRecord

log = logging.getLogger("scenario.jobs")


@dataclass
class EstimateResult:
    key: str
    cu_cost: float = None
    error: str = None


class JobManager:
    def __init__(self, client_factory, registry, paths, *, poll_interval=2.5, sleep=time.sleep,
                 downloader=assets_api.download_file, uploader=None):
        self.client_factory = client_factory
        self.registry = registry
        self.paths = paths
        self.poll_interval = poll_interval
        self.sleep = sleep
        self.downloader = downloader
        self.uploader = uploader or assets_api.upload_file
        self.events = queue.Queue()
        self._threads = []
        self._stop = threading.Event()
        self.resume_pending = []

    # -- public API (main thread) -----------------------------------------
    def submit(self, lane, kind, model_id, body, files=None, array_params=(), meta=None, prepare=None):
        """Queue a generation. `prepare(client, rec)`, when given, runs first on the worker (no bpy) and may rewrite
        `rec.body`: the render lanes use it to ask Prompt Spark for the look before the job is submitted."""
        client = self.client_factory()  # resolved on the calling (main) thread; workers never touch bpy
        rec = JobRecord.new(lane=lane, kind=kind, model_id=model_id, body=body, meta=meta)
        if prepare is not None:
            rec.status = "preparing"
        self.registry.add(rec)
        self.registry.save()
        self._spawn(self._run_job, client, rec, dict(files or {}), set(array_params), prepare)
        return rec

    def estimate(self, key, model_id, body):
        self._spawn(self._run_estimate, self.client_factory(), key, model_id, dict(body))

    def fetch_catalog(self, catalog, privacy="public", model_ids=()):
        self._spawn(self._run_catalog, catalog, privacy, tuple(model_ids))

    def fetch_models(self, catalog, model_ids):
        """Fetch detailed records for a few models without re-fetching the list."""
        self._spawn(self._run_models, catalog, tuple(model_ids))

    def track(self, rec, client=None):
        """Poll a job that is already submitted (resume, import from Generations)."""
        self._spawn(self._poll_job, client or self.client_factory(), rec)

    def resume(self, records=None):
        pending = []
        for rec in (records if records is not None else self.registry.active()):
            if rec.job_id:
                pending.append(rec)
            else:
                rec.status, rec.error = "failed", "Blender closed before the job was submitted"
        self.registry.save()
        self.resume_pending = []
        if not pending:
            return
        try:
            client = self.client_factory()
        except ScenarioError as err:
            self.resume_pending = pending  # retried by the pump once credentials are valid
            self.events.put(("error", err.reason))
            return
        for rec in pending:
            self._spawn(self._poll_job, client, rec)

    def retry_resume(self):
        if self.resume_pending:
            self.resume(list(self.resume_pending))

    def drain(self):
        out = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out

    def has_active(self):
        return any(t.is_alive() for t in self._threads)

    def join(self, timeout=None):
        deadline = None if timeout is None else time.time() + timeout
        for t in list(self._threads):
            remaining = None if deadline is None else max(0.0, deadline - time.time())
            t.join(remaining)
        self._threads = [t for t in self._threads if t.is_alive()]

    def shutdown(self):
        self._stop.set()

    # -- workers ------------------------------------------------------------
    def _spawn(self, target, *args):
        thread = threading.Thread(target=self._guard, args=(target,) + args, daemon=True, name=f"scenario-{target.__name__}")
        self._threads.append(thread)
        thread.start()
        return thread

    def _guard(self, target, *args):
        try:
            target(*args)
        except Exception as err:  # never let a worker die silently
            log.exception("worker %s failed", target.__name__)
            self.events.put(("error", str(err)))

    def _run_job(self, client, rec, files, array_params, prepare=None):
        if prepare is not None:
            try:
                prepare(client, rec)
            except Exception as err:  # Prompt Spark or any pre-step failing must fail the job visibly, not the worker
                self._fail(rec, f"preparation failed: {getattr(err, 'reason', err)}")
                return
            rec.status = "submitting"
            self.events.put(("job", rec))
        try:
            for param_name, paths in files.items():
                ids = [self.uploader(client, p) for p in paths]
                if not ids:
                    continue
                rec.body[param_name] = ids if param_name in array_params else ids[0]
            job = generate_api.submit(client, rec.model_id, rec.body)
        except ScenarioError as err:
            self._fail(rec, str(err))
            return
        rec.job_id = job.get("jobId")
        self._update_from_job(rec, job)
        self.events.put(("job", rec))
        self._poll_job(client, rec)

    def _poll_job(self, client, rec):
        while not self._stop.is_set():
            self.sleep(self.poll_interval)
            try:
                job = jobs_api.get_job(client, rec.job_id)
            except ScenarioError as err:
                if err.status in (401, 403, 404):
                    self._fail(rec, str(err))
                    return
                self.events.put(("error", f"poll {rec.job_id}: {err}"))
                continue
            self._update_from_job(rec, job)
            if not rec.is_terminal:
                self.events.put(("job", rec))
                continue
            if rec.is_success:
                try:
                    self._download_results(client, rec)
                except (ScenarioError, OSError) as err:
                    # the cloud job succeeded and the credits are spent: keep the assets reachable from Generations
                    rec.files = []
                    rec.status = "failed"
                    rec.error = f"download failed ({err}); the result is on Scenario, use Generations to import it again"
                    rec.updated_at = time.time()
                    self.registry.save()
                    self.events.put(("job_failed", rec))
                    return
                self.registry.save()
                self.events.put(("job_done", rec))
            else:
                self._fail(rec, jobs_api.error_text(job) or rec.status)
            return

    MESH_MIMES = ("model/gltf-binary", "model/gltf+json", "model/x-fbx", "model/obj")

    def _download_results(self, client, rec):
        """Fetch every asset record, then download meshes first. For 3D jobs a failed alternate or texture
        download is recorded, not fatal, as long as one mesh arrived (providers ship 200+ MB OBJ variants)."""
        now = dt.datetime.now()
        out_dir = self.paths.output_for(rec.kind, now)
        out_dir.mkdir(parents=True, exist_ok=True)
        records = []
        for index, asset_id in enumerate(rec.asset_ids):
            asset = assets_api.get_asset(client, asset_id)
            rec.asset_types[asset_id] = assets_api.asset_type(asset)
            records.append((index, asset_id, asset))
        if rec.kind == "3d":
            records.sort(key=lambda item: (0 if (item[2].get("mimeType") or "") in self.MESH_MIMES else 1, item[0]))
        errors = {}
        for index, asset_id, asset in records:
            ext = config.ext_for_mime(asset.get("mimeType"))
            dest = out_dir / config.output_filename(rec.kind, rec.model_id, rec.job_id, index, ext, when=now, asset_id=asset_id)
            url = asset.get("url")
            if not url:
                errors[asset_id] = "no url"
                continue
            try:
                self.downloader(url, dest)
            except (ScenarioError, OSError) as err:
                errors[asset_id] = str(err)
                continue
            rec.files.append(str(dest))
        if errors:
            rec.meta["download_errors"] = errors
        has_mesh = any(f.lower().endswith((".glb", ".gltf", ".fbx", ".obj")) for f in rec.files)
        if errors and not (rec.kind == "3d" and has_mesh):
            raise ScenarioError(0, "; ".join(list(errors.values())[:2]))

    def _update_from_job(self, rec, job):
        rec.status = (job.get("status") or rec.status).lower()
        rec.progress = jobs_api.progress(job)
        cost = jobs_api.cu_cost(job)
        if cost is not None:
            rec.cu_cost = cost
        ids = jobs_api.asset_ids(job)
        if ids:
            rec.asset_ids = ids
        rec.updated_at = time.time()
        self.registry.save()

    def _fail(self, rec, message):
        if not rec.is_terminal or rec.status == "submitting":
            rec.status = "failed"
        rec.error = message
        rec.updated_at = time.time()
        self.registry.save()
        self.events.put(("job_failed", rec))

    def _run_estimate(self, client, key, model_id, body):
        try:
            est = generate_api.estimate(client, model_id, body)
            self.events.put(("estimate", EstimateResult(key=key, cu_cost=est.cu_cost)))
        except ScenarioError as err:
            self.events.put(("estimate", EstimateResult(key=key, error=err.reason)))

    def _run_catalog(self, catalog, privacy, model_ids):
        try:
            records = catalog.fetch_list(privacy=privacy)
        except (ScenarioError, OSError) as err:
            self.events.put(("catalog_failed", str(getattr(err, "reason", err))))
            return
        detailed = []
        for model_id in model_ids:
            try:
                detailed.append(catalog.get(model_id))
            except (ScenarioError, OSError) as err:
                log.warning("model %s: %s", model_id, err)
        self.events.put(("catalog", {"privacy": privacy, "records": records, "detailed": detailed}))

    def _run_models(self, catalog, model_ids):
        detailed, failed = [], {}
        for model_id in model_ids:
            try:
                detailed.append(catalog.get(model_id, refresh=True))
            except (ScenarioError, OSError) as err:
                failed[model_id] = str(getattr(err, "reason", err))
        self.events.put(("models", {"detailed": detailed, "failed": failed}))
