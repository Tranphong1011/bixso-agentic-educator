function showToast(type, message) {
  const wrap = document.getElementById("toastWrap");
  const div = document.createElement("div");
  div.className = "toast " + type;
  div.textContent = message;
  wrap.appendChild(div);
  setTimeout(() => div.remove(), 3600);
}

function setOutput(data) {
  document.getElementById("out").textContent = JSON.stringify(data, null, 2);
}

function currentUserId() {
  return document.getElementById("userId").value.trim();
}

function headers(includeJson) {
  const h = { "X-User-Id": currentUserId() };
  if (includeJson) h["Content-Type"] = "application/json";
  return h;
}

function setLoading(buttonId, loading) {
  const btn = document.getElementById(buttonId);
  if (!btn) return;
  btn.disabled = loading;
  btn.dataset.prev = btn.dataset.prev || btn.textContent;
  btn.textContent = loading ? "Processing..." : btn.dataset.prev;
}

async function requestJson(url, options, buttonId, preserveOutput) {
  if (!currentUserId()) {
    const message = "Please provide User ID first.";
    showToast("error", message);
    throw new Error(message);
  }
  setLoading(buttonId, true);
  try {
    const res = await fetch(url, options);
    const data = await res.json();
    if (!preserveOutput) setOutput(data);
    if (!res.ok) {
      const detail = data && data.detail ? data.detail : "Request failed";
      showToast("error", "Failed: " + detail);
      throw new Error(detail);
    }
    showToast("success", "Success: " + url);
    return data;
  } finally {
    setLoading(buttonId, false);
  }
}

function updateWalletBadge(tokens) {
  const badge = document.getElementById("walletBadge");
  const state = document.getElementById("walletState");
  badge.textContent = "Tokens: " + tokens;
  state.className = "badge";
  if (tokens >= 30) {
    state.classList.add("ok");
    state.textContent = "Healthy";
  } else if (tokens >= 10) {
    state.classList.add("warn");
    state.textContent = "Low";
  } else {
    state.classList.add("err");
    state.textContent = "Insufficient";
  }
}

async function getWallet() {
  const data = await requestJson("/api/wallet", { headers: headers(false) }, "btnWallet", false);
  if (typeof data.tokens_remaining === "number") updateWalletBadge(data.tokens_remaining);
}

async function refreshWalletBadgeOnly() {
  const res = await fetch("/api/wallet", { headers: headers(false) });
  const data = await res.json();
  if (res.ok && typeof data.tokens_remaining === "number") {
    updateWalletBadge(data.tokens_remaining);
  }
}

async function getLastTransaction() {
  await requestJson("/api/transactions/last", { headers: headers(false) }, "btnLastTx");
}

async function getCourses() {
  await requestJson("/api/courses/enrolled", { headers: headers(false) }, "btnCourses");
}

async function uploadDoc() {
  const f = document.getElementById("file").files[0];
  if (!f) {
    showToast("error", "Please choose a PDF/TXT file.");
    return;
  }
  const form = new FormData();
  form.append("file", f);
  await requestJson(
    "/api/documents/upload",
    { method: "POST", headers: headers(false), body: form },
    "btnUpload",
    false
  );
  await refreshWalletBadgeOnly();
}

async function askAgent() {
  const question = document.getElementById("question").value.trim();
  if (!question) {
    showToast("error", "Question cannot be empty.");
    return;
  }
  const fileName = document.getElementById("fileName").value;
  const payload = { question: question, file_name: fileName || null };
  await requestJson(
    "/api/agent/ask",
    {
      method: "POST",
      headers: headers(true),
      body: JSON.stringify(payload),
    },
    "btnAsk",
    false
  );
  await refreshWalletBadgeOnly();
}

window.getWallet = getWallet;
window.getLastTransaction = getLastTransaction;
window.getCourses = getCourses;
window.uploadDoc = uploadDoc;
window.askAgent = askAgent;

showToast("info", "Dashboard ready. Enter user ID to start.");
