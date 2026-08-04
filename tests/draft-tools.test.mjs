import assert from "node:assert/strict";
import {
  createDraft,
  findDraftForWordCard,
  loadDraftState,
  saveDraftState,
  updateDraft,
  upsertDraft,
} from "../src/draft-tools.mjs";

function memoryStorage(seed = {}) {
  const values = new Map(Object.entries(seed));
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
  };
}

function throwingStorage() {
  return {
    getItem() {
      throw new Error("blocked");
    },
    setItem() {
      throw new Error("blocked");
    },
  };
}

const empty = createDraft({ lemma: "   " }, 1000);
assert.equal(empty.ok, false);
assert.equal(empty.error, "请先填写法语词。");

const created = createDraft({ lemma: " se lever ", pos: "ver", zhHint: " 起床 ", note: " 自反用法 ", sourceLexemeId: "lex-1" }, 1000);
assert.equal(created.ok, true);
assert.equal(created.draft.lemma, "se lever");
assert.equal(created.draft.pos, "VER");
assert.equal(created.draft.zhHint, "起床");
assert.equal(created.draft.sourceLexemeId, "lex-1");

const updated = updateDraft(created.draft, { lemma: "", pos: "NOM", zhHint: "起身", note: "常见日常动作", sourceLexemeId: "changed" }, 2000);
assert.equal(updated.ok, true);
assert.equal(updated.draft.lemma, "se lever");
assert.equal(updated.draft.pos, "VER");
assert.equal(updated.draft.zhHint, "起身");
assert.equal(updated.draft.note, "常见日常动作");
assert.equal(updated.draft.sourceLexemeId, "lex-1");

const drafts = upsertDraft([], updated.draft);
assert.equal(drafts.length, 1);
assert.equal(upsertDraft(drafts, { ...updated.draft, zhHint: "起床" }).length, 1);

const storage = memoryStorage();
const saved = saveDraftState(storage, drafts, "draft-test");
assert.equal(saved.ok, true);
const loaded = loadDraftState(storage, "draft-test", 3000);
assert.equal(loaded.error, null);
assert.equal(loaded.drafts.length, 1);
assert.equal(loaded.drafts[0].lemma, "se lever");
assert.equal(loaded.drafts[0].sourceLexemeId, "lex-1");

const sourceMatch = findDraftForWordCard(loaded.drafts, { lemma: "lever", pos: "VER", sourceLexemeId: "lex-1" });
assert.equal(sourceMatch.id, loaded.drafts[0].id);

const lemmaPosMatch = findDraftForWordCard(loaded.drafts, { lemma: " SE LEVER ", pos: "ver" });
assert.equal(lemmaPosMatch.id, loaded.drafts[0].id);

const noMatch = findDraftForWordCard(loaded.drafts, { lemma: "aller", pos: "VER" });
assert.equal(noMatch, null);

const corrupt = loadDraftState(memoryStorage({ "draft-test": "{bad json" }), "draft-test");
assert.equal(corrupt.drafts.length, 0);
assert.match(corrupt.error, /无法解析/);

const wrongShape = loadDraftState(memoryStorage({ "draft-test": "{\"drafts\":{}}" }), "draft-test");
assert.equal(wrongShape.drafts.length, 0);
assert.match(wrongShape.error, /格式不正确/);

const partial = loadDraftState(memoryStorage({ "draft-test": "{\"drafts\":[{\"id\":\"a\",\"lemma\":\"aller\"},{\"id\":\"b\"}]}" }), "draft-test");
assert.equal(partial.drafts.length, 1);
assert.match(partial.error, /部分/);

const blockedLoad = loadDraftState(throwingStorage(), "draft-test");
assert.equal(blockedLoad.drafts.length, 0);
assert.match(blockedLoad.error, /无法读取/);

const blockedSave = saveDraftState(throwingStorage(), drafts, "draft-test");
assert.equal(blockedSave.ok, false);
assert.match(blockedSave.error, /无法保存/);
