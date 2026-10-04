/* CQR browser demo: loads the Python package into Pyodide and drives it from the page. */
"use strict";

const PY_FILES = ["__init__.py", "layout.py", "bch.py", "profiles.py", "ecc.py", "codec.py",
                  "render.py", "palette.py", "decoder.py"];

const GLUE = `
import base64, io, json, time
import numpy as np
from PIL import Image, ImageOps
from cqr import codec, render
from cqr.decoder import decode_all

def encode_png(text, profile, ec, scale, quiet, plain):
    sym = codec.encode(text, ec_level=ec, profile=profile, core_complement=not plain)
    img = render.to_image(sym, module_px=int(scale), quiet=int(quiet))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return json.dumps({"png": base64.b64encode(buf.getvalue()).decode(), "version": sym.version,
                       "size": sym.size, "payload": sym.payload_bytes, "capacity": sym.capacity_bytes,
                       "bpm": sym.profile.bits_per_module, "profile": sym.profile.name, "ec": sym.ec_level})

def decode_file(path, max_side):
    img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if max(img.size) > max_side:
        s = max_side / max(img.size)
        img = img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)
    t = time.time()
    out = []
    for finders, res in decode_all(np.asarray(img), return_report=True):
        r = finders[0]
        item = {"x": round(r.x), "y": round(r.y), "module": round(r.module, 1)}
        if isinstance(res, Exception):
            item.update(ok=False, error=str(res))
        else:
            d = res.result
            item.update(ok=True, version=res.geometry.version, profile=d.profile.name, ec=d.ec_level,
                        corrected=d.corrected_codewords, confidence=round(res.mean_confidence, 2),
                        cores=bool(res.core_complement), nbytes=len(d.data),
                        text=d.data if isinstance(d.data, str) else None,
                        hex=None if isinstance(d.data, str) else d.data.hex())
        out.append(item)
    return json.dumps({"results": out, "seconds": round(time.time() - t, 1), "width": img.width, "height": img.height})
`;

const $ = (id) => document.getElementById(id);
const status = $("status");
let pyodide = null;
let lastPng = null;       // data URL of the last encoded symbol
let pendingFile = null;   // File or Blob chosen for decoding
let stream = null;        // active camera stream

function setStatus(text, cls) {
  status.textContent = text;
  status.className = "status" + (cls ? " " + cls : "");
}

async function init() {
  try {
    pyodide = await loadPyodide();
    setStatus("Loading numpy and Pillow…");
    await pyodide.loadPackage(["numpy", "pillow", "micropip"]);
    setStatus("Installing reedsolo…");
    await pyodide.runPythonAsync("import micropip\nawait micropip.install('reedsolo')");
    setStatus("Loading the CQR package…");
    pyodide.FS.mkdir("/home/pyodide/cqr");
    for (const f of PY_FILES) {
      const r = await fetch("cqr/" + f, { cache: "no-cache" });
      if (!r.ok) throw new Error("could not fetch cqr/" + f);
      pyodide.FS.writeFile("/home/pyodide/cqr/" + f, await r.text());
    }
    await pyodide.runPythonAsync(GLUE);
    setStatus("Ready. Everything runs locally in this tab.", "ready");
    $("encodeBtn").disabled = false;
    updateDecodeButton();
  } catch (e) {
    console.error(e);
    setStatus("Could not start the Python runtime: " + e.message, "error");
  }
}

function encode() {
  const text = $("text").value;
  const btn = $("encodeBtn");
  btn.disabled = true;
  setTimeout(() => {
    try {
      const fn = pyodide.globals.get("encode_png");
      const res = JSON.parse(fn(text, $("profile").value, $("ec").value, $("scale").value, $("quiet").value,
                                $("cores").value === "plain"));
      fn.destroy();
      lastPng = "data:image/png;base64," + res.png;
      $("encOut").innerHTML =
        `<img src="${lastPng}" alt="encoded CQR symbol">` +
        `<div class="caption">Version ${res.version} (${res.size}x${res.size} modules), profile ${res.profile}, ` +
        `${res.bpm} bits/module, EC ${res.ec}: ${res.payload} B used of ${res.capacity} B. ` +
        `<a href="${lastPng}" download="cqr_${res.profile}_v${res.version}.png">Download PNG</a></div>`;
      $("roundtripBtn").disabled = false;
    } catch (e) {
      $("encOut").innerHTML = `<div class="bad">${escapeHtml(pyError(e))}</div>`;
    } finally {
      btn.disabled = false;
    }
  }, 20);
}

async function decodeBlob(blob, label) {
  const btn = $("decodeBtn");
  btn.disabled = true;
  $("decOut").innerHTML = `<div class="caption">Decoding ${escapeHtml(label)}…</div>`;
  await new Promise((r) => setTimeout(r, 30));
  try {
    const buf = new Uint8Array(await blob.arrayBuffer());
    pyodide.FS.writeFile("/tmp/upload.bin", buf);
    const fn = pyodide.globals.get("decode_file");
    const res = JSON.parse(fn("/tmp/upload.bin", parseInt($("maxside").value, 10)));
    fn.destroy();
    renderResults(res);
  } catch (e) {
    $("decOut").innerHTML = `<div class="bad">${escapeHtml(pyError(e))}</div>`;
  } finally {
    btn.disabled = false;
  }
}

function renderResults(res) {
  const n = res.results.length;
  const ok = res.results.filter((r) => r.ok).length;
  let html = `<div class="caption">${n} symbol${n === 1 ? "" : "s"} found in ${res.width}x${res.height} px, ` +
             `${ok} decoded, ${res.seconds} s.</div>`;
  if (n === 0) {
    html += `<div class="result">No finder-pattern triple found. Try a sharper photo, more light, or a larger downscale limit.</div>`;
  }
  for (const r of res.results) {
    html += `<div class="result"><div class="head">`;
    if (r.ok) {
      html += `<span class="ok">decoded</span>` +
              `<span class="chip">V${r.version}</span><span class="chip">${r.profile} / ${r.ec}</span>` +
              `<span class="chip">${r.nbytes} B</span><span class="chip">RS corrected ${r.corrected}</span>` +
              `<span class="chip">confidence ${r.confidence}</span>` +
              `<span class="chip">${r.cores ? "C/M/Y cores" : "plain finders"}</span>` +
              `<span class="chip">${r.module} px/module at (${r.x}, ${r.y})</span></div>`;
      html += `<div class="text">${r.text !== null ? escapeHtml(r.text) : "binary: " + r.hex.slice(0, 400) + (r.hex.length > 400 ? "…" : "")}</div>`;
    } else {
      html += `<span class="bad">failed</span><span class="chip">${r.module} px/module at (${r.x}, ${r.y})</span></div>` +
              `<div class="caption">${escapeHtml(r.error)}</div>`;
    }
    html += `</div>`;
  }
  $("decOut").innerHTML = html;
}

function pyError(e) {
  const s = String(e.message || e);
  const lines = s.trim().split("\n");
  return lines[lines.length - 1];
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function updateDecodeButton() {
  $("decodeBtn").disabled = !(pyodide && pendingFile);
}

function showPreview(blob) {
  const img = $("preview");
  img.src = URL.createObjectURL(blob);
  img.style.display = "block";
}

$("encodeBtn").addEventListener("click", encode);
$("roundtripBtn").addEventListener("click", async () => {
  if (!lastPng) return;
  const blob = await (await fetch(lastPng)).blob();
  pendingFile = blob;
  showPreview(blob);
  updateDecodeButton();
  decodeBlob(blob, "the encoded image");
});
$("file").addEventListener("change", (ev) => {
  const f = ev.target.files && ev.target.files[0];
  if (!f) return;
  pendingFile = f;
  showPreview(f);
  updateDecodeButton();
});
$("decodeBtn").addEventListener("click", () => pendingFile && decodeBlob(pendingFile, pendingFile.name || "image"));
for (const b of document.querySelectorAll("[data-sample]")) {
  b.addEventListener("click", async () => {
    const url = b.dataset.sample;
    b.disabled = true;
    try {
      const blob = await (await fetch(url)).blob();
      pendingFile = blob;
      showPreview(blob);
      updateDecodeButton();
      if (pyodide) decodeBlob(blob, url);
    } finally {
      b.disabled = false;
    }
  });
}

init();


/* ---- camera -------------------------------------------------------------- */
async function startCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    $("decOut").innerHTML = `<div class="bad">This browser does not offer camera access here (it needs HTTPS and a camera). Use the file picker instead.</div>`;
    return;
  }
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 1920 }, height: { ideal: 1440 } },
      audio: false,
    });
  } catch (e) {
    $("decOut").innerHTML = `<div class="bad">Camera not available: ${escapeHtml(e.message || e)}. Use the file picker instead.</div>`;
    return;
  }
  const video = $("video");
  video.srcObject = stream;
  video.style.display = "block";
  $("camHint").style.display = "block";
  $("camBtn").style.display = "none";
  $("captureBtn").style.display = "";
  $("camStopBtn").style.display = "";
  $("preview").style.display = "none";
}

function stopCamera() {
  if (stream) {
    for (const t of stream.getTracks()) t.stop();
    stream = null;
  }
  const video = $("video");
  video.srcObject = null;
  video.style.display = "none";
  $("camHint").style.display = "none";
  $("camBtn").style.display = "";
  $("captureBtn").style.display = "none";
  $("camStopBtn").style.display = "none";
}

async function captureFrame() {
  if (!stream) return null;
  const track = stream.getVideoTracks()[0];
  // Full-resolution still where ImageCapture exists (Android Chrome); video frame otherwise.
  if (window.ImageCapture) {
    try {
      const blob = await new ImageCapture(track).takePhoto();
      if (blob && blob.size > 0) return blob;
    } catch (e) {
      console.warn("takePhoto failed, falling back to a video frame", e);
    }
  }
  const video = $("video");
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext("2d").drawImage(video, 0, 0);
  return new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.95));
}

$("camBtn").addEventListener("click", startCamera);
$("camStopBtn").addEventListener("click", stopCamera);
$("captureBtn").addEventListener("click", async () => {
  if (!pyodide) return;
  $("captureBtn").disabled = true;
  try {
    const blob = await captureFrame();
    if (!blob) return;
    pendingFile = blob;
    updateDecodeButton();
    await decodeBlob(blob, "the camera capture");
  } finally {
    $("captureBtn").disabled = false;
  }
});
document.addEventListener("visibilitychange", () => { if (document.hidden) stopCamera(); });
