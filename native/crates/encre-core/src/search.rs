//! Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
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

//! Recursive codebase search: substring, regex, and glob utilities.
use serde::{Deserialize, Serialize};

/// Directories to skip entirely during codebase search.
const SKIP_DIRS: &[&str] = &[
    ".git", "node_modules", "target", "build", "dist", "venv",
    ".venv", "env", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".tox", ".eggs", ".svn", ".hg",
];

/// Skip a directory whose name is dotted or listed in `SKIP_DIRS`.
fn should_skip_dir(name: &str) -> bool {
    name.starts_with('.') || SKIP_DIRS.contains(&name)
}

/// Heuristic binary detection: any NUL byte in the first 8 KiB.
fn is_binary(content: &[u8]) -> bool {
    content[..content.len().min(8192)].contains(&0x00)
}

/// A single matching line returned by codebase search.
#[derive(Serialize, Deserialize, Debug)]
pub struct SearchResult {
    /// Path of the file containing the match.
    pub file_path: String,
    /// 1-based line number of the match (0 for multiline).
    pub line_number: usize,
    /// Full text of the matched line.
    pub line_content: String,
    /// Relevance score (number of query terms found).
    pub score: f64,
    /// Lines before the match (for context display), each is (line_number, content).
    pub context_before: Vec<(usize, String)>,
    /// Lines after the match (for context display), each is (line_number, content).
    pub context_after: Vec<(usize, String)>,
}

/// Walk the workspace and rank every line containing all query terms.
pub fn search_codebase(query: &str, path: &str) -> Vec<SearchResult> {
    let mut results = Vec::new();
    let walker = walkdir::WalkDir::new(path)
        .follow_links(true)
        .into_iter()
        .filter_entry(|e| {
            if e.file_type().is_dir() {
                return e
                    .file_name()
                    .to_str()
                    .map(|s| !should_skip_dir(s))
                    .unwrap_or(false);
            }
            if e.file_name().to_str().map_or(false, |s| s.starts_with('.')) {
                return false;
            }
            true
        });

    let query_lower = query.to_lowercase();
    let terms: Vec<&str> = query_lower.split_whitespace().collect();
    if terms.is_empty() {
        return results;
    }

    for entry in walker {
        let entry = match entry {
            Ok(e) => e,
            Err(err) => {
                eprintln!("[encre] search_codebase: walk error: {err}");
                continue;
            }
        };
        if !entry.file_type().is_file() {
            continue;
        }

        if let Ok(meta) = entry.metadata() {
            if meta.len() > 2 * 1024 * 1024 {
                continue;
            }
        }

        let content = match std::fs::read(entry.path()) {
            Ok(c) => c,
            Err(err) => {
                eprintln!("[encre] search_codebase: read error {}: {err}", entry.path().display());
                continue;
            }
        };

        if is_binary(&content) {
            continue;
        }

        let content_str = match String::from_utf8(content) {
            Ok(s) => s,
            Err(_) => continue,
        };

        let file_path = entry.path().to_string_lossy().to_string();
        for (i, line) in content_str.lines().enumerate() {
            let line_lower = line.to_lowercase();
            let mut score = 0.0_f64;
            for term in &terms {
                if line_lower.contains(term) {
                    score += 1.0;
                }
            }
            if score > 0.0 {
                results.push(SearchResult {
                    file_path: file_path.clone(),
                    line_number: i + 1,
                    line_content: line.to_string(),
                    score,
                    context_before: Vec::new(),
                    context_after: Vec::new(),
                });
            }
        }
    }

    results.sort_by(|a, b| {
        b.score
            .partial_cmp(&a.score)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    results.truncate(50);
    results
}

/// Regex search across a workspace with optional case-insensitivity,
/// glob filtering, context capture, multiline mode, and result cap.
pub fn grep(
    pattern: &str,
    path: &str,
    case_insensitive: bool,
    glob_filter: Option<&str>,
    multiline: bool,
    head_limit: Option<usize>,
    context_before: usize,
    context_after: usize,
) -> Vec<SearchResult> {
    let mut results = Vec::new();
    let mut re_builder = regex::RegexBuilder::new(pattern);
    re_builder.multi_line(true);
    if case_insensitive {
        re_builder.case_insensitive(true);
    }
    if multiline {
        re_builder.dot_matches_new_line(true);
    }
    let re = match re_builder.build() {
        Ok(r) => r,
        Err(err) => {
            eprintln!("[encre] grep: invalid regex: {err}");
            return results;
        }
    };

    let glob_matcher = glob_filter.and_then(|g| glob::Pattern::new(g).ok());

    let walker = walkdir::WalkDir::new(path)
        .follow_links(true)
        .into_iter()
        .filter_entry(|e| {
            if e.file_type().is_dir() {
                return e
                    .file_name()
                    .to_str()
                    .map(|s| !should_skip_dir(s))
                    .unwrap_or(false);
            }
            if e.file_name().to_str().map_or(false, |s| s.starts_with('.')) {
                return false;
            }
            true
        });

    for entry in walker {
        let entry = match entry {
            Ok(e) => e,
            Err(err) => {
                eprintln!("[encre] grep: walk error: {err}");
                continue;
            }
        };
        if !entry.file_type().is_file() {
            continue;
        }
        if let Some(ref matcher) = glob_matcher {
            let fname = entry.file_name().to_string_lossy();
            if !matcher.matches(&fname) {
                continue;
            }
        }

        if let Ok(meta) = entry.metadata() {
            if meta.len() > 2 * 1024 * 1024 {
                continue;
            }
        }

        let content = match std::fs::read(entry.path()) {
            Ok(c) => c,
            Err(err) => {
                eprintln!("[encre] grep: read error {}: {err}", entry.path().display());
                continue;
            }
        };
        if is_binary(&content) {
            continue;
        }
        let content_str = match String::from_utf8(content) {
            Ok(s) => s,
            Err(_) => continue,
        };
        let lines: Vec<&str> = content_str.lines().collect();
        let file_path = entry.path().to_string_lossy().to_string();

        if multiline {
            for m in re.find_iter(&content_str) {
                results.push(SearchResult {
                    file_path: file_path.clone(),
                    line_number: 0,
                    line_content: m.as_str().to_string(),
                    score: 1.0,
                    context_before: Vec::new(),
                    context_after: Vec::new(),
                });
                if let Some(limit) = head_limit {
                    if results.len() >= limit {
                        return results;
                    }
                }
            }
        } else {
            for (i, line) in lines.iter().enumerate() {
                if re.is_match(line) {
                    // Capture context before
                    let lo = i.saturating_sub(context_before);
                    let before: Vec<(usize, String)> = lines[lo..i]
                        .iter()
                        .enumerate()
                        .map(|(j, l)| (lo + j + 1, l.to_string()))
                        .collect();

                    // Capture context after
                    let hi = lines.len().min(i + 1 + context_after);
                    let after: Vec<(usize, String)> = lines[i + 1..hi]
                        .iter()
                        .enumerate()
                        .map(|(j, l)| (i + j + 2, l.to_string()))
                        .collect();

                    results.push(SearchResult {
                        file_path: file_path.clone(),
                        line_number: i + 1,
                        line_content: line.to_string(),
                        score: 1.0,
                        context_before: before,
                        context_after: after,
                    });
                    if let Some(limit) = head_limit {
                        if results.len() >= limit {
                            return results;
                        }
                    }
                }
            }
        }
    }

    results
}

/// Return all files under `path` matching a glob pattern.
pub fn glob(pattern: &str, path: &str) -> Vec<String> {
    let mut results = Vec::new();
    let glob_pattern = match glob::Pattern::new(pattern) {
        Ok(p) => p,
        Err(_) => return results,
    };

    let walker = walkdir::WalkDir::new(path)
        .follow_links(true)
        .into_iter()
        .filter_entry(|e| {
            if e.file_type().is_dir() {
                return e
                    .file_name()
                    .to_str()
                    .map(|s| !should_skip_dir(s))
                    .unwrap_or(false);
            }
            if e.file_name().to_str().map_or(false, |s| s.starts_with('.')) {
                return false;
            }
            true
        });

    for entry in walker {
        let entry = match entry {
            Ok(e) => e,
            Err(err) => {
                eprintln!("[encre] glob: walk error: {err}");
                continue;
            }
        };
        if !entry.file_type().is_file() {
            continue;
        }
        let p = entry.path().to_string_lossy().to_string();
        if glob_pattern.matches(&p) {
            results.push(p);
        }
    }

    results.sort();
    results

}
