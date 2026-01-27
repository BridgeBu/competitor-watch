async function jget(path) {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`Fetch failed: ${path}`);
  return r.json();
}

function escapeHtml(s) {
  return (s || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function zhType(type) {
  return ({ NEW: "新上架", PRICE: "改价", REMOVED: "下架", OOS: "缺货", RESTOCK: "补货" })[type] || type;
}

function priceText(sym, p) {
  if (!p) return "";
  const [a, b] = p;
  if (a == null && b == null) return "";
  if (a === b) return `${sym}${a}`;
  return `${sym}${a}–${sym}${b}`;
}

function priceDelta(oldP, newP) {
  if (!oldP || !newP) return "";
  const o = oldP[0], n = newP[0];
  if (o == null || n == null) return "";
  if (n > o) return "↑ 上涨";
  if (n < o) return "↓ 降价";
  return "价格不变";
}

function groupBy(arr, key) {
  const m = {};
  for (const x of (arr || [])) {
    const k = x[key] || "Other";
    (m[k] ||= []).push(x);
  }
  return m;
}

function buildChangeIndex(changes) {
  const m = {};
  for (const ch of (changes || [])) {
    m[ch.key] = ch;
  }
  return m;
}

function setupAccordions() {
  // Ensure only one accordion detail is open per site
  document.querySelectorAll('details.accordion-item').forEach(d => {
    d.addEventListener('toggle', () => {
      if (!d.open) return;
      const site = d.getAttribute('data-site') || '';
      document.querySelectorAll(`details.accordion-item[data-site="${site}"]`).forEach(other => {
        if (other !== d) other.removeAttribute('open');
      });
    });
  });
}

function renderOverview(sum) {
  const t = sum.totals || {};
  const items = [
    ["新上架", t.new || 0],
    ["改价", t.price || 0],
    ["下架", t.removed || 0],
    ["缺货", t.oos || 0],
    ["补货", t.restock || 0],
  ];
  return items
    .map(([k, v]) => `
      <div class="pill"><b>${v}</b><div class="muted">${k}</div></div>
    `)
    .join("");
}

function renderSite(site) {
  const sym = site.currency_symbol || "€";
  const siteKey = site.site_id || site.name || 'site';

  const badge = site.status === "ok"
    ? `<span class="tag ok">正常</span>`
    : `<span class="tag err">错误</span>`;

  const headRight = site.status === "ok"
    ? `<span class="muted">币种：${escapeHtml(site.currency_code || "")}</span>`
    : `<span class="muted">${escapeHtml(site.error || "")}</span>`;

  const counts = site.counts || {};

  // 商品现状
  const ps = site.product_status || {};
  const statusPills = `
    <div class="grid" style="grid-template-columns: repeat(3, minmax(0, 1fr));">
      <div class="pill"><b>${ps.total ?? 0}</b><div class="muted">总SKU</div></div>
      <div class="pill"><b>${ps.in_stock ?? 0}</b><div class="muted">在架SKU</div></div>
      <div class="pill"><b>${ps.oos ?? 0}</b><div class="muted">缺货SKU</div></div>
    </div>
  `;

  // 商品变动（结构化）
  const changePills = `
    <div class="grid" style="grid-template-columns: repeat(5, minmax(0, 1fr));">
      <div class="pill"><b>${counts.new || 0}</b><div class="muted">新上架</div></div>
      <div class="pill"><b>${counts.price || 0}</b><div class="muted">改价</div></div>
      <div class="pill"><b>${counts.removed || 0}</b><div class="muted">下架</div></div>
      <div class="pill"><b>${counts.oos || 0}</b><div class="muted">缺货</div></div>
      <div class="pill"><b>${counts.restock || 0}</b><div class="muted">补货</div></div>
    </div>
  `;

  // 价格区间
  const pb = site.price_buckets_total || {};
  const bucketPills = `
    <div class="grid" style="grid-template-columns: repeat(5, minmax(0, 1fr));">
      <div class="pill"><b>${pb["0-50"] || 0}</b><div class="muted">0–50${sym}</div></div>
      <div class="pill"><b>${pb["50-100"] || 0}</b><div class="muted">50–100${sym}</div></div>
      <div class="pill"><b>${pb["100-150"] || 0}</b><div class="muted">100–150${sym}</div></div>
      <div class="pill"><b>${pb["150-200"] || 0}</b><div class="muted">150–200${sym}</div></div>
      <div class="pill"><b>${pb["200+"] || 0}</b><div class="muted">200+${sym}</div></div>
    </div>
  `;

  // （低优先级）按品类查看：用于查看“商品变动”的分类拆分
  const changes = (site.changes || []).slice(0, 400);
  const byCat = groupBy(changes, "category");
  const catHtml = Object.keys(byCat)
    .sort()
    .map(cat => {
      const list = (byCat[cat] || []).map(ch => {
        const title = escapeHtml(ch.title || "");
        const vlab = escapeHtml(ch.variant_label || "");
        const url = ch.url || "#";

        let tag = `<b>${zhType(ch.type)}</b>`;
        if (ch.type === "NEW") tag = `<b>新上架</b>`;
        if (ch.type === "PRICE") tag = `<b>${priceDelta(ch.old_price, ch.new_price)}</b>`;

        const newPrice = (ch.type === "PRICE" || ch.type === "NEW")
          ? ` <small>（现价：${priceText(sym, ch.new_price)}）</small>`
          : "";

        const meta = [vlab].filter(Boolean).join(" · ");
        return `
          <li class="change">
            ${tag}
            <a href="${url}" target="_blank" rel="noreferrer">${title}</a>
            ${newPrice}
            ${meta ? `<div><small>${meta}</small></div>` : ``}
          </li>
        `;
      }).join("");

      return `
        <div style="margin-top:10px; padding-top:10px; border-top:1px solid #1e2a3a;">
          <b>${escapeHtml(cat)}</b>
          <ul>${list}</ul>
        </div>
      `;
    })
    .join("");

  const changesByCategoryBlock = `
    <details style="margin-top:10px;">
      <summary class="muted" style="cursor:pointer;">按品类查看（可选）</summary>
      ${catHtml || `<div class="muted" style="margin-top:10px;">没有检测到变化。</div>`}
    </details>
  `;

  // 明细 1：畅销
  const bestsellers = (site.bestsellers || []).slice(0, 20);
  const bestsellersHtml = `
    <details class="accordion-item" data-site="${siteKey}" style="margin-top:10px;">
      <summary class="muted" style="cursor:pointer;">畅销（默认折叠） · ${bestsellers.length}条</summary>
      ${bestsellers.length ? `
        <ul>
          ${bestsellers.map(p => {
            const title = escapeHtml(p.title || "");
            const vlab = escapeHtml(p.variant_label || "");
            const url = p.url || "#";
            const priceNow = priceText(sym, [p.min_price, p.max_price]);
            const stock = (p.available === false)
              ? `<span class="tag err">缺货</span>`
              : `<span class="tag ok">有货</span>`;
            return `
              <li class="change">
                <a href="${url}" target="_blank" rel="noreferrer">${title}</a>
                ${vlab ? `<small> · ${vlab}</small>` : ""}
                <small> · 现价：${priceNow}</small>
                <small> · ${stock}</small>
              </li>
            `;
          }).join("")}
        </ul>
      ` : `<div class="muted" style="margin-top:10px;">未发现畅销集合（该站点可能未提供或命名不同）。</div>`}
    </details>
  `;

  // 明细 2：变动SKU明细
  const changesAll = (site.changes || []);
  const changesByType = groupBy(changesAll, "type");
  const typeOrder = ["NEW", "PRICE", "REMOVED", "OOS", "RESTOCK"];
  const changeDetailHtml = changesAll.length
    ? typeOrder
        .filter(t => (changesByType[t] || []).length)
        .map(t => {
          const items = (changesByType[t] || []).map(ch => {
            const title = escapeHtml(ch.title || "");
            const vlab = escapeHtml(ch.variant_label || "");
            const cat = escapeHtml(ch.category || "Other");
            const url = ch.url || "#";

            let tag = zhType(ch.type);
            let extra = "";
            if (ch.type === "NEW") {
              tag = "新上架";
              extra = ` <small>（现价：${priceText(sym, ch.new_price)}）</small>`;
            } else if (ch.type === "PRICE") {
              tag = priceDelta(ch.old_price, ch.new_price);
              extra = ` <small>（${priceText(sym, ch.old_price)} → ${priceText(sym, ch.new_price)}）</small>`;
            }

            return `
              <li class="change">
                <b>${tag}</b>
                <a href="${url}" target="_blank" rel="noreferrer">${title}</a>
                <small> · ${cat}${vlab ? ` · ${vlab}` : ""}</small>
                ${extra}
              </li>
            `;
          }).join("");

          return `
            <div style="margin-top:10px; padding-top:10px; border-top:1px solid #1e2a3a;">
              <b>${zhType(t)}</b> <span class="muted">（${(changesByType[t] || []).length}）</span>
              <ul>${items}</ul>
            </div>
          `;
        })
        .join("")
    : `<div class="muted" style="margin-top:10px;">暂无变动 SKU。</div>`;

  const changesDetailsBlock = `
    <details class="accordion-item" data-site="${siteKey}" style="margin-top:10px;">
      <summary class="muted" style="cursor:pointer;">变动SKU明细（默认折叠） · 共${changesAll.length}条</summary>
      ${changeDetailHtml}
    </details>
  `;

  // 明细 3：产品明细
  const productsByCat = site.products_by_category || {};
  const changeIndex = buildChangeIndex(site.changes || []);

  const productDetailsHtml = Object.keys(productsByCat)
    .sort()
    .map(cat => {
      const items = productsByCat[cat] || [];
      const rows = items.slice(0, 300).map(p => {
        const ch = changeIndex[p.key];
        let tag = "";
        let priceExtra = "";

        if (ch && ch.type === "NEW") {
          tag = `<span class="tag ok">新上架</span>`;
        } else if (ch && ch.type === "PRICE") {
          tag = `<span class="tag ok">${priceDelta(ch.old_price, ch.new_price)}</span>`;
          priceExtra = ` <small>（原价：${priceText(sym, ch.old_price)}）</small>`;
        }

        const priceNow = priceText(sym, [p.min_price, p.max_price]);
        const stock = (p.available === false)
          ? `<span class="tag err">缺货</span>`
          : `<span class="tag ok">有货</span>`;

        return `
          <li class="change">
            ${tag}
            <a href="${p.url}" target="_blank" rel="noreferrer">${escapeHtml(p.title || "")}</a>
            <small> · ${escapeHtml(p.variant_label || "")}</small>
            <small> · 现价：${priceNow}${priceExtra}</small>
            <small> · ${stock}</small>
          </li>
        `;
      }).join("");

      return `
        <div style="margin-top:12px;">
          <b>${escapeHtml(cat)}</b> <span class="muted">（${items.length}）</span>
          <ul>${rows}</ul>
        </div>
      `;
    })
    .join("");

  const detailsBlock = `
    <details class="accordion-item" data-site="${siteKey}" style="margin-top:10px;">
      <summary class="muted" style="cursor:pointer;">产品明细（默认折叠） · 总SKU：${site.product_total || 0}</summary>
      ${productDetailsHtml || `<div class="muted" style="margin-top:10px;">暂无产品明细</div>`}
    </details>
  `;

  const foldedHub = `
    <div style="margin-top:14px; padding-top:12px; border-top:1px solid #1e2a3a;">
      <div class="section-title" style="margin-bottom:6px;">明细（互斥展开）</div>
      ${bestsellersHtml}
      ${changesDetailsBlock}
      ${detailsBlock}
    </div>
  `;

  return `
    <div class="site">
      <div class="site-head">
        <div>
          <b>${escapeHtml(site.name || site.site_id)}</b>
          <span class="muted"> · <a href="${site.base_url}" target="_blank" rel="noreferrer">${site.base_url}</a></span>
        </div>
        <div style="display:flex; gap:10px; align-items:center;">${badge}${headRight}</div>
      </div>

      <div style="margin-top:12px;">
        <div class="section-title" style="margin-bottom:8px;">商品现状</div>
        ${statusPills}
      </div>

      <div style="margin-top:12px;">
        <div class="section-title" style="margin-bottom:8px;">商品变动</div>
        ${changePills}
        ${changesByCategoryBlock}
      </div>

      <div style="margin-top:12px;">
        <div class="section-title" style="margin-bottom:8px;">价格区间内的 SKU 数量</div>
        ${bucketPills}
      </div>

      ${foldedHub}
    </div>
  `;
}

async function main() {
  const meta = document.getElementById("meta");
  const overview = document.getElementById("overview");
  const sitesEl = document.getElementById("sites");
  const errorsEl = document.getElementById("errors");

  try {
    const [sum, sites, errors] = await Promise.all([
      jget("./data/summary.json"),
      jget("./data/sites.json"),
      jget("./data/errors.json"),
    ]);

    meta.textContent = `Last run (UTC): ${sum.time_utc} · Sites OK: ${sum.sites_ok} · Sites Error: ${sum.sites_error}`;
    overview.innerHTML = renderOverview(sum);
    sitesEl.innerHTML = (sites || []).map(renderSite).join("");
    setupAccordions();

    if (errors && errors.length) {
      errorsEl.innerHTML = errors
        .map(e => `• ${escapeHtml(e.name)}: ${escapeHtml(e.error)}`)
        .join("<br/>");
    } else {
      errorsEl.textContent = "No errors.";
    }
  } catch (e) {
    meta.textContent = "Failed to load dashboard data.";
    errorsEl.textContent = String(e);
  }
}

main();
