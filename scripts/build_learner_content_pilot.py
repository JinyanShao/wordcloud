#!/usr/bin/env python3
"""Create the bounded Phase 2 learner-content pilot; never modifies facts or runtime."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "processed" / "wordcloud.sqlite"
OUTPUT_PATH = ROOT / "data" / "learner-content-pilot.json"
MODEL = "gpt-5"
GENERATION_VERSION = "phase-2-pilot-1"

# These are the deterministic outcome of the documented stratified selection:
# six high-frequency multi-sense/no-family entries, four transparent pairs, and
# three opaque-family pairs.  Each draft is bound to one exact source sense.
SPECS = [
    (14232, "__ws_1_être__verb__1", "high_frequency_multisense_no_family", "是；处于", None, None, "Paris est en France.", "巴黎在法国。"),
    (1157, "__ws_1_avoir__verb__1", "high_frequency_multisense_no_family", "有；拥有", None, None, "J'ai un livre.", "我有一本书。"),
    (9976, "__ws_1_pouvoir__verb__1", "high_frequency_multisense_no_family", "能；可以", "常接不定式，表示能力或可能。", None, "Je peux venir demain.", "我明天可以来。"),
    (1034, "__ws_1_aujourd’hui__adv__1", "high_frequency_multisense_no_family", "今天", None, None, "Aujourd'hui, nous restons à la maison.", "今天我们待在家里。"),
    (2339, "__ws_1_chose__nom__1", "high_frequency_multisense_no_family", "东西；事情", "常用于不想或不能具体说明名称的事物。", None, "Cette chose est importante.", "这件事很重要。"),
    (406, "__ws_1_aller__verb__1", "high_frequency_multisense_with_nonfamily_relation", "去；前往", None, None, "Nous allons à l'école.", "我们去学校。"),
    (5859, "__ws_1_grand__adj__1", "transparent_sourced_suffix", "大的；尺寸大的", None, "现有来源把 grand 和 grandeur 记录为词族关系；这里关联的是“大的”与“大小、规模”的意思。它是已观察到的关系，不是可机械套用的规则。", "La maison est grande.", "这所房子很大。"),
    (5866, "__ws_1_grandeur__nom__1", "transparent_sourced_suffix", "大小；规模", None, "现有来源把 grandeur 和 grand 记录为词族关系；这里关联的是“大小、规模”与“大的”。它是已观察到的关系，不是可机械套用的规则。", "La grandeur de la salle est impressionnante.", "这个大厅的大小令人印象深刻。"),
    (9495, "__ws_1_petit__adj__1", "transparent_sourced_suffix", "小的；尺寸小的", None, "现有来源把 petit 和 petitesse 记录为词族关系；这里关联的是“小”与“小的程度或大小”。它是已观察到的关系，不是可机械套用的规则。", "Le sac est petit.", "这个包很小。"),
    (9504, "__ws_1_petitesse__nom__1", "transparent_sourced_suffix", "小；小的程度", None, "现有来源把 petitesse 和 petit 记录为词族关系；这里关联的是“小的程度”与“小”。它是已观察到的关系，不是可机械套用的规则。", "La petitesse de la pièce surprend les visiteurs.", "房间很小，这让来访者感到意外。"),
    (1515, "__ws_1_bon__adj__1", "transparent_sourced_suffix", "好的；符合期待的", None, "现有来源把 bon 和 bonté 记录为词族关系；这里关联的是“好的”与“善良、好品质”。它是已观察到的关系，不是可机械套用的规则。", "C'est un bon repas.", "这是一顿不错的饭。"),
    (1533, "__ws_1_bonté__nom__1", "transparent_sourced_suffix", "善良；好品质", None, "现有来源把 bonté 和 bon 记录为词族关系；这里关联的是“善良、好品质”与“好的”。它是已观察到的关系，不是可机械套用的规则。", "Sa bonté touche tout le monde.", "她的善良感动了所有人。"),
    (351, "__ws_1_aimer__verb__1", "transparent_sourced_suffix", "爱；喜欢", None, "现有来源把 aimer 和 aimable 记录为词族关系。aimable 在常用义中表示“讨人喜欢、友善”，但不要把它简单当成每个 aimer 都能按同一公式变化。", "J'aime cette chanson.", "我喜欢这首歌。"),
    (348, "__ws_3_aimable__adj__1", "transparent_sourced_suffix", "友善的；和蔼的", None, "现有来源把 aimable 和 aimer 记录为词族关系。这个常用义指待人友善；它不是让动词 aimer 机械变形的规则。", "Elle est très aimable avec les enfants.", "她对孩子们非常和蔼。"),
    (5081, "__ws_1_faire__verb__1", "opaque_sourced_family", "做；制作", None, "现有来源把 faire 和 façon 记录为词族关系，但这组的形式和意义不应当作可套用的构词规则。", "Je fais un gâteau.", "我在做一个蛋糕。"),
    (5163, "__ws_1_façon__nom__1", "opaque_sourced_family", "做法；方式", None, "现有来源把 façon 和 faire 记录为词族关系，但这组的形式和意义不应当作可套用的构词规则。", "C'est sa façon de parler.", "这是他说话的方式。"),
    (13641, "__ws_1_voir__verb__1", "opaque_sourced_family", "看见；看", None, "现有来源把 voir 和 vision 记录为词族关系；两者有关联，但词形变化不透明，不能当作机械规则。", "Je vois la mer.", "我看见大海。"),
    (13594, "__ws_1_vision__nom__1", "opaque_sourced_family", "视觉；看见的能力", None, "现有来源把 vision 和 voir 记录为词族关系；两者有关联，但词形变化不透明，不能当作机械规则。", "Sa vision est bonne.", "她的视力很好。"),
    (6194, "__ws_1_Homme__nom__1", "opaque_sourced_family", None, None, None, None, None),
    (6259, "__ws_1_humain__adj__1", "opaque_sourced_family", "人的；人类的", None, "现有来源把 humain 和 homme 记录为词族关系；这是不透明的词族联系，不应据此推导新的构词规则。", "Le cerveau humain est complexe.", "人类的大脑很复杂。"),
]

# One sourced edge per explanatory item.  The block entry deliberately has none.
EXPLANATION_EDGE = {5859: 1462, 5866: 1462, 9495: 2143, 9504: 2143, 1515: 443,
                    1533: 443, 351: 209, 348: 209, 5081: 1296, 5163: 1296,
                    13641: 3019, 13594: 3019, 6259: 1527}
ENTRY_IDS = {14232: "être__verb__1", 1157: "avoir__verb__1", 9976: "pouvoir__verb__1",
             1034: "aujourd’hui__adv__1", 2339: "chose__nom__1", 406: "aller__verb__1",
             5859: "grand__adj__1", 5866: "grandeur__nom__1", 9495: "petit__adj__1",
             9504: "petitesse__nom__1", 1515: "bon__adj__1", 1533: "bonté__nom__1",
             351: "aimer__verb__1", 348: "aimable__adj__1", 5081: "faire__verb__1",
             5163: "façon__nom__1", 13641: "voir__verb__1", 13594: "vision__nom__1",
             6194: "Homme__nom__1", 6259: "humain__adj__1"}


def fact_hash(conn: sqlite3.Connection, lexeme_id: int, entry_id: str, sense_id: str, edge_ids: list[int]) -> str:
    sense = conn.execute(
        "SELECT l.id,l.lemma,l.pos,s.id,s.sense_number,s.definition_fr FROM lexemes l JOIN lexeme_senses s ON s.lexeme_id=l.id WHERE l.id=? AND s.id=? AND s.entry_id=?",
        (lexeme_id, sense_id, entry_id),
    ).fetchone()
    edges = conn.execute(
        "SELECT id,a_id,b_id,relation,dimension,subtype,direction,review_status FROM official_edges WHERE id IN ({}) ORDER BY id".format(
            ",".join("?" * len(edge_ids)) or "NULL"
        ),
        edge_ids,
    ).fetchall()
    raw = json.dumps({"sense": sense, "edges": edges}, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def edge_ids_for(conn: sqlite3.Connection, lexeme_id: int) -> list[int]:
    return [row[0] for row in conn.execute("""
        SELECT e.id FROM official_edges e JOIN official_edge_sources x ON x.edge_id=e.id AND x.source_id='demonette_2'
        WHERE e.relation='fam' AND e.dimension='derivational_morphology' AND e.review_status='sourced'
          AND (e.a_id=? OR e.b_id=?) ORDER BY e.id
    """, (lexeme_id, lexeme_id))]


def build() -> dict:
    conn = sqlite3.connect(DB_PATH)
    try:
        items = []
        for lexeme_id, sense_id, sample_type, gloss, note, explanation, example_fr, example_zh in SPECS:
            edge_ids = [EXPLANATION_EDGE[lexeme_id]] if explanation else []
            entry_id = ENTRY_IDS[lexeme_id]
            items.append({
                "lexeme_id": lexeme_id, "entry_id": entry_id, "sense_id": sense_id, "sample_type": sample_type,
                "gloss_zh_short": gloss, "usage_note_zh": note, "relation_explanation_zh": explanation,
                "relation_edge_ids": edge_ids, "example_fr": example_fr, "example_zh": example_zh,
                "example_source_type": "ai_generated" if example_fr else None,
                "content_status": "blocked" if gloss is None else "ai_draft",
                "provenance": {"model": MODEL, "generation_version": GENERATION_VERSION,
                               "input_facts_sha256": fact_hash(conn, lexeme_id, entry_id, sense_id, edge_ids)},
            })
    finally:
        conn.close()
    return {"schema_version": 1, "scope": "Phase 2 pilot only; not runtime content or linguistic facts.",
            "selection_method": "deterministic stratification over current SQLite facts: frequency, POS, sense count, and sourced-family type.",
            "items": items}


if __name__ == "__main__":
    payload = build()
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"items": len(payload["items"]), "blocked": sum(x["content_status"] == "blocked" for x in payload["items"]) }))
