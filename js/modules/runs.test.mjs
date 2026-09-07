import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";

async function loadRunsModule() {
  const source = await readFile(new URL("./runs.js", import.meta.url), "utf8");
  const moduleUrl = `data:text/javascript;charset=utf-8,${encodeURIComponent(`${source}\nexport { renderRun, renderRunsShell, captureOpenDetails, restoreOpenDetails };`)}`;
  return import(moduleUrl);
}

test("live run step output keeps full text available in the card", async () => {
  const { renderRun } = await loadRunsModule();
  const longOutput = `prefix ${"context-response ".repeat(30)}suffix`;

  const html = renderRun({
    id: "run-long-output",
    goal: "Render long context response",
    provider: "codex",
    status: "active",
    last_heartbeat: new Date().toISOString(),
    updated: new Date().toISOString(),
    steps: [
      {
        title: "Save context",
        status: "done",
        output: longOutput,
      },
    ],
    context_blob: {},
  });

  assert.match(html, /prefix/);
  assert.match(html, /suffix/);
  assert.ok(
    html.includes(longOutput),
    "full step output should be present, not sliced out of the rendered HTML",
  );
});

test("expanded long output is keyed so polling can restore it", async () => {
  const { renderRun } = await loadRunsModule();

  const html = renderRun({
    id: "run-poll-state",
    goal: "Keep expanded output open",
    provider: "codex",
    status: "active",
    last_heartbeat: new Date().toISOString(),
    updated: new Date().toISOString(),
    steps: [
      {
        title: "Long output",
        status: "done",
        output: `prefix ${"poll ".repeat(60)}suffix`,
      },
    ],
    context_blob: { next: "keep open" },
  });

  assert.match(html, /data-persist-open="run-poll-state:step:0"/);
  assert.match(html, /data-persist-open="run-poll-state:context"/);
});

test("run card shows provider/model when a model is recorded", async () => {
  const { renderRun } = await loadRunsModule();

  const html = renderRun({
    id: "run-provider-model",
    goal: "Show provider model",
    provider: "codex",
    model: "gpt-5.5",
    status: "active",
    last_heartbeat: new Date().toISOString(),
    updated: new Date().toISOString(),
    steps: [],
    context_blob: {},
  });

  assert.match(html, /codex\/gpt-5\.5/);
});

test("open details survive a polling render cycle", async () => {
  const { captureOpenDetails, restoreOpenDetails } = await loadRunsModule();
  const details = [
    { dataset: { persistOpen: "run:step:0" }, open: true },
    { dataset: { persistOpen: "run:step:1" }, open: false },
    { dataset: { persistOpen: "run:context" }, open: true },
  ];
  const root = {
    querySelectorAll(selector) {
      if (selector === "details[data-persist-open][open]") return details.filter(detail => detail.open);
      if (selector === "details[data-persist-open]") return details;
      throw new Error(`unexpected selector ${selector}`);
    },
  };

  const openKeys = captureOpenDetails(root);
  details.forEach(detail => { detail.open = false; });
  restoreOpenDetails(root, openKeys);

  assert.deepEqual(details.map(detail => detail.open), [true, false, true]);
});

test("runs shell includes clickable total and hidden previous-run list", async () => {
  const { renderRunsShell } = await loadRunsModule();
  const active = [{
    id: "active-run",
    goal: "Active run",
    provider: "codex",
    status: "active",
    last_heartbeat: new Date().toISOString(),
    updated: new Date().toISOString(),
    steps: [],
    context_blob: {},
  }];
  const previous = [{
    id: "completed-run",
    goal: "Completed run",
    provider: "codex",
    status: "completed",
    last_heartbeat: new Date().toISOString(),
    updated: new Date().toISOString(),
    steps: [],
    context_blob: {},
  }];

  const html = renderRunsShell({
    active,
    finished: previous,
    previous,
    counts: { total: 2, active: 1, previous: 1 },
    showAllRuns: false,
  });

  assert.match(html, /data-act="toggle-all-runs"/);
  assert.match(html, /aria-expanded="false"/);
  assert.match(html, /<strong>2<\/strong> total/);
  assert.doesNotMatch(html, /All previous runs/);

  const expanded = renderRunsShell({
    active,
    finished: previous,
    previous,
    counts: { total: 2, active: 1, previous: 1 },
    showAllRuns: true,
  });

  assert.match(expanded, /aria-expanded="true"/);
  assert.match(expanded, /All previous runs/);
  assert.match(expanded, /Completed run/);
});
