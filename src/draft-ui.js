(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const scriptUrl = document.currentScript?.src || new URL("src/draft-ui.js", document.baseURI).href;
  const toolsUrl = new URL("draft-tools.mjs", scriptUrl).href;
  const state = { drafts: [], selectedId: null, storageError: null, tools: null };
  const pendingWordCards = [];

  const fields = {
    dialog: "#draft-dialog",
    open: "#draft-open",
    close: "#draft-close",
    mask: "#draft-mask",
    createForm: "#draft-create-form",
    createLemma: "#draft-lemma",
    createPos: "#draft-pos",
    createZh: "#draft-zh",
    createNote: "#draft-note",
    createError: "#draft-create-error",
    storageNotice: "#draft-storage-notice",
    list: "#draft-list",
    detail: "#draft-detail",
  };

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" }[char]));
  }

  function formatTime(value) {
    const date = new Date(Number(value) || Date.now());
    return date.toLocaleDateString("zh-CN", { month: "2-digit", day: "2-digit" });
  }

  function saveDrafts() {
    const result = state.tools.saveDraftState(window.localStorage, state.drafts);
    state.drafts = result.drafts;
    state.storageError = result.error;
    return result.ok;
  }

  function selectedDraft() {
    return state.drafts.find((draft) => draft.id === state.selectedId) || null;
  }

  function selectDraft(id) {
    state.selectedId = id;
    render();
  }

  function renderNotice() {
    const notice = $(fields.storageNotice);
    if (!state.storageError) {
      notice.classList.add("hidden");
      notice.textContent = "";
      return;
    }
    notice.textContent = state.storageError;
    notice.classList.remove("hidden");
  }

  function renderList() {
    const list = $(fields.list);
    if (!state.drafts.length) {
      list.innerHTML = `<div class="draft-empty">还没有词卡。先记录一个想记住的词。</div>`;
      return;
    }
    list.innerHTML = state.drafts.map((draft) => `
      <button class="draft-list-item${draft.id === state.selectedId ? " active" : ""}" type="button" data-draft-id="${escapeHtml(draft.id)}">
        <strong>${escapeHtml(draft.lemma)}</strong>
        <em>${escapeHtml(draft.pos)}</em>
        <small>${escapeHtml(draft.zhHint || "暂无中文提示")} · ${formatTime(draft.updatedAt)}</small>
      </button>
    `).join("");
    list.querySelectorAll("[data-draft-id]").forEach((button) => button.addEventListener("click", () => selectDraft(button.dataset.draftId)));
  }

  function renderDetail() {
    const detail = $(fields.detail);
    const draft = selectedDraft();
    if (!draft) {
      detail.innerHTML = `<div class="draft-empty">选择左侧词卡后，可编辑中文提示和备注。</div>`;
      return;
    }
    detail.innerHTML = `
      <article class="draft-card-preview">
        <div class="word-meta"><span>${escapeHtml(draft.pos)}</span><span>我的词卡</span></div>
        <h3>${escapeHtml(draft.lemma)}</h3>
        <p>${escapeHtml(draft.zhHint || "暂无中文提示")}</p>
      </article>
      <form id="draft-edit-form" class="draft-edit-form">
        <label>中文提示<textarea id="draft-edit-zh" rows="3">${escapeHtml(draft.zhHint)}</textarea></label>
        <label>备注<textarea id="draft-edit-note" rows="6">${escapeHtml(draft.note)}</textarea></label>
        <p id="draft-edit-error" class="form-error"></p>
        <div class="dialog-actions">
          <button class="primary-button" type="submit">保存词卡</button>
        </div>
      </form>
    `;
    $("#draft-edit-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const result = state.tools.updateDraft(draft, {
        zhHint: $("#draft-edit-zh").value,
        note: $("#draft-edit-note").value,
      });
      if (!result.ok) {
        $("#draft-edit-error").textContent = result.error;
        return;
      }
      state.drafts = state.tools.upsertDraft(state.drafts, result.draft);
      if (!saveDrafts()) $("#draft-edit-error").textContent = state.storageError;
      render();
    });
  }

  function render() {
    renderNotice();
    renderList();
    renderDetail();
  }

  function openDialog() {
    $(fields.dialog).classList.remove("hidden");
    $(fields.createLemma).focus();
    render();
  }

  function openSelectedDialog() {
    $(fields.dialog).classList.remove("hidden");
    $(fields.createError).textContent = "";
    render();
  }

  function closeDialog() {
    $(fields.dialog).classList.add("hidden");
    $(fields.createError).textContent = "";
  }

  function bindCreateForm() {
    $(fields.createForm).addEventListener("submit", (event) => {
      event.preventDefault();
      const result = state.tools.createDraft({
        lemma: $(fields.createLemma).value,
        pos: $(fields.createPos).value,
        zhHint: $(fields.createZh).value,
        note: $(fields.createNote).value,
      });
      if (!result.ok) {
        $(fields.createError).textContent = result.error;
        return;
      }
      state.drafts = state.tools.upsertDraft(state.drafts, result.draft);
      state.selectedId = result.draft.id;
      if (!saveDrafts()) {
        $(fields.createError).textContent = state.storageError;
        render();
        return;
      }
      $(fields.createForm).reset();
      $(fields.createError).textContent = "";
      render();
    });
  }

  function openFromWordCard(input) {
    if (!state.tools) {
      pendingWordCards.push(input);
      return;
    }
    const existing = state.tools.findDraftForWordCard(state.drafts, input);
    if (existing) {
      state.selectedId = existing.id;
      openSelectedDialog();
      return;
    }
    const result = state.tools.createDraft({
      lemma: input?.lemma,
      pos: input?.pos,
      zhHint: input?.zhHint,
      note: "",
      sourceLexemeId: input?.sourceLexemeId,
    });
    if (!result.ok) {
      state.storageError = result.error;
      openSelectedDialog();
      return;
    }
    state.drafts = state.tools.upsertDraft(state.drafts, result.draft);
    state.selectedId = result.draft.id;
    saveDrafts();
    openSelectedDialog();
  }

  window.WordcloudDraftCards = {
    open: openDialog,
    openFromWordCard,
  };

  window.addEventListener("wordcloud:open-draft-card", (event) => openFromWordCard(event.detail));

  async function init() {
    state.tools = await import(toolsUrl);
    const loaded = state.tools.loadDraftState(window.localStorage);
    state.drafts = loaded.drafts;
    state.storageError = loaded.error;
    state.selectedId = state.drafts[0]?.id || null;
    $(fields.open).addEventListener("click", openDialog);
    $(fields.close).addEventListener("click", closeDialog);
    $(fields.mask).addEventListener("click", closeDialog);
    bindCreateForm();
    render();
    while (pendingWordCards.length) openFromWordCard(pendingWordCards.shift());
  }

  window.addEventListener("DOMContentLoaded", () => {
    init().catch(() => {
      const notice = $(fields.storageNotice);
      if (notice) {
        notice.textContent = "我的词卡暂时不可用。";
        notice.classList.remove("hidden");
      }
    });
  });
})();
