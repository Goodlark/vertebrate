// Human Touch publish endpoint. The contribute form POSTs {title, author, body,
// password, image_b64?, image_name?}. If the password matches, this commits the
// column (and image) into the repo and triggers a rebuild — no database.
//
// Netlify env vars required:
//   CONTRIBUTOR_PASSWORD  — the password you choose
//   GH_TOKEN              — a GitHub fine-grained token for this repo (Contents + Actions: write)
//   GH_REPO               — optional, defaults to "Goodlark/vertebrate"

const API = "https://api.github.com";

exports.handler = async (event) => {
  if (event.httpMethod !== "POST") return json(405, { error: "Method not allowed" });

  let data;
  try { data = JSON.parse(event.body || "{}"); } catch { return json(400, { error: "Bad request" }); }
  const { title, author, body, password, image_b64, image_name } = data;

  if (!process.env.CONTRIBUTOR_PASSWORD || !process.env.GH_TOKEN)
    return json(500, { error: "Server not configured (set CONTRIBUTOR_PASSWORD and GH_TOKEN)" });
  if (!password || password !== process.env.CONTRIBUTOR_PASSWORD)
    return json(401, { error: "Wrong password" });
  if (!title || !body) return json(400, { error: "Title and column body are required" });

  const token = process.env.GH_TOKEN;
  const repo = process.env.GH_REPO || "Goodlark/vertebrate";
  const date = new Date().toISOString().slice(0, 10);
  const base = String(title).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 60) || "column";
  const slug = `${date}-${base}`;

  const putFile = (path, contentB64, message) =>
    fetch(`${API}/repos/${repo}/contents/${path}`, {
      method: "PUT",
      headers: ghHeaders(token),
      body: JSON.stringify({ message, content: contentB64, branch: "main" }),
    }).then(async (r) => { if (!r.ok) throw new Error(`${path}: ${r.status} ${await r.text()}`); });

  try {
    let imageField = "";
    if (image_b64 && image_name) {
      const ext = (String(image_name).split(".").pop() || "jpg").toLowerCase().replace(/[^a-z0-9]/g, "") || "jpg";
      await putFile(`content/human-touch/images/${slug}.${ext}`, image_b64, `human-touch image: ${slug}`);
      imageField = `images/${slug}.${ext}`;
    }
    const md =
      `---\ntitle: ${JSON.stringify(title)}\nauthor: ${JSON.stringify(author || "Svitlana Rahimova")}\n` +
      `date: ${date}\nimage: ${imageField}\n---\n${body}\n`;
    await putFile(`content/human-touch/${slug}.md`, Buffer.from(md, "utf-8").toString("base64"), `human-touch: ${title}`);

    // Trigger the render-only rebuild workflow so the column goes live.
    await fetch(`${API}/repos/${repo}/actions/workflows/build.yml/dispatches`, {
      method: "POST", headers: ghHeaders(token), body: JSON.stringify({ ref: "main" }),
    });

    return json(200, { ok: true, slug });
  } catch (e) {
    return json(500, { error: String((e && e.message) || e) });
  }
};

function ghHeaders(token) {
  return { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "Content-Type": "application/json" };
}
function json(statusCode, obj) {
  return { statusCode, headers: { "Content-Type": "application/json" }, body: JSON.stringify(obj) };
}
