const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? "").replace(/[&<>"']/g, char => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
}[char]));

function inlineMarkdown(value) {
  const links = [];
  let source = String(value ?? "").replace(/\[([^\]\n]+)\]\((https:\/\/[^\s)]+)\)/g,
    (_, label, url) => {
      const index = links.push({label, url}) - 1;
      return `@@SHOPFLOW_LINK_${index}@@`;
    });
  source = esc(source)
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`\n]+)`/g, "<code>$1</code>");
  return source.replace(/@@SHOPFLOW_LINK_(\d+)@@/g, (_, index) => {
    const link = links[Number(index)];
    return '<a href="' + esc(link.url) + '" target="_blank" rel="noopener">' +
      esc(link.label) + '<span aria-hidden="true"> ↗</span></a>';
  });
}

function markdown(value) {
  const lines = String(value ?? "").replace(/\r/g, "").split("\n");
  const output = [];
  const cells = line => line.trim().replace(/^\|/, "").replace(/\|$/, "")
    .split("|").map(cell => cell.trim());
  const isDivider = line => /^\s*\|?\s*:?-{3,}/.test(line) && line.includes("|");
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) { index += 1; continue; }
    if (line.includes("|") && index + 1 < lines.length && isDivider(lines[index + 1])) {
      const head = cells(line);
      index += 2;
      const rows = [];
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        rows.push(cells(lines[index])); index += 1;
      }
      output.push('<div class="message-table"><table><thead><tr>' +
        head.map(cell => '<th>' + inlineMarkdown(cell) + '</th>').join("") +
        '</tr></thead><tbody>' + rows.map(row => '<tr>' +
          head.map((_, cellIndex) => '<td>' + inlineMarkdown(row[cellIndex] || "") + '</td>').join("") +
        '</tr>').join("") + '</tbody></table></div>');
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*[-*]\s+/, "")); index += 1;
      }
      output.push('<ul>' + items.map(item => '<li>' + inlineMarkdown(item) + '</li>').join("") + '</ul>');
      continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items = [];
      while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\s*\d+[.)]\s+/, "")); index += 1;
      }
      output.push('<ol>' + items.map(item => '<li>' + inlineMarkdown(item) + '</li>').join("") + '</ol>');
      continue;
    }
    const heading = line.match(/^\s*(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = Math.min(heading[1].length + 2, 5);
      output.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`); index += 1; continue;
    }
    const paragraph = [line]; index += 1;
    while (index < lines.length && lines[index].trim() &&
      !/^\s*(?:[-*]\s+|\d+[.)]\s+|#{1,3}\s+)/.test(lines[index]) &&
      !(lines[index].includes("|") && index + 1 < lines.length && isDivider(lines[index + 1]))) {
      paragraph.push(lines[index]); index += 1;
    }
    output.push('<p>' + paragraph.map(inlineMarkdown).join("<br>") + '</p>');
  }
  return output.join("");
}

let boot;
let task = null;
let catalog = {demo: [], real: []};
let busy = false;
let cart = null;
let replaceId = null;
let deleteTargetId = null;

const statusLabels = {
  "新的采购任务": "New list",
  "规划中": "Planning",
  "待确认": "Ready to review",
  "已确认，尚未购买": "Confirmed",
  "已准备购买入口": "Links ready",
  "用户标记已购买": "Marked purchased",
  "已完成演练": "Demo complete"
};
const kindLabels = {
  fixture: "Demo item",
  verified: "Verified",
  external: "Web result",
  shopify_test: "Test store"
};
const money = (value, currency = task?.currency || "CNY") =>
  value === null || value === undefined
    ? "Unknown"
    : new Intl.NumberFormat("en-US", {style: "currency", currency}).format(value / 100);
const labelStatus = value => statusLabels[value] || value || "Not recorded";

function notice(message) {
  $("#notice").textContent = message;
  $("#notice").hidden = false;
  setTimeout(() => $("#notice").hidden = true, 7000);
}

async function api(path, payload) {
  const response = await fetch(path, {
    method: payload ? "POST" : "GET",
    headers: payload ? {"Content-Type": "application/json", "X-CSRF-Token": boot.csrf} : {},
    body: payload ? JSON.stringify(payload) : undefined
  });
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || "The request could not be completed.");
    error.status = response.status;
    throw error;
  }
  return data;
}

function saveLocal(nextTask) {
  task = nextTask;
  localStorage.setItem("task", nextTask.id);
  const index = boot.tasks.findIndex(item => item.id === nextTask.id);
  if (index >= 0) boot.tasks[index] = nextTask;
  else boot.tasks.unshift(nextTask);
}

function requestBody(extra = {}) {
  if (!task) throw new Error("Create a list first.");
  return {task_id: task.id, revision: task.revision, ...extra};
}

async function create(scope = "real", currency = "CNY") {
  saveLocal(await api("/api/tasks", {scope, currency}));
  cart = null;
  render();
}

function historyList() {
  if (!boot.tasks.length) return '<p class="muted">Your saved lists will appear here.</p>';
  return boot.tasks.map(item =>
    '<button class="history-item ' + (task?.id === item.id ? "selected" : "") +
    '" data-action="history" data-id="' + esc(item.id) + '">' +
    esc(item.title === "新的采购任务" ? "New list" : item.title) +
    '<small>' + esc(item.scope === "demo" ? "Demo" : "Live") + ' · ' +
    esc(labelStatus(item.status)) + '</small></button>'
  ).join("");
}

function productImage(snapshot) {
  const product = snapshot.product;
  if (product.image) {
    return '<div class="product-image"><img src="' + esc(product.image) + '" alt="' +
      esc(product.name) + '" loading="lazy"></div>';
  }
  return '<div class="product-image">' + esc(product.category) + '<small>No image</small></div>';
}

function productCard(item) {
  const snapshot = item.snapshot;
  const offer = snapshot.offer;
  const product = snapshot.product;
  const attributes = Object.values(product.attributes || {}).join(" · ") || "No specifications recorded";
  const evidence = (product.evidence || []).map(entry =>
    '<p>' + (entry.url
      ? '<a href="' + esc(entry.url) + '" target="_blank" rel="noopener">Source ↗</a>'
      : '<span>Demo fixture</span>') + ' · ' + esc(entry.excerpt) + '</p>'
  ).join("");
  const priceType = offer.price_kind === "fixture" ? "Demo price" :
    offer.price_kind === "unknown" ? "Price unavailable" : "Captured price";
  const stock = offer.stock === "unknown" ? "Unknown" :
    offer.stock === "out" ? "Out of stock" : "Available when captured";

  return '<article class="product"><div class="product-top">' + productImage(snapshot) +
    '<div class="product-info"><h3>' + esc(product.name) + '</h3><p class="spec">' +
    esc(snapshot.variant.spec) + '</p><span class="badge">' +
    (item.required ? "Required" : "Optional") + '</span> <span class="badge amber">' +
    esc(kindLabels[product.kind] || product.kind) + '</span>' +
    (offer.url ? '<a class="product-link" href="' + esc(offer.url) +
      '" target="_blank" rel="noopener">View product ↗</a>' : '') +
    '</div><div class="price">' + money(offer.price_minor, offer.currency) + '</div></div><p class="reason">' +
    esc(item.reason) + '</p><details><summary>Details and sources</summary><p>' +
    esc(attributes) + '</p><p>' + esc(offer.merchant) + ' · SKU ' +
    esc(snapshot.variant.sku) + '</p><p>' + esc(priceType) + ' · ' +
    esc((offer.captured_at || "").slice(0, 10) || "Date unknown") + '</p><p>Stock: ' +
    esc(stock) + ' · Shipping: ' + money(offer.shipping_minor, offer.currency) +
    '</p><p>' + esc(offer.conditions || "") + '</p>' + evidence + '<p>' +
    esc((product.limitations || []).join(" · ")) + '</p></details><div class="card-actions">' +
    '<div class="qty"><button data-action="quantity" data-id="' + esc(item.offer_id) +
    '" data-delta="-1" aria-label="Decrease ' + esc(product.name) + '">−</button><span>' +
    item.quantity + '</span><button data-action="quantity" data-id="' + esc(item.offer_id) +
    '" data-delta="1" aria-label="Increase ' + esc(product.name) + '">＋</button></div>' +
    '<button data-action="replace" data-id="' + esc(item.offer_id) + '">Replace</button>' +
    '<button data-action="priority" data-id="' + esc(item.offer_id) + '">' +
    (item.required ? "Make optional" : "Make required") + '</button>' +
    '<button class="remove" data-action="remove" data-id="' + esc(item.offer_id) +
    '">Remove</button></div></article>';
}

function planPanel() {
  const items = task?.items || [];
  const totals = task?.totals;
  const headerState = task?.confirmation ? "Confirmed" : items.length ? "Review" : "Empty";
  const itemContent = items.length
    ? '<div class="budget"><form id="budget-form" class="budget-row"><label for="budget">Budget · ' +
      esc(task.currency || "CNY") + '</label><div><input id="budget" aria-label="Budget" type="number" ' +
      'min="0" max="1000000" step=".01" value="' +
      (task.budget_minor === null ? "" : task.budget_minor / 100) +
      '" placeholder="Not set"><button type="submit">Update</button></div></form></div>' +
      items.map(productCard).join("")
    : '<div class="plan-empty"><span class="empty-glyph">＋</span><h3>Your plan</h3>' +
      '<p>Recommendations will collect here.</p><div class="empty-steps">' +
      '<span>Search</span><span>·</span><span>Compare</span><span>·</span><span>Confirm</span></div></div>';

  let totalsContent = "";
  if (items.length) {
    totalsContent = '<div class="total-row"><span>Known total</span><strong>' +
      money(totals.known_total_minor, totals.currency) + '</strong></div><div class="status-line">' +
      (totals.remaining_minor !== null
        ? money(totals.remaining_minor, totals.currency) + " remaining"
        : "No budget set") + '</div>';
    if (totals.unknown.length) {
      totalsContent += '<div class="unknown">Some costs are still unknown.<details><summary>' +
        totals.unknown.length + ' notes</summary>' +
        totals.unknown.map(entry => esc(entry)).join("<br>") + '</details></div>';
    }
    if ((task.compatibility || []).length) {
      totalsContent += '<details class="compat"><summary>Compatibility · ' +
        task.compatibility.length + '</summary>' +
        task.compatibility.map(entry => esc(entry)).join("<br>") + '</details>';
    }
  }

  return '<section class="plan"><div class="plan-head"><div><h3>Shopping plan</h3><small>' +
    (items.length ? items.length + ' item' + (items.length === 1 ? "" : "s") +
      ' · Revision ' + task.revision : "Nothing added yet") +
    '</small></div><span class="badge">' + headerState + '</span></div>' + itemContent +
    '<div class="plan-bottom">' + totalsContent +
    '<button class="primary wide" data-action="' + (task?.confirmation ? "checkout" : "confirm") +
    '" ' + (!items.length || busy ? "disabled" : "") + '>' +
    (task?.confirmation ? "Open purchase options →" : "Review and confirm →") + '</button>' +
    '<div class="secondary-row"><button data-action="catalog">' +
    (task?.scope === "demo" ? "Browse demo items" : "Add from results") + '</button>' +
    (items.length ? '<button data-action="refresh">Refresh</button>' : "") +
    '</div>' + (task ? '<p>' + esc(labelStatus(task.status)) + '</p>' : "") + '</div></section>';
}

function conversationContent() {
  if (task?.messages.length) {
    return '<div class="messages">' + task.messages.map(message =>
      '<div class="bubble ' + (message.role === "user" ? "user" : "") +
      '"><span class="bubble-label">' + (message.role === "user" ? "You" : "ShopFlow") +
      '</span><div class="message-content">' +
      (message.role === "user" ? '<p>' + esc(message.content) + '</p>' : markdown(message.content)) +
      '</div></div>'
    ).join("") + (busy ? '<p class="status-line">Working on your request…</p>' : "") + '</div>';
  }
  const recent = boot.tasks.filter(item => item.id !== task?.id && item.messages?.length).slice(0, 4);
  const recentCards = recent.length ? recent.map(item => {
    const product = item.items?.[0]?.snapshot?.product;
    const visual = product?.image
      ? '<img src="' + esc(product.image) + '" alt="" loading="lazy">'
      : '<span>' + esc((product?.category || item.title || "S").slice(0, 1).toUpperCase()) + '</span>';
    return '<button class="recent-card" data-action="history" data-id="' + esc(item.id) +
      '"><span class="recent-visual">' + visual + '</span><strong>' +
      esc(item.title === "新的采购任务" ? "Shopping list" : item.title) + '</strong><small>' +
      esc(item.items?.length ? item.items.length + " planned item" + (item.items.length === 1 ? "" : "s") : "Continue shopping") +
      '</small></button>';
  }).join("") : '<p class="recent-empty">Your recent shopping tasks will appear here.</p>';
  return '<div class="welcome"><div class="welcome-orb"><img class="companion-icon" src="/shopflow-companion.svg" alt=""></div>' +
    '<p class="eyebrow">SHOPFLOW</p><h1>What are you looking for?</h1>' +
    '<p>Describe what you need. Add a budget or a must-have detail when it matters.</p>' +
    composer(true) +
    '<div class="prompt-chips"><button data-action="example" ' +
    'data-text="I have a budget of CNY 1,000 to improve my study desk. I already own a laptop and mouse.">Study setup</button>' +
    '<button data-action="example" data-text="Find a reliable wired USB keyboard under USD 20.">Keyboard under $20</button></div>' +
    '<section class="recent-section"><div class="recent-head"><h2>Recent shopping</h2><span>Pick up where you left off</span></div>' +
    '<div class="recent-grid">' + recentCards + '</div></section></div>';
}

function composer(hero = false) {
  return '<form class="composer ' + (hero ? "hero-composer" : "") + '" id="chat-form">' +
    '<textarea id="message" aria-label="Shopping request" placeholder="Describe what you want to buy…" maxlength="2000" ' +
    (busy ? "disabled" : "") + '></textarea><div class="composer-row"><small>' +
    ((!task || task.scope === "real") ? "Shop products" : "Demo catalog") +
    '</small><button class="primary send" type="submit" aria-label="Send" ' +
    (busy ? "disabled" : "") + '></button></div></form>';
}

function workspace() {
  const title = task && task.title !== "新的采购任务" ? task.title : "New shopping list";
  return '<div class="workspace"><div class="workspace-head"><div><h2>' + esc(title) +
    '</h2></div><div class="scope-control"><button class="compact-new" data-action="new">＋ New</button>' +
    '<select id="scope" aria-label="Shopping mode"><option value="real" ' +
    ((!task || task.scope === "real") ? "selected" : "") + '>Live</option><option value="demo" ' +
    (task?.scope === "demo" ? "selected" : "") + '>Demo</option></select>' +
    '<select id="currency" aria-label="Currency"><option value="CNY">CNY</option>' +
    '<option value="USD" ' + (task?.currency === "USD" ? "selected" : "") + '>USD</option>' +
    '<option value="GBP" ' + (task?.currency === "GBP" ? "selected" : "") + '>GBP</option></select></div></div>' +
    '<div class="columns ' + (task?.messages.length ? "active-chat" : "landing") +
    '"><section class="conversation">' + conversationContent() +
    (task?.messages.length ? composer() : "") + '</section>' + planPanel() + '</div></div>';
}

function modeSummary() {
  if (boot.mode === "offline") return ["Demo", "Rules"];
  if (!boot.integrations.model_configured) return ["Setup needed", "Model"];
  if (!boot.integrations.search_configured) return ["Setup needed", "Search"];
  return ["Live", "Ready"];
}

function setRouteLabel() {
  const label = location.pathname.startsWith("/runs") ? "Activity" :
    location.pathname.startsWith("/evaluation") ? "Evaluation" :
    location.pathname === "/lab" ? "Lab" : "Workspace";
  $("#route-label").textContent = label;
}

function render() {
  if (!boot) return;
  const mode = modeSummary();
  $("#modebar").innerHTML = '<span class="mode-dot"></span><strong>' + mode[0] +
    '</strong><small>' + mode[1] + '</small>';
  $("#history").innerHTML = historyList();
  setRouteLabel();
  document.querySelectorAll("[data-nav]").forEach(link =>
    link.classList.toggle("active",
      link.dataset.nav === "/" ? location.pathname === "/" : location.pathname.startsWith(link.dataset.nav))
  );
  if (location.pathname === "/") {
    $("#main").innerHTML = workspace();
    const messages = $(".messages");
    if (messages) messages.scrollTop = messages.scrollHeight;
  }
}

function modal(title, content, actions = "") {
  const dialog = $("#dialog");
  $("#dialog-content").innerHTML = '<div class="dialog-head"><h2>' + esc(title) +
    '</h2><button class="close" data-action="close" aria-label="Close">×</button></div>' +
    '<div class="dialog-body">' + content + '</div>' +
    (actions ? '<div class="dialog-actions">' + actions + '</div>' : "");
  if (!dialog.open) dialog.showModal();
}
function closeModal() { $("#dialog").close(); }

async function send(message, fault) {
  if (busy || !message.trim()) return;
  busy = true;
  try {
    if (!task) await create($("#scope")?.value || "real", $("#currency")?.value || "CNY");
    render();
    saveLocal(await api(fault ? "/api/lab/chat" : "/api/chat", requestBody({text: message, fault})));
    cart = null;
  } catch (error) {
    notice(error.message);
    if (task) saveLocal(await api("/api/task/" + task.id));
  } finally {
    busy = false;
    render();
  }
}

const planLines = () => task.items.map(({offer_id, quantity, required, reason}) =>
  ({offer_id, quantity, required, reason}));

async function editItems(items) {
  saveLocal(await api("/api/edit", requestBody({action: "plan", items})));
  cart = null;
  render();
}

async function showCatalog(id) {
  if (!task) await create();
  replaceId = id || null;
  if (task.scope === "real") {
    const planned = new Set(task.items.map(item => item.offer_id));
    const rows = (task.cached_offers || []).filter(item => !planned.has(item.offer_id));
    if (!rows.length) {
      modal("Add a product", "<p>Ask ShopFlow to find another product first. New results will appear here so you can add them to the plan.</p>");
      return;
    }
    modal(id ? "Choose a replacement" : "Add from search results",
      '<div class="catalog-grid">' + rows.map(item =>
        '<article class="catalog-card">' +
        (item.image ? '<div class="product-image"><img src="' + esc(item.image) + '" alt="' + esc(item.name) + '" loading="lazy"></div>' : '') +
        '<h3>' + esc(item.name) + '</h3><p>' + esc(item.spec || "Specifications not listed") + '</p>' +
        '<strong>' + money(item.price_minor, item.currency) + '</strong><p>' + esc(item.merchant || "") + '</p>' +
        (item.source_url ? '<a target="_blank" rel="noopener" href="' + esc(item.source_url) + '">View product ↗</a>' : '') +
        '<button data-action="add" data-id="' + esc(item.offer_id) + '" ' +
        (item.currency !== (task.currency || "CNY") ? "disabled" : "") + '>' +
        (id ? "Use this product" : "Add to plan") + '</button></article>'
      ).join("") + '</div>');
    return;
  }
  const old = task.items.find(item => item.offer_id === id);
  const rows = catalog[task.scope].filter(snapshot =>
    (!old || snapshot.product.category === old.snapshot.product.category) &&
    snapshot.offer.id !== id
  );
  modal(id ? "Replace item" : "Demo catalog",
    '<div class="catalog-grid">' + rows.map(snapshot =>
      '<article class="catalog-card">' + productImage(snapshot) + '<h3>' +
      esc(snapshot.product.name) + '</h3><p>' + esc(snapshot.variant.spec) + '</p><p>' +
      esc(Object.values(snapshot.product.attributes || {}).join(" · ")) + '</p><span class="badge">' +
      esc(kindLabels[snapshot.product.kind] || snapshot.product.kind) + '</span><strong>' +
      money(snapshot.offer.price_minor, snapshot.offer.currency) + '</strong><p>' +
      esc(snapshot.offer.conditions) + '</p>' +
      (snapshot.product.evidence || []).filter(entry => entry.url).map(entry =>
        '<a target="_blank" rel="noopener" href="' + esc(entry.url) + '">Source ↗</a>'
      ).join("") + '<button data-action="add" data-id="' + esc(snapshot.offer.id) + '" ' +
      (snapshot.offer.currency !== (task.currency || "CNY") ? "disabled" : "") + '>' +
      (snapshot.offer.currency !== (task.currency || "CNY")
        ? "Different currency"
        : replaceId ? "Use this item" : "Add to plan") +
      '</button></article>').join("") + '</div>');
}

function confirmationPanel() {
  const shippingUnknown = task.totals.unknown.some(entry => String(entry).includes("运费") || /shipping/i.test(entry));
  modal("Review your plan",
    '<p>Check the seller, specifications, quantities, and known costs.</p>' +
    task.items.map(item => '<div class="confirm-line"><strong>' +
      esc(item.snapshot.product.name) + '</strong>' + esc(item.snapshot.offer.merchant) +
      ' · ' + esc(item.snapshot.variant.spec) + '<br>SKU ' + esc(item.snapshot.variant.sku) +
      ' · Qty ' + item.quantity + ' · ' +
      money(item.snapshot.offer.price_minor, item.snapshot.offer.currency) + '</div>').join("") +
    '<p>Known total: ' + money(task.totals.known_total_minor, task.totals.currency) +
    '<br>Shipping: ' + (shippingUnknown ? "Unknown" : money(task.totals.shipping_known_minor)) +
    '</p><label class="check-label"><input id="ack" type="checkbox">' +
    'I have reviewed this version and its unknown costs.</label>',
    '<button data-action="close">Keep editing</button>' +
    '<button class="primary" data-action="do-confirm">Confirm plan</button>');
}

function showEntries(nextCart) {
  cart = nextCart;
  modal("Purchase options",
    '<p>Revision ' + nextCart.revision + '</p>' +
    nextCart.entries.map((entry, index) =>
      '<div class="entry"><strong>' + esc(entry.merchant) + '</strong><small>' +
      esc(entry.kind === "local_demo" ? "Local demo" :
        entry.kind === "shopify_test" ? "Test store" :
        entry.kind === "external" ? "Seller website" : "Link unavailable") +
      '</small>' + (entry.url
        ? '<button class="primary" data-action="jump" data-index="' + index + '">' +
          esc(entry.label) + ' ↗</button>'
        : esc(entry.label)) + '</div>'
    ).join(""),
    '<button data-action="close">Close</button><button data-action="mark">Mark as purchased</button>');
}

async function route(path, push = true) {
  if (push) history.pushState({}, "", path);
  document.body.classList.toggle("maintenance", /^\/(runs|evaluation)(\/|$)/.test(path));
  document.body.classList.toggle("drawer-hidden", path !== "/");
  const title = path.startsWith("/runs") ? "Activity" :
    path.startsWith("/evaluation") ? "Evaluation" :
    path === "/lab" ? "Lab" : "Workspace";
  document.title = "ShopFlow · " + title;
  render();
  if (path === "/") return;
  $("#main").innerHTML = '<p class="loading">Loading…</p>';
  try {
    if (path === "/runs" || path.startsWith("/runs/") ||
        path === "/evaluation" || path.startsWith("/evaluation/")) {
      await MaintenanceUI.route(path);
    } else if (path === "/lab") {
      $("#main").innerHTML = '<div class="page"><h1>Lab</h1><p>Test failure recovery on the current list.</p>' +
        '<section class="panel"><h3>Failure injection</h3><p>' +
        (!boot.test_lab ? "Enable the test lab to use these controls." : "The test lab is ready.") +
        '</p><p>Current list: ' + esc(task?.title || "None") + '</p><div class="toolbar">' +
        '<button data-action="fault-search" ' + (!boot.test_lab || !task ? "disabled" : "") +
        '>Search timeout</button><button data-action="fault-model" ' +
        (!boot.test_lab || !task ? "disabled" : "") + '>Model failure</button>' +
        '<button data-action="fault-checkout" ' +
        (!boot.test_lab || !task?.confirmation ? "disabled" : "") +
        '>Checkout failure</button></div></section></div>';
    } else if (path.startsWith("/checkout/")) {
      const response = await api("/api/cart/" + path.split("/").pop());
      const data = response.body;
      $("#main").innerHTML = '<div class="page checkout-summary"><span class="pill">Demo checkout</span>' +
        '<h1>Checkout rehearsal</h1><p>No payment or order is created.</p><div class="panel">' +
        (data.snapshot?.items || []).map(item => '<div class="confirm-line"><strong>' +
          esc(item.snapshot.product.name) + '</strong>' + esc(item.snapshot.variant.spec) +
          ' × ' + item.quantity + '<br>' +
          money(item.snapshot.offer.price_minor, item.snapshot.offer.currency) + '</div>').join("") +
        '<p>Known total ' + money(data.snapshot?.totals.known_total_minor,
          data.snapshot?.currency || "CNY") + '</p><p>' + esc(labelStatus(data.status)) +
        '</p><button class="primary wide" data-action="finish-demo" data-id="' +
        esc(response.id) + '">Complete demo</button></div>' +
        '<a href="/" data-nav="/">← Back to workspace</a></div>';
    } else if (path === "/preferences") {
      history.replaceState({}, "", "/");
      render();
      showPreferences();
    }
  } catch (error) {
    $("#main").innerHTML = '<div class="page"><h2>Could not load this page</h2><p>' +
      esc(error.message) + '</p><a href="/" data-nav="/">Back to workspace</a></div>';
  }
  setRouteLabel();
}

function showPreferences() {
  const preferences = boot.preferences;
  modal("Preferences",
    '<label>Things you own<input id="owned" type="text" value="' +
    esc(preferences.owned.join(", ")) + '" placeholder="Mouse, monitor"></label>' +
    '<label>Shopping preferences<textarea id="pref-text" rows="4" ' +
    'placeholder="Quiet keys, limited desk space">' + esc(preferences.text) +
    '</textarea></label>',
    '<button data-action="close">Cancel</button>' +
    '<button class="primary" data-action="save-preferences">Save</button>');
}

function showDeleteTask(taskId) {
  const target = boot.tasks.find(item => item.id === taskId);
  if (!target) return;
  deleteTargetId = taskId;
  modal("Delete this conversation?",
    "<p>This removes <strong>" + esc(target.title === "新的采购任务" ? "New list" : target.title) +
    "</strong> and its saved activity from this device.</p>",
    '<button data-action="close">Cancel</button>' +
    '<button class="danger-button" data-action="do-delete-task">Delete conversation</button>');
}

function hideHistoryMenu() {
  const menu = $("#history-menu");
  if (menu) menu.hidden = true;
}

document.addEventListener("contextmenu", event => {
  const item = event.target.closest(".history-item");
  if (!item) return;
  event.preventDefault();
  deleteTargetId = item.dataset.id;
  const menu = $("#history-menu");
  menu.hidden = false;
  const width = 190, height = 48;
  menu.style.left = Math.min(event.clientX, window.innerWidth - width - 8) + "px";
  menu.style.top = Math.min(event.clientY, window.innerHeight - height - 8) + "px";
  menu.querySelector("button").focus();
});

document.addEventListener("click", async event => {
  if (!event.target.closest("#history-menu")) hideHistoryMenu();
  const navigation = event.target.closest("[data-nav]");
  if (navigation) {
    event.preventDefault();
    return route(navigation.dataset.nav);
  }
  const element = event.target.closest("[data-action]");
  if (!element || element.disabled) return;
  const action = element.dataset.action;
  try {
    if (action === "close") closeModal();
    else if (action === "new") { await create(); await route("/"); }
    else if (action === "history") {
      saveLocal(await api("/api/task/" + element.dataset.id));
      cart = null;
      await route("/");
    } else if (action === "example") await send(element.dataset.text);
    else if (action === "preferences") showPreferences();
    else if (action === "delete-history") { hideHistoryMenu(); showDeleteTask(deleteTargetId); }
    else if (action === "do-delete-task") {
      const deletedId = deleteTargetId;
      const target = deletedId === task?.id ? task : boot.tasks.find(item => item.id === deletedId);
      if (!target) throw new Error("Conversation not found.");
      element.disabled = true;
      await api("/api/delete-task", {task_id: target.id, revision: target.revision});
      boot.tasks = boot.tasks.filter(item => item.id !== deletedId);
      if (task?.id === deletedId) task = boot.tasks[0] || null;
      if (task) localStorage.setItem("task", task.id); else localStorage.removeItem("task");
      deleteTargetId = null;
      cart = null;
      closeModal();
      await route("/", false);
      notice("Conversation deleted.");
    }
    else if (action === "save-preferences") {
      boot.preferences = await api("/api/preferences", {
        owned: $("#owned").value.split(/[,，、]/).map(value => value.trim()).filter(Boolean),
        text: $("#pref-text").value
      });
      closeModal();
      notice("Preferences saved.");
    } else if (action === "catalog" || action === "replace") {
      await showCatalog(action === "replace" ? element.dataset.id : null);
    } else if (action === "add") {
      const items = planLines();
      if (replaceId) {
        const item = items.find(entry => entry.offer_id === replaceId);
        item.offer_id = element.dataset.id;
        item.reason = "Selected as a replacement; review the specifications.";
      } else {
        if (items.some(entry => entry.offer_id === element.dataset.id)) {
          throw new Error("This item is already in the plan.");
        }
        items.push({
          offer_id: element.dataset.id,
          quantity: 1,
          required: true,
          reason: "Selected by the user."
        });
      }
      await editItems(items);
      closeModal();
    } else if (action === "remove") {
      await editItems(planLines().filter(item => item.offer_id !== element.dataset.id));
    } else if (action === "priority") {
      const items = planLines();
      const item = items.find(entry => entry.offer_id === element.dataset.id);
      item.required = !item.required;
      await editItems(items);
    } else if (action === "quantity") {
      const items = planLines();
      const item = items.find(entry => entry.offer_id === element.dataset.id);
      item.quantity += Number(element.dataset.delta);
      if (item.quantity < 1) throw new Error("Quantity must be at least one.");
      await editItems(items);
    } else if (action === "refresh") {
      saveLocal(await api("/api/edit", requestBody({action: "refresh"})));
      cart = null;
      render();
      notice("Plan refreshed.");
    } else if (action === "confirm") confirmationPanel();
    else if (action === "do-confirm") {
      if (!$("#ack").checked) throw new Error("Review and accept the note first.");
      element.disabled = true;
      saveLocal(await api("/api/confirm", requestBody({acknowledge_unknown: true})));
      closeModal();
      render();
      notice("Plan confirmed.");
    } else if (action === "checkout") {
      element.disabled = true;
      showEntries(await api("/api/checkout", requestBody()));
    } else if (action === "jump") {
      const result = await api("/api/jump", {cart_id: cart.id, index: Number(element.dataset.index)});
      if (result.url.startsWith("/")) {
        closeModal();
        await route(result.url);
      } else {
        const link = document.createElement("a");
        link.href = result.url;
        link.target = "_blank";
        link.rel = "noopener";
        link.click();
        notice("Link opened.");
      }
    } else if (action === "mark") {
      saveLocal(await api("/api/mark-purchased", requestBody({explicit: true})));
      closeModal();
      render();
    } else if (action === "finish-demo") {
      await api("/api/demo-finish", {cart_id: element.dataset.id});
      await route(location.pathname, false);
    } else if (action === "fault-search" || action === "fault-model") {
      await send("Find a keyboard under CNY 300.",
        action === "fault-search" ? "search" : "model");
      await route("/runs");
    } else if (action === "fault-checkout") {
      await api("/api/lab/checkout", requestBody());
      notice("Checkout test finished.");
    }
  } catch (error) {
    notice(error.message);
    if (element.isConnected) element.disabled = false;
    if (error.status === 409 && task) {
      saveLocal(await api("/api/task/" + task.id));
      render();
    }
  }
});

document.addEventListener("submit", async event => {
  event.preventDefault();
  try {
    if (event.target.id === "chat-form") {
      await send($("#message").value);
    } else if (event.target.id === "budget-form") {
      const value = $("#budget").value;
      if (value === "") throw new Error("Enter a budget.");
      saveLocal(await api("/api/edit", requestBody({
        action: "budget",
        budget_minor: Math.round(Number(value) * 100)
      })));
      cart = null;
      render();
    }
  } catch (error) {
    notice(error.message);
  }
});

document.addEventListener("change", async event => {
  if (["scope", "currency"].includes(event.target.id)) {
    try {
      const scope = $("#scope").value;
      const currency = scope === "demo" ? "CNY" : $("#currency").value;
      await create(scope, currency);
    } catch (error) {
      notice(error.message);
    }
  }
});

document.addEventListener("keydown", event => {
  if (event.target.id === "message" && event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    send(event.target.value);
  }
});

addEventListener("popstate", () => route(location.pathname, false));

(async () => {
  try {
    boot = await api("/api/bootstrap");
    catalog = await api("/api/catalog");
    task = boot.tasks.find(item => item.id === localStorage.getItem("task")) || boot.tasks[0] || null;
    render();
    await route(location.pathname, false);
  } catch (error) {
    $("#main").innerHTML = '<div class="page"><h2>ShopFlow is unavailable</h2><p>' +
      esc(error.message) + '</p><p>Start the service and refresh this page.</p></div>';
  }
})();

document.addEventListener("error", event => {
  if (event.target.tagName === "IMG" && event.target.closest(".product-image")) {
    event.target.closest(".product-image").textContent = "Image unavailable";
  }
}, true);
