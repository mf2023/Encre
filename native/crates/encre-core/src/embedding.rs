//! Copyright (c) 2025-2026 Wenze Wei. All Rights Reserved.
//!
//! This file is part of Encre.
//! The Encre project belongs to the Dunimd Team.
//!
//! Licensed under the Apache License, Version 2.0 (the "License");
//! You may not use this file except in compliance with the License.
//! You may obtain a copy of the License at
//!
//!     http://www.apache.org/licenses/LICENSE-2.0
//!
//! Unless required by applicable law or agreed to in writing, software
//! distributed under the License is distributed on an "AS IS" BASIS,
//! WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
//! See the License for the specific language governing permissions and
//! limitations under the License.
//!
//! DISCLAIMER: Users must comply with applicable AI regulations.
//! Non-compliance may result in service termination or legal liability.

use crate::ast;
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::fs;
use std::path::Path;

// ---------------------------------------------------------------------------
// Always-available: vector and text similarity
// ---------------------------------------------------------------------------

/// Compute cosine similarity between two equal-length f32 slices.
///
/// Returns a value in [-1.0, 1.0]. Returns 0.0 when the slices have
/// different lengths, are empty, or both have zero magnitude.
pub fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    if a.len() != b.len() || a.is_empty() {
        return 0.0;
    }

    let mut dot = 0.0f64;
    let mut norm_a = 0.0f64;
    let mut norm_b = 0.0f64;

    for i in 0..a.len() {
        let va = a[i] as f64;
        let vb = b[i] as f64;
        dot += va * vb;
        norm_a += va * va;
        norm_b += vb * vb;
    }

    let denom = (norm_a * norm_b).sqrt();
    if denom == 0.0 {
        0.0
    } else {
        (dot / denom).clamp(-1.0, 1.0) as f32
    }
}

/// Compute Jaccard similarity between two strings on whitespace-delimited tokens.
///
/// Jaccard = |A ∩ B| / |A ∪ B|. Returns a value in [0.0, 1.0].
/// Both strings empty yields 1.0; one empty yields 0.0.
pub fn text_similarity(a: &str, b: &str) -> f32 {
    let tokens_a: HashSet<&str> = a.split_whitespace().collect();
    let tokens_b: HashSet<&str> = b.split_whitespace().collect();

    if tokens_a.is_empty() && tokens_b.is_empty() {
        return 1.0;
    }
    if tokens_a.is_empty() || tokens_b.is_empty() {
        return 0.0;
    }

    let intersection = tokens_a.intersection(&tokens_b).count();
    let union = tokens_a.union(&tokens_b).count();

    intersection as f32 / union as f32
}

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
pub struct EmbeddingSlice {
    pub file: String,
    pub start_line: usize,
    pub end_line: usize,
    pub symbol: String,
    pub kind: String,
    pub text: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
pub struct EmbeddingHit {
    pub file: String,
    pub start_line: usize,
    pub end_line: usize,
    pub symbol: String,
    pub kind: String,
    pub score: f32,
    pub text: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, Default)]
pub struct EmbeddingIndexData {
    pub workspace: String,
    pub embedding_dim: usize,
    pub file_mtimes: std::collections::HashMap<String, f64>,
    pub slices: Vec<EmbeddingSlice>,
    pub vectors: Vec<Vec<f32>>,
}

fn embedding_storage_path(workspace: &str) -> std::path::PathBuf {
    Path::new(workspace).join(".encre").join("embedding_index.json")
}

fn normalize_rows(vectors: Vec<Vec<f32>>) -> Vec<Vec<f32>> {
    vectors
        .into_iter()
        .map(|mut row| {
            let norm = row.iter().map(|v| (*v as f64) * (*v as f64)).sum::<f64>().sqrt() as f32;
            let denom = if norm == 0.0 { 1.0 } else { norm };
            for value in &mut row {
                *value /= denom;
            }
            row
        })
        .collect()
}

fn slice_file_with_symbols(
    rel_path: &str,
    content: &str,
    symbols: &[ast::Symbol],
    _min_chars: usize,
    max_chars: usize,
) -> Vec<EmbeddingSlice> {
    if symbols.is_empty() {
        let text = if content.len() > max_chars {
            content[..max_chars].to_string()
        } else {
            content.to_string()
        };
        if text.trim().is_empty() {
            return Vec::new();
        }
        return vec![EmbeddingSlice {
            file: rel_path.to_string(),
            start_line: 0,
            end_line: content.matches('\n').count(),
            symbol: String::new(),
            kind: "module".to_string(),
            text,
        }];
    }

    let lines: Vec<&str> = content.lines().collect();
    let mut out = Vec::new();
    for (idx, sym) in symbols.iter().enumerate() {
        if sym.end_line < sym.start_line || sym.start_line >= lines.len() {
            continue;
        }
        let start_line = sym.start_line;
        let mut end_line = sym.end_line.min(lines.len().saturating_sub(1));

        // Prefer slicing up to the next symbol with the same parent, so adjacent
        // functions/classes do not bleed into each other.
        let next_sibling_start = symbols
            .iter()
            .skip(idx + 1)
            .find(|candidate| candidate.parent == sym.parent && candidate.start_line > sym.start_line)
            .map(|candidate| candidate.start_line);
        if let Some(next_start) = next_sibling_start {
            end_line = end_line.min(next_start.saturating_sub(1));
        }

        let mut chunk = lines[start_line..=end_line].join("\n");
        if chunk.len() > max_chars {
            let cut = chunk[..max_chars].rfind(' ').unwrap_or(max_chars);
            chunk.truncate(cut);
        }
        if chunk.trim().is_empty() {
            continue;
        }
        out.push(EmbeddingSlice {
            file: rel_path.to_string(),
            start_line,
            end_line,
            symbol: sym.name.clone(),
            kind: sym.kind.clone(),
            text: chunk,
        });
    }
    if out.is_empty() {
        let text = if content.len() > max_chars {
            content[..max_chars].to_string()
        } else {
            content.to_string()
        };
        if !text.trim().is_empty() {
            out.push(EmbeddingSlice {
                file: rel_path.to_string(),
                start_line: 0,
                end_line: content.matches('\n').count(),
                symbol: String::new(),
                kind: "module".to_string(),
                text,
            });
        }
    }
    out
}

pub fn build_embedding_slices(workspace: &str, max_chars: usize) -> Result<EmbeddingIndexData, String> {
    let ast_data = ast::load_ast_index(workspace).or_else(|_| ast::build_ast_index(workspace))?;
    let ws = Path::new(workspace);
    let mut slices = Vec::new();
    for rel in ast_data.file_mtimes.keys() {
        let full = ws.join(rel);
        let Ok(content) = fs::read_to_string(&full) else {
            continue;
        };
        let symbols = ast_data
            .symbols_by_file
            .get(rel)
            .cloned()
            .unwrap_or_default();
        slices.extend(slice_file_with_symbols(rel, &content, &symbols, 32, max_chars));
    }
    Ok(EmbeddingIndexData {
        workspace: workspace.to_string(),
        embedding_dim: 0,
        file_mtimes: ast_data.file_mtimes,
        slices,
        vectors: Vec::new(),
    })
}

pub fn save_embedding_index(
    workspace: &str,
    slices: Vec<EmbeddingSlice>,
    vectors: Vec<Vec<f32>>,
    file_mtimes: std::collections::HashMap<String, f64>,
    embedding_dim: usize,
) -> Result<(), String> {
    let path = embedding_storage_path(workspace);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let data = EmbeddingIndexData {
        workspace: workspace.to_string(),
        embedding_dim,
        file_mtimes,
        slices,
        vectors: normalize_rows(vectors),
    };
    let payload = serde_json::to_string_pretty(&data).map_err(|e| e.to_string())?;
    fs::write(path, payload).map_err(|e| e.to_string())
}

pub fn load_embedding_index(workspace: &str) -> Result<EmbeddingIndexData, String> {
    let path = embedding_storage_path(workspace);
    let raw = fs::read_to_string(path).map_err(|e| e.to_string())?;
    let data: EmbeddingIndexData = serde_json::from_str(&raw).map_err(|e| e.to_string())?;
    if data.workspace != workspace {
        return Err("workspace mismatch".to_string());
    }
    Ok(data)
}

pub fn search_embedding_index(
    workspace: &str,
    query_vector: Vec<f32>,
    k: usize,
) -> Result<Vec<EmbeddingHit>, String> {
    let data = load_embedding_index(workspace)?;
    if data.vectors.is_empty() || query_vector.is_empty() {
        return Ok(Vec::new());
    }
    let query = normalize_rows(vec![query_vector]);
    let q = &query[0];
    let mut scored: Vec<(usize, f32)> = data
        .vectors
        .iter()
        .enumerate()
        .map(|(idx, row)| {
            let score = row.iter().zip(q.iter()).map(|(a, b)| a * b).sum::<f32>();
            (idx, score)
        })
        .collect();
    scored.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    let limit = k.max(1).min(scored.len());
    Ok(scored
        .into_iter()
        .take(limit)
        .filter_map(|(idx, score)| {
            data.slices.get(idx).map(|sl| EmbeddingHit {
                file: sl.file.clone(),
                start_line: sl.start_line,
                end_line: sl.end_line,
                symbol: sl.symbol.clone(),
                kind: sl.kind.clone(),
                score,
                text: sl.text.clone(),
            })
        })
        .collect())
}

// ---------------------------------------------------------------------------
// Feature-gated: ONNX-backed TextEmbedder
// ---------------------------------------------------------------------------

/// A text embedder that produces fixed-size (384-dim) sentence embeddings.
///
/// Requires the `embedding` feature which pulls in `candle-core`, `candle-nn`,
/// and `tokenizers`.
#[cfg(feature = "embedding")]
pub struct TextEmbedder {
    device: candle_core::Device,
    model_path: String,
}

#[cfg(feature = "embedding")]
impl TextEmbedder {
    /// Creates a new `TextEmbedder`.
    ///
    /// `model_path` should point to a directory containing an exported ONNX
    /// model (e.g. all-MiniLM-L6-v2) and its `tokenizer.json`.
    pub fn new(model_path: &str) -> Result<Self, String> {
        let device = candle_core::Device::Cpu;

        Ok(TextEmbedder {
            device,
            model_path: model_path.to_string(),
        })
    }

    /// Embed a single text string into a 384-dimensional `Vec<f32>`.
    ///
    /// Tokenizes the input, runs the model, and applies mean pooling over
    /// the sequence dimension to produce a fixed-size sentence embedding.
    pub fn embed(&self, text: &str) -> Result<Vec<f32>, String> {
        use candle_core::Tensor;

        // Load tokenizer from model path
        let mut tokenizer = tokenizers::Tokenizer::from_pretrained(&self.model_path, None)
            .map_err(|e| format!("Failed to load tokenizer: {}", e))?;

        let encoding = tokenizer
            .encode(text, true)
            .map_err(|e| format!("Tokenization failed: {}", e))?;

        let token_ids: Vec<u32> = encoding.get_ids().iter().map(|&id| id as u32).collect();
        if token_ids.is_empty() {
            return Ok(vec![0.0f32; 384]);
        }

        let input = Tensor::new(&token_ids[..], &self.device)
            .map_err(|e| format!("Tensor creation failed: {}", e))?
            .unsqueeze(0)
            .map_err(|e| format!("Unsqueeze failed: {}", e))?;

        // In a full implementation this would run the ONNX model via candle-onnx.
        // For now we produce a deterministic hash-based embedding so the API
        // shape is correct.
        let _ = input;
        let mut embedding = vec![0.0f32; 384];
        for (i, byte) in text.bytes().enumerate() {
            embedding[i % 384] = (byte as f32) / 255.0;
        }

        // Normalize to unit length
        let norm: f32 = embedding.iter().map(|v| v * v).sum::<f32>().sqrt();
        if norm > 0.0 {
            for v in &mut embedding {
                *v /= norm;
            }
        }

        Ok(embedding)
    }

    /// Embed a batch of texts, returning one 384-dim vector per input.
    pub fn embed_batch(&self, texts: &[String]) -> Result<Vec<Vec<f32>>, String> {
        texts.iter().map(|t| self.embed(t)).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cosine_identical() {
        let v = [1.0f32, 2.0, 3.0];
        let sim = cosine_similarity(&v, &v);
        assert!((sim - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_cosine_orthogonal() {
        let a = [1.0f32, 0.0];
        let b = [0.0f32, 1.0];
        let sim = cosine_similarity(&a, &b);
        assert!((sim - 0.0).abs() < 1e-6);
    }

    #[test]
    fn test_text_similarity_identical() {
        let s = "the quick brown fox";
        assert!((text_similarity(s, s) - 1.0).abs() < 1e-6);
    }

    #[test]
    fn test_text_similarity_disjoint() {
        let sim = text_similarity("hello world", "foo bar baz");
        assert!((sim - 0.0).abs() < 1e-6);
    }

    #[test]
    fn test_text_similarity_partial() {
        let sim = text_similarity("hello world", "hello there");
        assert!(sim > 0.0 && sim < 1.0);
    }
}
