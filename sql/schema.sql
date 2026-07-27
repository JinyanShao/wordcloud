PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sources (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  version TEXT NOT NULL,
  homepage_url TEXT NOT NULL,
  download_url TEXT,
  license_id TEXT NOT NULL,
  license_url TEXT,
  attribution TEXT NOT NULL,
  commercial_use TEXT NOT NULL CHECK (commercial_use IN ('yes', 'no', 'unclear', 'local-only')),
  redistribution TEXT NOT NULL CHECK (redistribution IN ('yes', 'no', 'unclear', 'local-only')),
  local_path TEXT,
  sha256 TEXT,
  downloaded_at TEXT,
  notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS flelex_entries (
  word TEXT NOT NULL,
  normalized TEXT NOT NULL,
  tag TEXT NOT NULL,
  freq_a1 REAL NOT NULL,
  freq_a2 REAL NOT NULL,
  freq_b1 REAL NOT NULL,
  freq_b2 REAL NOT NULL,
  freq_c1 REAL NOT NULL,
  freq_c2 REAL NOT NULL,
  freq_total REAL NOT NULL,
  cefr_level TEXT NOT NULL,
  source_id TEXT NOT NULL REFERENCES sources(id),
  PRIMARY KEY (normalized, tag)
);

CREATE TABLE IF NOT EXISTS lexique_entries (
  form TEXT NOT NULL,
  normalized_form TEXT NOT NULL,
  lemma TEXT NOT NULL,
  normalized_lemma TEXT NOT NULL,
  pos TEXT NOT NULL,
  pos_ortho TEXT,
  gender TEXT,
  number TEXT,
  phonetic TEXT,
  phonetic_ipa TEXT,
  freq_form REAL NOT NULL,
  freq_ortho REAL NOT NULL,
  freq_lemma REAL NOT NULL,
  contextual_diversity REAL NOT NULL,
  is_lemma INTEGER NOT NULL CHECK (is_lemma IN (0, 1)),
  morph_base TEXT,
  morph_structure TEXT,
  morph_decomposition TEXT,
  prevalence REAL,
  source_id TEXT NOT NULL REFERENCES sources(id)
);

CREATE INDEX IF NOT EXISTS idx_lexique_lemma_pos
  ON lexique_entries(normalized_lemma, pos);
CREATE INDEX IF NOT EXISTS idx_lexique_form
  ON lexique_entries(normalized_form);

CREATE TABLE IF NOT EXISTS cfdict_entries (
  word TEXT PRIMARY KEY,
  normalized TEXT NOT NULL,
  glosses_json TEXT NOT NULL,
  source_id TEXT NOT NULL REFERENCES sources(id)
);

CREATE INDEX IF NOT EXISTS idx_cfdict_normalized
  ON cfdict_entries(normalized);

CREATE TABLE IF NOT EXISTS lexemes (
  id INTEGER PRIMARY KEY,
  lemma TEXT NOT NULL,
  normalized TEXT NOT NULL,
  pos TEXT NOT NULL,
  cefr_level TEXT,
  flelex_frequency REAL,
  lexique_frequency REAL,
  contextual_diversity REAL,
  phonetic_ipa TEXT,
  morph_base TEXT,
  morph_structure TEXT,
  morph_decomposition TEXT,
  gloss_zh TEXT,
  editorial_note TEXT,
  status TEXT NOT NULL CHECK (status IN ('eligible', 'auxiliary', 'excluded', 'needs_review')),
  decision_reason TEXT NOT NULL,
  eligibility_score REAL NOT NULL DEFAULT 0,
  has_flelex INTEGER NOT NULL DEFAULT 0 CHECK (has_flelex IN (0, 1)),
  has_lexique INTEGER NOT NULL DEFAULT 0 CHECK (has_lexique IN (0, 1)),
  has_cfdict INTEGER NOT NULL DEFAULT 0 CHECK (has_cfdict IN (0, 1)),
  created_at TEXT NOT NULL,
  UNIQUE (normalized, pos)
);

CREATE INDEX IF NOT EXISTS idx_lexemes_status
  ON lexemes(status);
CREATE INDEX IF NOT EXISTS idx_lexemes_level_pos
  ON lexemes(cefr_level, pos);

CREATE TABLE IF NOT EXISTS aliases (
  lexeme_id INTEGER NOT NULL REFERENCES lexemes(id) ON DELETE CASCADE,
  form TEXT NOT NULL,
  normalized TEXT NOT NULL,
  alias_type TEXT NOT NULL,
  source_id TEXT NOT NULL REFERENCES sources(id),
  PRIMARY KEY (lexeme_id, normalized, alias_type)
);

CREATE TABLE IF NOT EXISTS edge_candidates (
  id INTEGER PRIMARY KEY,
  a_id INTEGER NOT NULL REFERENCES lexemes(id),
  b_id INTEGER NOT NULL REFERENCES lexemes(id),
  relation TEXT NOT NULL,
  signal TEXT NOT NULL,
  weight REAL NOT NULL CHECK (weight >= 0 AND weight <= 1),
  source_id TEXT REFERENCES sources(id),
  details_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'candidate' CHECK (status IN ('candidate', 'sourced', 'reviewed', 'rejected')),
  created_at TEXT NOT NULL,
  CHECK (a_id < b_id),
  UNIQUE (a_id, b_id, signal)
);

CREATE INDEX IF NOT EXISTS idx_candidates_signal
  ON edge_candidates(signal, weight DESC);

CREATE TABLE IF NOT EXISTS official_edges (
  id INTEGER PRIMARY KEY,
  a_id INTEGER NOT NULL REFERENCES lexemes(id),
  b_id INTEGER NOT NULL REFERENCES lexemes(id),
  relation TEXT NOT NULL CHECK (relation IN ('syn', 'compare', 'fam', 'drift', 'trap', 'ant', 'cause')),
  dimension TEXT,
  subtype TEXT,
  direction TEXT,
  label TEXT NOT NULL,
  explanation TEXT,
  examples_json TEXT NOT NULL DEFAULT '[]',
  confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  review_status TEXT NOT NULL CHECK (review_status IN ('sourced', 'reviewed')),
  reviewed_at TEXT,
  created_at TEXT NOT NULL,
  CHECK (a_id < b_id),
  UNIQUE (a_id, b_id, relation, dimension, subtype)
);

CREATE TABLE IF NOT EXISTS official_edge_sources (
  edge_id INTEGER NOT NULL REFERENCES official_edges(id) ON DELETE CASCADE,
  source_id TEXT NOT NULL REFERENCES sources(id),
  source_record TEXT,
  PRIMARY KEY (edge_id, source_id)
);

CREATE TABLE IF NOT EXISTS layout_links (
  a_id INTEGER NOT NULL REFERENCES lexemes(id),
  b_id INTEGER NOT NULL REFERENCES lexemes(id),
  signal TEXT NOT NULL CHECK (signal IN ('semantic', 'derivation', 'spelling', 'phonetic', 'editorial_seed', 'skeleton')),
  weight REAL NOT NULL CHECK (weight >= 0 AND weight <= 1),
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  CHECK (a_id < b_id),
  PRIMARY KEY (a_id, b_id, signal)
);

CREATE TABLE IF NOT EXISTS positions (
  lexeme_id INTEGER PRIMARY KEY REFERENCES lexemes(id) ON DELETE CASCADE,
  x REAL NOT NULL,
  y REAL NOT NULL,
  degree INTEGER NOT NULL,
  weighted_degree REAL NOT NULL,
  community INTEGER,
  layout_version TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY,
  candidate_id INTEGER REFERENCES edge_candidates(id),
  reviewer TEXT NOT NULL,
  decision TEXT NOT NULL CHECK (decision IN ('accept', 'reject', 'edit', 'defer')),
  note TEXT NOT NULL DEFAULT '',
  reviewed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_samples (
  audit_id TEXT NOT NULL,
  sample_order INTEGER NOT NULL,
  lexeme_id INTEGER NOT NULL REFERENCES lexemes(id),
  stratum TEXT NOT NULL,
  automated_status TEXT NOT NULL,
  automated_reason TEXT NOT NULL,
  manual_decision TEXT CHECK (manual_decision IN ('agree', 'override_eligible', 'override_auxiliary', 'override_excluded', 'defer')),
  manual_note TEXT NOT NULL DEFAULT '',
  reviewer TEXT,
  reviewed_at TEXT,
  PRIMARY KEY (audit_id, sample_order)
);

CREATE TABLE IF NOT EXISTS build_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
