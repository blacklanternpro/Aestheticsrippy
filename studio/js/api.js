// Calls to the local studio server (server.py).

async function json(res) {
  let body = null;
  try { body = await res.json(); } catch { /* not JSON */ }
  if (!res.ok || (body && body.status === "error")) {
    throw new Error((body && body.error) || `${res.status} ${res.statusText}`);
  }
  return body;
}

export async function ripPacks() {
  return (await json(await fetch("/api/rip-packs"))).packs;
}

export async function contentFiles() {
  return (await json(await fetch("/api/content"))).files;
}

export async function contentFile(name) {
  return (await json(await fetch(`/api/content/${encodeURIComponent(name)}`))).data;
}

export async function saveContentFile(name, data) {
  return json(await fetch(`/api/content/${encodeURIComponent(name)}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ data }),
  }));
}

/** Render the document to PDF on the server; returns { blob, pages, overflow }. */
export async function exportPdf(doc) {
  const res = await fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      pack: doc.pack, variant: doc.variant, data: doc.data, styles: doc.styles,
      tokens: doc.tokens, assets: doc.assets || {}, source: doc.source,
    }),
  });
  if (!res.ok) await json(res);
  return {
    blob: await res.blob(),
    pages: +(res.headers.get("X-Rip-Pages") || 0),
    overflow: (res.headers.get("X-Rip-Overflow") || "").split(",").filter(Boolean),
  };
}
