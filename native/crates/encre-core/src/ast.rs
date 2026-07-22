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

//! Rust-backed AST workspace index.

use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};
use tree_sitter::{Language, Node, Parser};
use walkdir::WalkDir;

/// Maximum file size (2 MiB) that is indexed or parsed for symbols.
const MAX_FILE_SIZE: u64 = 2 * 1024 * 1024;
/// Directories excluded from AST walking.
const SKIP_DIRS: &[&str] = &[
    "node_modules",
    "__pycache__",
    "target",
    "build",
    "dist",
    ".git",
    "venv",
    ".venv",
    "env",
    ".tox",
    ".eggs",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".hg",
    ".encre",
];

/// A symbol (function, class, variable, …) extracted from source.
#[derive(Clone, Serialize, Deserialize, Debug, Default)]
    /// Symbol name as written in source.
pub struct Symbol {
    /// Kind of symbol (e.g. "function", "class", "struct").
    pub name: String,
    /// Relative path of the file containing the symbol.
    pub kind: String,
    /// 0-based start line of the symbol.
    pub file: String,
    /// 0-based start column of the symbol.
    pub start_line: usize,
    /// 0-based end line of the symbol.
    pub start_col: usize,
    /// 0-based end column of the symbol.
    pub end_line: usize,
    /// Name of the enclosing symbol, if any.
    pub end_col: usize,
    /// Optional source signature (first non-empty line).
    pub parent: Option<String>,
    /// Optional docstring (Python only).
    pub signature: Option<String>,
    pub docstring: Option<String>,
}

/// A textual reference / usage occurrence of an identifier.
#[derive(Clone, Serialize, Deserialize, Debug, Default)]
    /// File containing the reference.
pub struct Reference {
    /// 0-based line of the reference.
    pub file: String,
    /// 0-based column of the reference.
    pub line: usize,
    /// Referenced identifier name.
    pub col: usize,
    /// Always "reference".
    pub name: String,
    pub kind: String,
}

/// Serialised AST index for a workspace.
#[derive(Clone, Serialize, Deserialize, Debug, Default)]
    /// Workspace root path.
pub struct AstIndexData {
    /// Per-file modification times, used for incremental updates.
    pub workspace: String,
    /// Symbols grouped by relative file path.
    pub file_mtimes: HashMap<String, f64>,
    pub symbols_by_file: HashMap<String, Vec<Symbol>>,
}

// Path to the persisted JSON index inside `.encre/`.
fn storage_path(workspace: &str) -> PathBuf {
    Path::new(workspace).join(".encre").join("ast_index.json")
}

// Detect binary content by scanning for NUL bytes in the first 8 KiB.
fn is_binary(content: &[u8]) -> bool {
    content[..content.len().min(8192)].contains(&0x00)
}

// Skip a path whose any component is a dotfile or a skipped directory.
fn should_skip_path(path: &Path) -> bool {
    path.components().any(|component| match component {
        std::path::Component::Normal(part) => {
            let name = part.to_string_lossy();
            name.starts_with('.') || SKIP_DIRS.contains(&name.as_ref())
        }
        _ => false,
    })
}

// Convert an absolute path to a repo-relative, forward-slash path.
fn rel_path(path: &Path, workspace: &Path) -> Option<String> {
    path.strip_prefix(workspace)
        .ok()
        .map(|p| p.to_string_lossy().replace('\\', "/"))
}

// Map a file extension to its tree-sitter language name.
fn lang_by_ext(ext: &str) -> Option<&'static str> {
    match ext {
        ".py" | ".pyi" | ".pyx" => Some("python"),
        ".js" | ".jsx" | ".mjs" | ".cjs" => Some("javascript"),
        ".ts" => Some("typescript"),
        ".tsx" => Some("tsx"),
        ".rs" => Some("rust"),
        ".go" => Some("go"),
        ".java" => Some("java"),
        ".c" | ".h" => Some("c"),
        ".cpp" | ".cc" | ".cxx" | ".hpp" | ".hh" | ".hxx" => Some("cpp"),
        ".cs" => Some("csharp"),
        ".rb" => Some("ruby"),
        ".php" => Some("php"),
        ".swift" => Some("swift"),
        ".kt" | ".kts" => Some("kotlin"),
        ".scala" | ".sc" => Some("scala"),
        _ => None,
    }
}

// Resolve a tree-sitter `Language` for a given language name.
fn language_for_name(name: &str) -> Option<Language> {
    match name {
        "python" => Some(tree_sitter_python::LANGUAGE.into()),
        "javascript" => Some(tree_sitter_javascript::LANGUAGE.into()),
        "typescript" => Some(tree_sitter_typescript::LANGUAGE_TYPESCRIPT.into()),
        "tsx" => Some(tree_sitter_typescript::LANGUAGE_TSX.into()),
        "rust" => Some(tree_sitter_rust::LANGUAGE.into()),
        "go" => Some(tree_sitter_go::LANGUAGE.into()),
        "java" => Some(tree_sitter_java::LANGUAGE.into()),
        "c" => Some(tree_sitter_c::LANGUAGE.into()),
        "cpp" => Some(tree_sitter_cpp::LANGUAGE.into()),
        "csharp" => Some(tree_sitter_c_sharp::LANGUAGE.into()),
        "php" => Some(tree_sitter_php::LANGUAGE_PHP.into()),
        "ruby" => Some(tree_sitter_ruby::LANGUAGE.into()),
        "swift" => Some(tree_sitter_swift::LANGUAGE.into()),
        "kotlin" => Some(tree_sitter_kotlin_ng::LANGUAGE.into()),
        "scala" => Some(tree_sitter_scala::LANGUAGE.into()),
        _ => None,
    }
}

// Map a tree-sitter node type to a normalized symbol-kind string.
fn definition_kind(lang: &str, node_type: &str) -> Option<&'static str> {
    match lang {
        "python" => match node_type {
            "function_definition" => Some("function"),
            "class_definition" => Some("class"),
            _ => None,
        },
        "javascript" => match node_type {
            "function_declaration" | "generator_function_declaration" => Some("function"),
            "class_declaration" => Some("class"),
            "method_definition" => Some("method"),
            "variable_declarator" => Some("variable"),
            _ => None,
        },
        "typescript" | "tsx" => match node_type {
            "function_declaration" | "generator_function_declaration" => Some("function"),
            "class_declaration" => Some("class"),
            "method_definition" => Some("method"),
            "interface_declaration" => Some("interface"),
            "type_alias_declaration" => Some("type_alias"),
            "enum_declaration" => Some("enum"),
            "variable_declarator" | "lexical_declaration" => Some("variable"),
            _ => None,
        },
        "rust" => match node_type {
            "function_item" => Some("function"),
            "struct_item" => Some("struct"),
            "enum_item" => Some("enum"),
            "trait_item" => Some("trait"),
            "impl_item" => Some("impl"),
            "type_item" => Some("type_alias"),
            "const_item" | "static_item" => Some("constant"),
            _ => None,
        },
        "go" => match node_type {
            "function_declaration" => Some("function"),
            "method_declaration" => Some("method"),
            "type_declaration" => Some("type"),
            "const_declaration" => Some("constant"),
            "var_declaration" => Some("variable"),
            _ => None,
        },
        "java" => match node_type {
            "method_declaration" | "constructor_declaration" => Some("method"),
            "class_declaration" => Some("class"),
            "interface_declaration" => Some("interface"),
            "enum_declaration" => Some("enum"),
            "annotation_type_declaration" => Some("interface"),
            _ => None,
        },
        "c" => match node_type {
            "function_definition" => Some("function"),
            "struct_specifier" | "union_specifier" => Some("struct"),
            "enum_specifier" => Some("enum"),
            "type_definition" => Some("type_alias"),
            _ => None,
        },
        "cpp" => match node_type {
            "function_definition" | "function_decl" => Some("function"),
            "class_specifier" => Some("class"),
            "struct_specifier" | "union_specifier" => Some("struct"),
            "enum_specifier" => Some("enum"),
            "namespace_definition" => Some("namespace"),
            _ => None,
        },
        "csharp" => match node_type {
            "method_declaration" => Some("method"),
            "class_declaration" => Some("class"),
            "interface_declaration" => Some("interface"),
            "struct_declaration" => Some("struct"),
            "enum_declaration" => Some("enum"),
            "record_declaration" => Some("class"),
            "delegate_declaration" => Some("type_alias"),
            _ => None,
        },
        "ruby" => match node_type {
            "method" => Some("method"),
            "class" => Some("class"),
            "module" => Some("module"),
            _ => None,
        },
        "php" => match node_type {
            "function_definition" => Some("function"),
            "class_declaration" => Some("class"),
            "method_declaration" => Some("method"),
            "interface_declaration" => Some("interface"),
            "trait_declaration" => Some("trait"),
            _ => None,
        },
        "swift" => match node_type {
            "function_declaration" => Some("function"),
            "class_declaration" => Some("class"),
            "protocol_declaration" => Some("interface"),
            "enum_declaration" => Some("enum"),
            "struct_declaration" => Some("struct"),
            "extension_declaration" => Some("extension"),
            _ => None,
        },
        "kotlin" => match node_type {
            "function_declaration" => Some("function"),
            "class_declaration" | "object_declaration" => Some("class"),
            "interface_declaration" => Some("interface"),
            "property_declaration" => Some("property"),
            _ => None,
        },
        "scala" => match node_type {
            "function_definition" => Some("function"),
            "class_definition" | "object_definition" => Some("class"),
            "trait_definition" => Some("trait"),
            _ => None,
        },
        _ => None,
    }
}

// Read a source file, rejecting oversized or binary content.
fn read_source_file(path: &Path) -> Result<String, String> {
    let raw = fs::read(path).map_err(|e| e.to_string())?;
    if raw.len() as u64 > MAX_FILE_SIZE {
        return Err("file too large".to_string());
    }
    if is_binary(&raw) {
        return Err("binary file".to_string());
    }
    Ok(String::from_utf8_lossy(&raw).into_owned())
}

// Slice `content` by byte offsets into an owned `String`.
fn slice_bytes(content: &str, start: usize, end: usize) -> Option<String> {
    content.get(start..end).map(|s| s.to_string())
}

// Extract the identifier name from a definition node.
fn extract_name(node: &Node<'_>, content: &str) -> Option<String> {
    if let Some(name_node) = node.child_by_field_name("name") {
        return slice_bytes(content, name_node.start_byte(), name_node.end_byte());
    }
    let node_type = node.kind();
    if node_type == "variable_declarator" {
        let child_count = node.child_count();
        for idx in 0..child_count {
            if let Some(child) = node.child(idx) {
                let kind = child.kind();
                if kind == "identifier" || kind == "property_identifier" {
                    return slice_bytes(content, child.start_byte(), child.end_byte());
                }
            }
        }
    }
    if node_type == "const_item" || node_type == "static_item" {
        let child_count = node.child_count();
        for idx in 0..child_count {
            if let Some(child) = node.child(idx) {
                if child.kind() == "identifier" {
                    return slice_bytes(content, child.start_byte(), child.end_byte());
                }
            }
        }
    }
    if node_type == "type_definition" {
        let child_count = node.child_count();
        for idx in (0..child_count).rev() {
            if let Some(child) = node.child(idx) {
                if child.kind() == "type_identifier" {
                    return slice_bytes(content, child.start_byte(), child.end_byte());
                }
            }
        }
    }
    if node_type == "const_declaration" || node_type == "var_declaration" {
        let child_count = node.child_count();
        for idx in 0..child_count {
            if let Some(child) = node.child(idx) {
                let child_kind = child.kind();
                if child_kind == "const_spec" || child_kind == "var_spec" {
                    let cc = child.child_count();
                    for cidx in 0..cc {
                        if let Some(grandchild) = child.child(cidx) {
                            if grandchild.kind() == "identifier" {
                                return slice_bytes(content, grandchild.start_byte(), grandchild.end_byte());
                            }
                        }
                    }
                }
            }
        }
    }
    None
}

// Extract the first non-empty source line as a signature.
fn extract_signature(node: &Node<'_>, content: &str) -> Option<String> {
    let start = node.start_position().row;
    let lines: Vec<&str> = content.split('\n').collect();
    let first = lines.get(start)?;
    if !first.trim().is_empty() {
        return Some(first.trim().chars().take(200).collect());
    }
    let second = lines.get(start + 1)?;
    if !second.trim().is_empty() {
        return Some(second.trim().chars().take(200).collect());
    }
    None
}

// Extract a Python docstring from the first body statement.
fn extract_docstring(node: &Node<'_>, content: &str, lang: &str) -> Option<String> {
    if lang != "python" {
        return None;
    }
    let body = node.child_by_field_name("body")?;
    if body.child_count() == 0 {
        return None;
    }
    let first = body.child(0)?;
    if first.kind() != "string" {
        return None;
    }
    let raw = slice_bytes(content, first.start_byte(), first.end_byte())?;
    for triple in ["\"\"\"", "'''"] {
        if raw.starts_with(triple) && raw.ends_with(triple) && raw.len() >= 6 {
            return Some(raw[3..raw.len() - 3].trim().chars().take(500).collect());
        }
    }
    let bytes = raw.as_bytes();
    if bytes.len() >= 2 && bytes[0] == bytes[bytes.len() - 1] && (bytes[0] == b'"' || bytes[0] == b'\'') {
        return Some(raw[1..raw.len() - 1].trim().chars().take(500).collect());
    }
    None
}

// Recursively walk a tree-sitter node, collecting symbols.
fn walk_symbols(
    node: Node<'_>,
    rel_path: &str,
    content: &str,
    lang: &str,
    parent: Option<String>,
    out: &mut Vec<Symbol>,
) {
    let child_count = node.child_count();
    for idx in 0..child_count {
        let Some(child) = node.child(idx) else {
            continue;
        };
        let child_type = child.kind();
        if let Some(kind) = definition_kind(lang, &child_type) {
            if let Some(name) = extract_name(&child, content) {
                let start = child.start_position();
                let end = child.end_position();
                let sym = Symbol {
                    name: name.clone(),
                    kind: kind.to_string(),
                    file: rel_path.to_string(),
                    start_line: start.row,
                    start_col: start.column,
                    end_line: end.row,
                    end_col: end.column,
                    parent: parent.clone(),
                    signature: extract_signature(&child, content),
                    docstring: extract_docstring(&child, content, lang),
                };
                out.push(sym);
                walk_symbols(child, rel_path, content, lang, Some(name), out);
                continue;
            }
        }
        walk_symbols(child, rel_path, content, lang, parent.clone(), out);
    }
}

// Parse a single source file into a list of symbols.
fn parse_symbols(rel_path: &str, content: &str, lang: &str) -> Vec<Symbol> {
    let Some(language) = language_for_name(lang) else {
        return Vec::new();
    };
    let mut parser = Parser::new();
    if parser.set_language(&language).is_err() {
        return Vec::new();
    }
    let Some(tree) = parser.parse(content, None) else {
        return Vec::new();
    };
    let root = tree.root_node();
    let mut out = Vec::new();
    walk_symbols(root, rel_path, content, lang, None, &mut out);
    out
}

// Walk the workspace and gather (path, rel, lang, mtime) tuples.
fn collect_source_files(workspace: &Path) -> Vec<(PathBuf, String, String, f64)> {
    let mut out = Vec::new();
    for entry in WalkDir::new(workspace).into_iter().filter_map(|e| {
        if let Err(ref err) = e {
            eprintln!("[ast] walk error: {err}");
        }
        e.ok()
    }) {
        let path = entry.path();
        if path == workspace || !entry.file_type().is_file() {
            continue;
        }
        if should_skip_path(path) {
            continue;
        }
        let Some(ext) = path.extension().and_then(|e| e.to_str()) else {
            continue;
        };
        let ext = format!(".{}", ext).to_lowercase();
        let Some(lang) = lang_by_ext(&ext) else {
            continue;
        };
        let Ok(meta) = entry.metadata() else {
            continue;
        };
        if meta.len() > MAX_FILE_SIZE {
            continue;
        }
        let Ok(_content) = read_source_file(path) else {
            continue;
        };
        let Some(rel) = rel_path(path, workspace) else {
            continue;
        };
        let mtime = meta
            .modified()
            .ok()
            .and_then(|mtime| mtime.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_secs_f64())
            .unwrap_or_default();
        out.push((path.to_path_buf(), rel, lang.to_string(), mtime));
    }
    out
}

// Persist the AST index to `.encre/ast_index.json`.
fn save_index(data: &AstIndexData) -> Result<(), String> {
    let path = storage_path(&data.workspace);
    let parent = path.parent().ok_or_else(|| "invalid storage path".to_string())?;
    fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    let payload = serde_json::to_string_pretty(data).map_err(|e| e.to_string())?;
    fs::write(path, payload).map_err(|e| e.to_string())
}

/// Always returns `true`: the tree-sitter backend is statically linked.
pub fn ast_available() -> bool {
    true
}

/// Return the human-readable name of the AST backend.
pub fn ast_backend_name() -> &'static str {
    "tree-sitter-static"
}

/// Load a previously built AST index from disk.
pub fn load_ast_index(workspace: &str) -> Result<AstIndexData, String> {
    let path = storage_path(workspace);
    let raw = fs::read_to_string(path).map_err(|e| e.to_string())?;
    let data: AstIndexData = serde_json::from_str(&raw).map_err(|e| e.to_string())?;
    if data.workspace != workspace {
        return Err("workspace mismatch".to_string());
    }
    Ok(data)
}

/// Build (or rebuild) the AST index for a workspace from scratch.
pub fn build_ast_index(workspace: &str) -> Result<AstIndexData, String> {
    let ws = Path::new(workspace);
    if !ws.exists() {
        return Ok(AstIndexData {
            workspace: workspace.to_string(),
            ..Default::default()
        });
    }
    let mut data = AstIndexData {
        workspace: workspace.to_string(),
        ..Default::default()
    };
    for (_path, rel, lang, mtime) in collect_source_files(ws) {
        let full = ws.join(&rel);
        let Ok(content) = read_source_file(&full) else {
            continue;
        };
        data.file_mtimes.insert(rel.clone(), mtime);
        data.symbols_by_file
            .insert(rel.clone(), parse_symbols(&rel, &content, &lang));
    }
    save_index(&data)?;
    Ok(data)
}

/// Incrementally update the AST index, re-parsing only changed files.
pub fn update_ast_index(workspace: &str) -> Result<AstIndexData, String> {
    let ws = Path::new(workspace);
    if !ws.exists() {
        return Ok(AstIndexData {
            workspace: workspace.to_string(),
            ..Default::default()
        });
    }
    let mut data = load_ast_index(workspace).unwrap_or(AstIndexData {
        workspace: workspace.to_string(),
        ..Default::default()
    });
    let current = collect_source_files(ws);
    let mut current_files = HashSet::new();
    for (_path, rel, lang, mtime) in current {
        current_files.insert(rel.clone());
        let changed = match data.file_mtimes.get(&rel) {
            Some(old) => *old < mtime,
            None => true,
        };
        if changed {
            let full = ws.join(&rel);
            let Ok(content) = read_source_file(&full) else {
                continue;
            };
            data.file_mtimes.insert(rel.clone(), mtime);
            data.symbols_by_file
                .insert(rel.clone(), parse_symbols(&rel, &content, &lang));
        }
    }
    let stale: Vec<String> = data
        .file_mtimes
        .keys()
        .filter(|rel| !current_files.contains(*rel))
        .cloned()
        .collect();
    for rel in stale {
        data.file_mtimes.remove(&rel);
        data.symbols_by_file.remove(&rel);
    }
    save_index(&data)?;
    Ok(data)
}

// Build a name -> symbols map across the whole workspace.
fn global_index(data: &AstIndexData) -> HashMap<String, Vec<Symbol>> {
    let mut out: HashMap<String, Vec<Symbol>> = HashMap::new();
    for symbols in data.symbols_by_file.values() {
        for sym in symbols {
            out.entry(sym.name.clone()).or_default().push(sym.clone());
        }
    }
    out
}

/// Look up all symbols matching a given name across the workspace.
pub fn ast_get_symbol(workspace: &str, name: &str) -> Result<Vec<Symbol>, String> {
    let data = load_ast_index(workspace)?;
    Ok(global_index(&data).remove(name).unwrap_or_default())
}

/// Return all symbols defined in a single file.
pub fn ast_get_outline(workspace: &str, file: &str) -> Result<Vec<Symbol>, String> {
    let data = load_ast_index(workspace)?;
    Ok(data.symbols_by_file.get(file).cloned().unwrap_or_default())
}

/// Return a sorted list of indexed file paths.
pub fn ast_list_files(workspace: &str) -> Result<Vec<String>, String> {
    let data = load_ast_index(workspace)?;
    let mut files: Vec<String> = data.file_mtimes.keys().cloned().collect();
    files.sort();
    Ok(files)
}

/// Find symbols whose name contains `name`, up to `limit` results.
pub fn ast_find_relevant(workspace: &str, name: &str, limit: usize) -> Result<Vec<Symbol>, String> {
    if name.is_empty() {
        return Ok(Vec::new());
    }
    let data = load_ast_index(workspace)?;
    let mut out = Vec::new();
    for symbols in data.symbols_by_file.values() {
        for sym in symbols {
            if sym.name.contains(name) {
                out.push(sym.clone());
                if out.len() >= limit {
                    return Ok(out);
                }
            }
        }
    }
    Ok(out)
}

/// Find every textual occurrence of `name` across indexed files.
pub fn ast_find_references(workspace: &str, name: &str) -> Result<Vec<Reference>, String> {
    let ident = Regex::new(r"^[A-Za-z_][A-Za-z0-9_]*$").expect("valid identifier regex");
    if name.is_empty() || !ident.is_match(name) {
        return Ok(Vec::new());
    }
    let pattern = Regex::new(&format!(r"\b{}\b", regex::escape(name))).map_err(|e| e.to_string())?;
    let data = load_ast_index(workspace)?;
    let ws = Path::new(workspace);
    let mut refs = Vec::new();
    for rel in data.file_mtimes.keys() {
        let full = ws.join(rel);
        let Ok(content) = fs::read_to_string(full) else {
            continue;
        };
        for mat in pattern.find_iter(&content) {
            let abs = mat.start();
            let prefix = &content[..abs];
            let line = prefix.bytes().filter(|b| *b == b'\n').count();
            let col = prefix.rsplit('\n').next().map(|s| s.chars().count()).unwrap_or(0);
            refs.push(Reference {
                file: rel.clone(),
                line,
                col,
                name: name.to_string(),
                kind: "reference".to_string(),
            });
        }
    }
    Ok(refs)
}

// Extract the identifier surrounding a (line, column) position.
fn extract_identifier_at(line_text: &str, col: usize) -> Option<String> {
    if col >= line_text.chars().count() {
        return None;
    }
    let chars: Vec<char> = line_text.chars().collect();
    let mut start = col;
    while start > 0 && (chars[start - 1].is_alphanumeric() || chars[start - 1] == '_') {
        start -= 1;
    }
    let mut end = col;
    while end < chars.len() && (chars[end].is_alphanumeric() || chars[end] == '_') {
        end += 1;
    }
    if start >= end {
        return None;
    }
    Some(chars[start..end].iter().collect())
}

/// Resolve the definition of the symbol at a position in a file.
pub fn ast_goto_definition(workspace: &str, file: &str, line: usize, col: usize) -> Result<Option<Symbol>, String> {
    let full = Path::new(workspace).join(file);
    let content = fs::read_to_string(full).map_err(|e| e.to_string())?;
    let lines: Vec<&str> = content.split('\n').collect();
    let Some(line_text) = lines.get(line) else {
        return Ok(None);
    };
    let Some(name) = extract_identifier_at(line_text, col) else {
        return Ok(None);
    };
    let data = load_ast_index(workspace)?;
    let mut candidates = global_index(&data).remove(&name).unwrap_or_default();
    if candidates.is_empty() {
        return Ok(None);
    }
    let mut same_file: Vec<Symbol> = candidates
        .iter()
        .filter(|sym| sym.file == file)
        .cloned()
        .collect();
    if !same_file.is_empty() {
        same_file.sort_by_key(|sym| sym.start_line);
        let mut best = same_file[0].clone();
        for sym in same_file {
            if sym.start_line <= line {
                best = sym;
            } else {
                break;
            }
        }
        return Ok(Some(best));
    }
    candidates.sort_by_key(|sym| (sym.file.clone(), sym.start_line));
    Ok(candidates.into_iter().next())
}
