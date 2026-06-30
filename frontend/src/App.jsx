import React, { useState } from "react";

const API_BASE = "http://localhost:8000";

const App = () => {
  const [recruiterPath, setRecruiterPath] = useState("");
  const [atsPath, setAtsPath] = useState("");
  const [resumePath, setResumePath] = useState("");
  const [githubFixturePath, setGithubFixturePath] = useState("");
  const [githubUsername, setGithubUsername] = useState("caroldev");

  const [configJson, setConfigJson] = useState(
    JSON.stringify(
      {
        fields: [
          { path: "full_name", type: "string", required: true },
          {
            path: "primary_email",
            from: "emails[0]",
            type: "string",
            required: true,
          },
          { path: "skills", from: "skills[].name", type: "string[]" },
        ],
        include_provenance: false,
        include_confidence: true,
        on_missing: "null",
      },
      null,
      2,
    ),
  );

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [candidateIds, setCandidateIds] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [projection, setProjection] = useState("");

  const buildSourcesPayload = () => {
    const sources = [];
    if (recruiterPath.trim()) {
      sources.push({ type: "recruiter_csv", path: recruiterPath.trim() });
    }
    if (atsPath.trim()) {
      sources.push({ type: "ats_json", path: atsPath.trim() });
    }
    if (githubFixturePath.trim()) {
      sources.push({
        type: "github_fixture",
        path: githubFixturePath.trim(),
        username: githubUsername.trim() || undefined,
      });
    }
    if (resumePath.trim()) {
      sources.push({ type: "resume", path: resumePath.trim() });
    }
    return sources;
  };

  const uploadFile = async (sourceType, file, setPath) => {
    if (!file) return;
    setError("");
    setLoading(true);
    try {
      const form = new FormData();
      form.append("file", file);
      const resp = await fetch(`${API_BASE}/uploads/${sourceType}`, {
        method: "POST",
        body: form,
      });
      if (!resp.ok) {
        const detail = await resp.text();
        throw new Error(
          `Upload failed (${resp.status}): ${detail || "Unknown error"}`,
        );
      }
      const data = await resp.json();
      setPath(data.path || "");
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  const ingestAndProject = async () => {
    setError("");
    setProjection("");
    setLoading(true);
    try {
      const sources = buildSourcesPayload();
      if (sources.length === 0) {
        throw new Error("Please provide at least one source file.");
      }

      let parsedConfig;
      try {
        parsedConfig = JSON.parse(configJson);
      } catch (e) {
        throw new Error("Config JSON is not valid JSON.");
      }

      const ingestResp = await fetch(`${API_BASE}/candidates/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sources }),
      });
      if (!ingestResp.ok) {
        const detail = await ingestResp.text();
        throw new Error(
          `Ingest failed (${ingestResp.status}): ${detail || "Unknown error"}`,
        );
      }
      const ingestData = await ingestResp.json();
      const ids = ingestData.candidate_ids || [];
      setCandidateIds(ids);
      if (ids.length === 0) {
        setSelectedId(null);
        setProjection("// No candidates produced from these sources.");
        return;
      }

      const id = ids[0];
      setSelectedId(id);

      const projectResp = await fetch(
        `${API_BASE}/candidates/${id}/project`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ config: parsedConfig }),
        },
      );
      if (!projectResp.ok) {
        const detail = await projectResp.text();
        throw new Error(
          `Project failed (${projectResp.status}): ${detail || "Unknown error"}`,
        );
      }
      const proj = await projectResp.json();
      setProjection(JSON.stringify(proj, null, 2));
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  const reprojectForId = async (id) => {
    setError("");
    setLoading(true);
    try {
      let parsedConfig;
      try {
        parsedConfig = JSON.parse(configJson);
      } catch (e) {
        throw new Error("Config JSON is not valid JSON.");
      }
      const resp = await fetch(`${API_BASE}/candidates/${id}/project`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config: parsedConfig }),
      });
      if (!resp.ok) {
        const detail = await resp.text();
        throw new Error(
          `Project failed (${resp.status}): ${detail || "Unknown error"}`,
        );
      }
      const proj = await resp.json();
      setProjection(JSON.stringify(proj, null, 2));
      setSelectedId(id);
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-root">
      <div className="app-shell">
        <header className="app-header">
          <div className="app-title-block">
            <div className="badge-row">
              <span className="badge">
                <span className="badge-dot" />
                <span>Multi-source pipeline</span>
              </span>
              <span className="badge">
                <span>FastAPI · React · Postgres</span>
              </span>
            </div>
            <h1 className="app-title">Candidate data projection console</h1>
            <p className="app-subtitle">
              Upload heterogeneous candidate sources, resolve them into a
              canonical profile, and shape the JSON output with a runtime
              config.
            </p>
          </div>
          <div className="app-meta">
            <div>
              <strong>1</strong> run =&nbsp;ingest → merge → project
            </div>
            <div>Safe to retry, config-driven output.</div>
          </div>
        </header>

        {error && <div className="error-box">{error}</div>}

        <section className="layout-grid">
          <div>
            <div className="card">
              <div className="card-title-row">
                <h2 className="card-title">Source uploads</h2>
                <span className="card-caption">
                  CSV · JSON · GitHub fixture · resume
                </span>
              </div>

              <div className="form-field">
                <label className="form-label">
                  <span>Recruiter CSV</span>
                  <span>required for the demo</span>
                </label>
                <input
                  className="file-input"
                  type="file"
                  accept=".csv"
                  onChange={(e) =>
                    uploadFile(
                      "recruiter_csv",
                      e.target.files && e.target.files[0],
                      setRecruiterPath,
                    )
                  }
                />
                {recruiterPath && (
                  <div className="upload-path">Uploaded to: {recruiterPath}</div>
                )}
              </div>

              <div className="form-field">
                <label className="form-label">
                  <span>ATS JSON</span>
                  <span>structured fields</span>
                </label>
                <input
                  className="file-input"
                  type="file"
                  accept=".json"
                  onChange={(e) =>
                    uploadFile(
                      "ats_json",
                      e.target.files && e.target.files[0],
                      setAtsPath,
                    )
                  }
                />
                {atsPath && (
                  <div className="upload-path">Uploaded to: {atsPath}</div>
                )}
              </div>

              <div className="form-field">
                <label className="form-label">
                  <span>GitHub fixture JSON</span>
                  <span>skills + activity</span>
                </label>
                <input
                  className="file-input"
                  type="file"
                  accept=".json"
                  onChange={(e) =>
                    uploadFile(
                      "github_fixture",
                      e.target.files && e.target.files[0],
                      setGithubFixturePath,
                    )
                  }
                />
                {githubFixturePath && (
                  <div className="upload-path">
                    Uploaded to: {githubFixturePath}
                  </div>
                )}
              </div>

              <div className="form-field">
                <label className="form-label">
                  <span>GitHub username (for fixture)</span>
                  <span>used in provenance</span>
                </label>
                <input
                  className="text-input"
                  type="text"
                  value={githubUsername}
                  onChange={(e) => setGithubUsername(e.target.value)}
                />
              </div>

              <div className="form-field">
                <label className="form-label">
                  <span>Resume (PDF/DOCX/TXT, optional)</span>
                  <span>parsed via Groq if configured</span>
                </label>
                <input
                  className="file-input"
                  type="file"
                  accept=".pdf,.doc,.docx,.txt"
                  onChange={(e) =>
                    uploadFile(
                      "resume",
                      e.target.files && e.target.files[0],
                      setResumePath,
                    )
                  }
                />
                {resumePath && (
                  <div className="upload-path">Uploaded to: {resumePath}</div>
                )}
              </div>
              <p className="helper-text">
                All uploads are stored under `backend/uploads/...` and then
                passed into the same ingestion pipeline the CLI uses.
              </p>
            </div>
          </div>

          <div>
            <div className="card">
              <div className="card-title-row">
                <h2 className="card-title">Projection config (JSON)</h2>
                <span className="card-caption">shape the output per consumer</span>
              </div>
              <textarea
                className="config-textarea"
                value={configJson}
                onChange={(e) => setConfigJson(e.target.value)}
              />
              <p className="helper-text">
                Example: `primary_email` is read from `emails[0]`,
                `skills` from `skills[].name`. The same canonical profile can be
                re-projected with any compatible config.
              </p>
            </div>
          </div>
        </section>

        <button
          type="button"
          onClick={ingestAndProject}
          disabled={loading}
          className="primary-button"
        >
          {loading ? (
            <>
              <span className="primary-button-loader" />
              <span className="primary-button-label">
                <span>Running pipeline…</span>
                <span>ingest → resolve → project</span>
              </span>
            </>
          ) : (
            <span className="primary-button-label">
              <span>Run ingest + project</span>
              <span>safe to run repeatedly with new configs</span>
            </span>
          )}
        </button>

        {candidateIds.length > 0 && (
          <section style={{ marginBottom: "0.9rem" }}>
            <h2 className="section-heading">Candidates produced</h2>
            <div className="candidate-list">
              {candidateIds.map((id) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => reprojectForId(id)}
                  className={`candidate-pill${
                    selectedId === id ? " candidate-pill--active" : ""
                  }`}
                  title={id}
                >
                  {id}
                </button>
              ))}
            </div>
          </section>
        )}

        <section className="output-section">
          <div className="output-header-row">
            <h2 className="section-heading">Projected JSON</h2>
            <span className="output-hint">
              Canonical profile × projection config → caller view
            </span>
          </div>
          <pre className="output-pre">
            {projection || "// Run ingest + project to see output here."}
          </pre>
        </section>
      </div>
    </div>
  );
};

export default App;

