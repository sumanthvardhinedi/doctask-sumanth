import { FormEvent, useEffect, useState } from "react";
import {
  AgentWorkflow,
  Finding,
  PackageDetail,
  PackageSummary,
  SuperDocsReview,
  api,
} from "./api";

export default function App() {
  const [packages, setPackages] = useState<PackageSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string>("");
  const [detail, setDetail] = useState<PackageDetail | null>(null);
  const [runId, setRunId] = useState<string>("");
  const [findings, setFindings] = useState<Finding[]>([]);
  const [workflow, setWorkflow] = useState<AgentWorkflow | null>(null);
  const [reviews, setReviews] = useState<Record<string, SuperDocsReview>>({});
  const [error, setError] = useState<string>("");
  const [busy, setBusy] = useState<string>("");

  const [pkgName, setPkgName] = useState("Demo filing");
  const [authority, setAuthority] = useState("authority_a");
  const [filename, setFilename] = useState("cover_letter.pdf");
  const [contentType, setContentType] = useState("application/pdf");
  const [fileSize, setFileSize] = useState("1024");
  const [storagePath, setStoragePath] = useState("cover_letter.pdf");
  const [sortOrder, setSortOrder] = useState("1");
  const [notes, setNotes] = useState<Record<string, string>>({});

  async function withError<T>(label: string, work: () => Promise<T>): Promise<T | undefined> {
    setBusy(label);
    setError("");
    try {
      return await work();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return undefined;
    } finally {
      setBusy("");
    }
  }

  async function refreshPackages(preferId?: string) {
    const items = await api.listPackages();
    setPackages(items);
    const nextId = preferId || selectedId || items[0]?.id || "";
    if (nextId) {
      setSelectedId(nextId);
    }
  }

  async function loadPackage(packageId: string) {
    if (!packageId) {
      setDetail(null);
      setFindings([]);
      setWorkflow(null);
      setRunId("");
      return;
    }
    const pkg = await api.getPackage(packageId);
    setDetail(pkg);
    try {
      const flow = await api.getWorkflow(packageId);
      setWorkflow(flow);
      if (flow.validation_run_id) {
        setRunId(flow.validation_run_id);
        setFindings(await api.listFindings(packageId, flow.validation_run_id));
      } else {
        setFindings([]);
      }
    } catch {
      setWorkflow(null);
      setFindings([]);
      setRunId("");
    }
  }

  useEffect(() => {
    void withError("load", () => refreshPackages());
  }, []);

  useEffect(() => {
    if (selectedId) {
      void withError("package", () => loadPackage(selectedId));
    }
  }, [selectedId]);

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    const created = await withError("create", () =>
      api.createPackage(authority, pkgName),
    );
    if (created) {
      await refreshPackages(created.id);
    }
  }

  async function onAddDocument(event: FormEvent) {
    event.preventDefault();
    if (!selectedId) {
      return;
    }
    await withError("document", () =>
      api.addDocument(selectedId, {
        filename,
        content_type: contentType,
        file_size_bytes: Number(fileSize),
        storage_path: storagePath,
        sort_order: Number(sortOrder),
      }),
    );
    await loadPackage(selectedId);
  }

  async function onValidate() {
    if (!selectedId) {
      return;
    }
    const run = await withError("validate", () => api.validate(selectedId));
    if (run) {
      setRunId(run.id);
      await loadPackage(selectedId);
    }
  }

  async function onDecide(finding: Finding, approved: boolean) {
    if (!selectedId || !runId) {
      return;
    }
    await withError("decide", () =>
      api.decideFinding(
        selectedId,
        runId,
        finding.id,
        approved,
        notes[finding.id] ?? "",
      ),
    );
    await loadPackage(selectedId);
  }

  async function onSuperDocs(finding: Finding, action: "start" | "approve" | "reject" | "export") {
    if (!selectedId || !runId) {
      return;
    }
    const existing = reviews[finding.id];
    const result = await withError("superdocs", async () => {
      if (action === "start") {
        return api.startSuperDocs(selectedId, runId, finding.id);
      }
      if (!existing) {
        throw new Error("Start SuperDocs review before decide/export.");
      }
      if (action === "export") {
        return api.exportSuperDocs(selectedId, existing.id);
      }
      return api.decideSuperDocs(
        selectedId,
        existing.id,
        action === "approve",
        notes[finding.id] ?? "",
      );
    });
    if (result) {
      setReviews((current) => ({ ...current, [finding.id]: result }));
      await loadPackage(selectedId);
    }
  }

  return (
    <div className="page">
      <header>
        <div>
          <p className="eyebrow">SuperDocs assigned build</p>
          <h1>Pre-submission filing validator</h1>
        </div>
        <p className="lede">
          Optional review UI. The workflow is still machine-driven over REST/MCP.
          Document bytes are not parsed here; metadata is sent as data, not
          instructions. Token/cost fields stay unused unless a stage recorded them.
        </p>
      </header>

      {error ? <div className="banner error">{error}</div> : null}
      {busy ? <div className="banner">{busy}…</div> : null}

      <div className="grid">
        <section>
          <h2>Package</h2>
          <form className="stack" onSubmit={onCreate}>
            <label>
              Authority
              <select
                value={authority}
                onChange={(event) => setAuthority(event.target.value)}
              >
                <option value="authority_a">authority_a</option>
                <option value="authority_b">authority_b</option>
              </select>
            </label>
            <label>
              Name
              <input
                value={pkgName}
                onChange={(event) => setPkgName(event.target.value)}
                required
              />
            </label>
            <button type="submit">Create package</button>
          </form>

          <label>
            Open package
            <select
              value={selectedId}
              onChange={(event) => setSelectedId(event.target.value)}
            >
              <option value="">Select…</option>
              {packages.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} · {item.authority_code} · {item.status}
                </option>
              ))}
            </select>
          </label>

          {detail ? (
            <p className="meta">
              {detail.id}
              <br />
              {detail.document_count} document(s) · {detail.status}
            </p>
          ) : null}

          <h3>Documents (metadata only)</h3>
          <form className="stack" onSubmit={onAddDocument}>
            <input
              value={filename}
              onChange={(event) => setFilename(event.target.value)}
              placeholder="filename"
              required
            />
            <input
              value={contentType}
              onChange={(event) => setContentType(event.target.value)}
              placeholder="content type"
              required
            />
            <input
              value={fileSize}
              onChange={(event) => setFileSize(event.target.value)}
              placeholder="size bytes"
              required
            />
            <input
              value={storagePath}
              onChange={(event) => setStoragePath(event.target.value)}
              placeholder="storage path under UPLOADS_ROOT"
              required
            />
            <input
              value={sortOrder}
              onChange={(event) => setSortOrder(event.target.value)}
              placeholder="sort order"
              required
            />
            <button type="submit" disabled={!selectedId}>
              Add document
            </button>
          </form>
          <ul className="docs">
            {detail?.documents.map((doc) => (
              <li key={doc.id}>
                {doc.sort_order}. {doc.filename} ({doc.content_type},{" "}
                {doc.file_size_bytes ?? "unknown"} bytes)
              </li>
            ))}
          </ul>
          <button type="button" onClick={() => void onValidate()} disabled={!selectedId}>
            Validate / resume
          </button>
        </section>

        <section>
          <h2>Agent stages</h2>
          {workflow ? (
            <div className="meta">
              status {workflow.status}
              {workflow.current_stage ? ` · ${workflow.current_stage}` : ""}
              {workflow.total_duration_ms != null
                ? ` · total ${workflow.total_duration_ms} ms`
                : workflow.elapsed_ms != null
                  ? ` · elapsed ${workflow.elapsed_ms} ms`
                  : ""}
              <br />
              tokens {workflow.token_count ?? "null"} · cost{" "}
              {workflow.estimated_cost ?? "null"} · retries {workflow.retry_count}
            </div>
          ) : (
            <p className="meta">No workflow until you validate.</p>
          )}
          <ol className="stages">
            {workflow?.stages.map((stage) => (
              <li key={stage.stage}>
                <strong>{stage.stage}</strong> · {stage.status}
                {stage.duration_ms != null ? ` · ${stage.duration_ms} ms` : ""}
                {stage.error ? ` · ${stage.error}` : ""}
              </li>
            ))}
          </ol>
        </section>
      </div>

      <section>
        <h2>Findings (decide one at a time)</h2>
        {findings.length === 0 ? (
          <p className="meta">No findings loaded.</p>
        ) : (
          <div className="findings">
            {findings.map((finding) => (
              <article key={finding.id} className={`finding ${finding.result}`}>
                <header>
                  <code>{finding.rule_id}</code>
                  <span>{finding.result}</span>
                  <span>{finding.is_hard_rejection ? "hard" : "discretionary"}</span>
                </header>
                <p>{finding.explanation}</p>
                <p className="meta">
                  {finding.location || "no location"} · {finding.evidence || "no evidence"}
                </p>
                {finding.approved == null ? (
                  <>
                    <textarea
                      placeholder="Reviewer notes"
                      value={notes[finding.id] ?? ""}
                      onChange={(event) =>
                        setNotes((current) => ({
                          ...current,
                          [finding.id]: event.target.value,
                        }))
                      }
                    />
                    <div className="row">
                      <button type="button" onClick={() => void onDecide(finding, true)}>
                        Approve
                      </button>
                      <button
                        type="button"
                        className="danger"
                        onClick={() => void onDecide(finding, false)}
                      >
                        Reject
                      </button>
                    </div>
                  </>
                ) : (
                  <p className="meta">
                    Decision: {finding.approved ? "approved" : "rejected"}
                    {finding.reviewer_notes ? ` · ${finding.reviewer_notes}` : ""}
                  </p>
                )}
                {finding.approved === true && finding.package_document_id ? (
                  <div className="row">
                    <button
                      type="button"
                      onClick={() => void onSuperDocs(finding, "start")}
                    >
                      SuperDocs start
                    </button>
                    <button
                      type="button"
                      onClick={() => void onSuperDocs(finding, "approve")}
                    >
                      SuperDocs approve
                    </button>
                    <button
                      type="button"
                      className="danger"
                      onClick={() => void onSuperDocs(finding, "reject")}
                    >
                      SuperDocs reject
                    </button>
                    <button
                      type="button"
                      onClick={() => void onSuperDocs(finding, "export")}
                    >
                      Export
                    </button>
                    {reviews[finding.id] ? (
                      <span className="meta">{reviews[finding.id].status}</span>
                    ) : null}
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
