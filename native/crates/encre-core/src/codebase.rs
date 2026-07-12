//! Rust-backed workspace code index.

use crate::indexer::Bm25Index;
use ignore::WalkBuilder;
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::{Path, PathBuf};

const MAX_FILE_SIZE: u64 = 2 * 1024 * 1024;
const SKIP_DIRS: &[&str] = &[
    "node_modules", "__pycache__", "target", "build", "dist", ".git", "venv", ".venv", "env",
    ".tox", ".eggs", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".svn", ".hg", ".encre", "release",
    "win-unpacked", "resources",
];

/// Per-module index entry: imports, exports, and metadata.
#[derive(Clone, Serialize, Deserialize, Debug, Default)]
    /// Relative path of the module within the workspace.
pub struct ModuleInfo {
    /// Module name (defaults to its relative path).
    pub path: String,
    /// Modules/packages this module imports.
    pub name: String,
    /// Modules that import this module (reverse edges).
    pub imports: Vec<String>,
    /// Public symbols this module exports.
    pub imported_by: Vec<String>,
    /// Detected language of the module.
    pub exports: Vec<String>,
    /// Line count of the module.
    pub language: String,
    pub loc: usize,
}

/// Serialised workspace code index.
#[derive(Clone, Serialize, Deserialize, Debug, Default)]
    /// Workspace root path.
pub struct CodeIndexData {
    /// Indexed modules keyed by relative path.
    pub workspace: String,
    /// Per-file modification times for incremental updates.
    pub modules: HashMap<String, ModuleInfo>,
    /// Whether the workspace is a git repository.
    pub file_mtimes: HashMap<String, f64>,
    /// Whether a `.gitignore` exists in the workspace.
    pub has_git: bool,
    /// Count of git-ignored files encountered during scan.
    pub has_gitignore: bool,
    pub gitignored_count: usize,
}

fn should_skip_dir(name: &str) -> bool {
    SKIP_DIRS.contains(&name)
}

fn is_binary(content: &[u8]) -> bool {
    content[..content.len().min(8192)].contains(&0x00)
}

fn storage_path(workspace: &str) -> PathBuf {
    Path::new(workspace).join(".encre").join("code_index.json")
}

fn rel_path(path: &Path, workspace: &Path) -> Option<String> {
    path.strip_prefix(workspace)
        .ok()
        .map(|p| p.to_string_lossy().replace('\\', "/"))
}

fn language_for_ext(ext: &str) -> String {
    match ext {
        ".py" | ".pyi" | ".pyx" => "python",
        ".js" | ".jsx" | ".mjs" | ".cjs" => "javascript",
        ".ts" | ".tsx" => "typescript",
        ".rs" => "rust",
        ".go" => "go",
        other => other.trim_start_matches('.'),
    }
    .to_string()
}

fn parse_generic_imports(content: &str) -> Vec<String> {
    let import_re = Regex::new(
        r#"(?:import\s+[\w.]+)|(?:from\s+\S+\s+import\s+\S+)|(?:#include\s+[<"][^>"]+[>"])|(?:require\s*\(\s*['"][^'"]+['"]\s*\))"#,
    )
    .expect("valid import regex");
    import_re
        .find_iter(content)
        .map(|m| m.as_str().trim().to_string())
        .collect()
}

fn parse_python(rel: &str, content: &str) -> ModuleInfo {
    let mut info = ModuleInfo {
        path: rel.to_string(),
        name: rel.to_string(),
        imports: Vec::new(),
        imported_by: Vec::new(),
        exports: Vec::new(),
        language: "python".to_string(),
        loc: content.lines().count(),
    };
    let import_re = Regex::new(r#"(?m)^\s*import\s+([A-Za-z0-9_.,\s]+)"#).expect("valid regex");
    for caps in import_re.captures_iter(content) {
        if let Some(m) = caps.get(1) {
            for part in m.as_str().split(',') {
                let name = part.trim().split_whitespace().next().unwrap_or("").trim();
                if !name.is_empty() {
                    info.imports.push(name.to_string());
                }
            }
        }
    }
    let from_re = Regex::new(r#"(?m)^\s*from\s+([A-Za-z0-9_\.]+)\s+import\s+"#).expect("valid regex");
    for caps in from_re.captures_iter(content) {
        if let Some(m) = caps.get(1) {
            info.imports.push(m.as_str().to_string());
        }
    }
    let export_re = Regex::new(r#"(?m)^\s*(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)"#)
        .expect("valid regex");
    for caps in export_re.captures_iter(content) {
        if let Some(m) = caps.get(1) {
            let name = m.as_str();
            if !name.starts_with('_') {
                info.exports.push(name.to_string());
            }
        }
    }
    let const_re = Regex::new(r#"(?m)^([A-Z][A-Z0-9_]*)\s*="#).expect("valid regex");
    for caps in const_re.captures_iter(content) {
        if let Some(m) = caps.get(1) {
            info.exports.push(m.as_str().to_string());
        }
    }
    info
}

fn parse_javascript(rel: &str, content: &str, ext: &str) -> ModuleInfo {
    let mut info = ModuleInfo {
        path: rel.to_string(),
        name: rel.to_string(),
        imports: Vec::new(),
        imported_by: Vec::new(),
        exports: Vec::new(),
        language: language_for_ext(ext),
        loc: content.lines().count(),
    };
    let import_re = Regex::new(
        r#"(?:import\s+(?:(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)\s*,?\s*)*from\s+['"]([^'"]+)['"])|(?:import\s+['"]([^'"]+)['"])|(?:require\s*\(\s*['"]([^'"]+)['"]\s*\))"#,
    )
    .expect("valid regex");
    for caps in import_re.captures_iter(content) {
        let mod_name = caps
            .get(1)
            .or_else(|| caps.get(2))
            .or_else(|| caps.get(3))
            .map(|m| m.as_str())
            .unwrap_or("");
        if !mod_name.is_empty() && !mod_name.starts_with('.') {
            info.imports.push(mod_name.to_string());
        }
    }
    let export_re = Regex::new(
        r#"(?:export\s+(?:default\s+)?(?:function|class|const|let|var|interface|type|enum)\s+(\w+))|(?:export\s*\{\s*([^}]*)\s*\})"#,
    )
    .expect("valid regex");
    for caps in export_re.captures_iter(content) {
        if let Some(name) = caps.get(1) {
            info.exports.push(name.as_str().to_string());
        } else if let Some(items) = caps.get(2) {
            for part in items.as_str().split(',') {
                let trimmed = part.trim();
                if !trimmed.is_empty() {
                    info.exports.push(
                        trimmed
                            .split(" as ")
                            .last()
                            .unwrap_or(trimmed)
                            .trim()
                            .to_string(),
                    );
                }
            }
        }
    }
    info
}

fn parse_rust(rel: &str, content: &str) -> ModuleInfo {
    let mut info = ModuleInfo {
        path: rel.to_string(),
        name: rel.to_string(),
        imports: Vec::new(),
        imported_by: Vec::new(),
        exports: Vec::new(),
        language: "rust".to_string(),
        loc: content.lines().count(),
    };
    let use_re = Regex::new(r#"use\s+((?:\w+::)*\w+)\s*;"#).expect("valid regex");
    for caps in use_re.captures_iter(content) {
        if let Some(m) = caps.get(1) {
            info.imports.push(m.as_str().to_string());
        }
    }
    for pattern in [
        r#"pub\s+(?:async\s+)?fn\s+(\w+)"#,
        r#"pub\s+struct\s+(\w+)"#,
        r#"pub\s+enum\s+(\w+)"#,
        r#"pub\s+trait\s+(\w+)"#,
    ] {
        let re = Regex::new(pattern).expect("valid regex");
        for caps in re.captures_iter(content) {
            if let Some(m) = caps.get(1) {
                info.exports.push(m.as_str().to_string());
            }
        }
    }
    info
}

fn parse_go(rel: &str, content: &str) -> ModuleInfo {
    let mut info = ModuleInfo {
        path: rel.to_string(),
        name: rel.to_string(),
        imports: Vec::new(),
        imported_by: Vec::new(),
        exports: Vec::new(),
        language: "go".to_string(),
        loc: content.lines().count(),
    };
    let import_block_re =
        Regex::new(r#"import\s*\(\s*((?:[^)]*?"[^"]+"[^)]*?)*)\s*\)"#).expect("valid regex");
    let single_import_re = Regex::new(r#"import\s+"([^"]+)""#).expect("valid regex");
    let quoted_re = Regex::new(r#""([^"]+)""#).expect("valid regex");
    for caps in import_block_re.captures_iter(content) {
        if let Some(block) = caps.get(1) {
            for q in quoted_re.captures_iter(block.as_str()) {
                if let Some(m) = q.get(1) {
                    info.imports.push(m.as_str().to_string());
                }
            }
        }
    }
    for caps in single_import_re.captures_iter(content) {
        if let Some(m) = caps.get(1) {
            info.imports.push(m.as_str().to_string());
        }
    }
    let func_re = Regex::new(r#"func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)"#).expect("valid regex");
    for caps in func_re.captures_iter(content) {
        if let Some(m) = caps.get(1) {
            let name = m.as_str();
            if name.chars().next().map(|c| c.is_uppercase()).unwrap_or(false) {
                info.exports.push(name.to_string());
            }
        }
    }
    let type_re = Regex::new(r#"type\s+(\w+)\s+struct"#).expect("valid regex");
    for caps in type_re.captures_iter(content) {
        if let Some(m) = caps.get(1) {
            info.exports.push(m.as_str().to_string());
        }
    }
    info
}

fn parse_module(rel: &str, content: &str, ext: &str) -> ModuleInfo {
    match ext {
        ".py" | ".pyi" | ".pyx" => parse_python(rel, content),
        ".js" | ".jsx" | ".ts" | ".tsx" | ".mjs" | ".cjs" => parse_javascript(rel, content, ext),
        ".rs" => parse_rust(rel, content),
        ".go" => parse_go(rel, content),
        _ => ModuleInfo {
            path: rel.to_string(),
            name: rel.to_string(),
            imports: parse_generic_imports(content),
            imported_by: Vec::new(),
            exports: Vec::new(),
            language: language_for_ext(ext),
            loc: content.lines().count(),
        },
    }
}

// Recompute reverse dependency edges between modules.
fn build_dependencies(modules: &mut HashMap<String, ModuleInfo>) {
    let mut modules_by_name: HashMap<String, String> = HashMap::new();
    for mod_info in modules.values() {
        if let Some(stem) = Path::new(&mod_info.path).file_stem().and_then(|s| s.to_str()) {
            modules_by_name.insert(stem.to_string(), mod_info.path.clone());
        }
    }
    for mod_info in modules.values_mut() {
        mod_info.imported_by.clear();
    }
    let keys: Vec<String> = modules.keys().cloned().collect();
    let mut reverse_edges: Vec<(String, String)> = Vec::new();
    for path in &keys {
        if let Some(mod_info) = modules.get(path) {
            for imp in &mod_info.imports {
                let candidate = imp.split('.').next().unwrap_or("");
                if let Some(dep_path) = modules_by_name.get(candidate) {
                    reverse_edges.push((dep_path.clone(), path.clone()));
                }
            }
        }
    }
    let mut seen: HashSet<(String, String)> = HashSet::new();
    for (dep, importer) in reverse_edges {
        if seen.insert((dep.clone(), importer.clone())) {
            if let Some(dep_mod) = modules.get_mut(&dep) {
                dep_mod.imported_by.push(importer);
            }
        }
    }
}

// Walk the workspace honouring .gitignore, skipping ignored directories.
fn scan_workspace_files(workspace_path: &Path) -> Vec<(String, PathBuf, fs::Metadata)> {
    let walker = WalkBuilder::new(workspace_path)
        .hidden(false)
        .git_ignore(true)
        .git_global(true)
        .git_exclude(true)
        .parents(true)
        .follow_links(true)
        .filter_entry(|entry| {
            if let Some(name) = entry.path().file_name().and_then(|s| s.to_str()) {
                if entry
                    .file_type()
                    .map(|ft| ft.is_dir() && should_skip_dir(name))
                    .unwrap_or(false)
                {
                    return false;
                }
            }
            true
        })
        .build();

    let mut out = Vec::new();
    for entry in walker.filter_map(|e| e.ok()) {
        if !entry.file_type().map(|ft| ft.is_file()).unwrap_or(false) {
            continue;
        }
        let name = entry.path().file_name().and_then(|s| s.to_str()).unwrap_or("");
        if name.starts_with('.') || name == ".gitignore" {
            continue;
        }
        let metadata = match entry.metadata() {
            Ok(m) => m,
            Err(_) => continue,
        };
        if metadata.len() > MAX_FILE_SIZE {
            continue;
        }
        let path = entry.path().to_path_buf();
        let rel = match rel_path(&path, workspace_path) {
            Some(v) => v,
            None => continue,
        };
        if rel == ".encre/code_index.json" || rel.starts_with(".encre/") {
            continue;
        }
        out.push((rel, path, metadata));
    }
    out
}

fn parse_file_to_module(rel: &str, path: &Path, metadata: &fs::Metadata) -> Option<(ModuleInfo, f64)> {
    let raw = fs::read(path).ok()?;
    if is_binary(&raw) {
        return None;
    }
    let content = String::from_utf8_lossy(&raw).to_string();
    let ext = path.extension().and_then(|s| s.to_str()).unwrap_or("");
    let ext = if ext.is_empty() {
        String::new()
    } else {
        format!(".{}", ext.to_lowercase())
    };
    let mtime = metadata
        .modified()
        .ok()
        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0);
    Some((parse_module(rel, &content, &ext), mtime))
}

/// Build (or rebuild) the full code index for a workspace from scratch.
pub fn build_code_index(workspace: &str) -> Result<CodeIndexData, String> {
    let workspace_path = Path::new(workspace)
        .canonicalize()
        .map_err(|e| e.to_string())?;
    let mut data = CodeIndexData {
        workspace: workspace.to_string(),
        modules: HashMap::new(),
        file_mtimes: HashMap::new(),
        has_git: workspace_path.join(".git").is_dir(),
        has_gitignore: workspace_path.join(".gitignore").is_file(),
        gitignored_count: 0,
    };

    for (rel, path, metadata) in scan_workspace_files(&workspace_path) {
        if let Some((module, mtime)) = parse_file_to_module(&rel, &path, &metadata) {
            data.file_mtimes.insert(rel.clone(), mtime);
            data.modules.insert(rel.clone(), module);
        }
    }

    build_dependencies(&mut data.modules);
    save_code_index(workspace, &data)?;
    Ok(data)
}

/// Count the number of files that would be indexed in a workspace.
pub fn count_code_index_candidates(workspace: &str) -> Result<usize, String> {
    let workspace_path = Path::new(workspace)
        .canonicalize()
        .map_err(|e| e.to_string())?;
    Ok(scan_workspace_files(&workspace_path).len())
}

/// Incrementally update the code index, re-parsing only changed files.
pub fn update_code_index(workspace: &str) -> Result<CodeIndexData, String> {
    let workspace_path = Path::new(workspace)
        .canonicalize()
        .map_err(|e| e.to_string())?;
    let mut data = load_code_index(workspace).unwrap_or_else(|_| CodeIndexData {
        workspace: workspace.to_string(),
        modules: HashMap::new(),
        file_mtimes: HashMap::new(),
        has_git: workspace_path.join(".git").is_dir(),
        has_gitignore: workspace_path.join(".gitignore").is_file(),
        gitignored_count: 0,
    });

    data.workspace = workspace.to_string();
    data.has_git = workspace_path.join(".git").is_dir();
    data.has_gitignore = workspace_path.join(".gitignore").is_file();

    let mut current_files: HashSet<String> = HashSet::new();
    for (rel, path, metadata) in scan_workspace_files(&workspace_path) {
        current_files.insert(rel.clone());
        let mtime = metadata
            .modified()
            .ok()
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_secs_f64())
            .unwrap_or(0.0);
        let needs_update = data
            .file_mtimes
            .get(&rel)
            .map(|old| *old < mtime)
            .unwrap_or(true);
        if needs_update {
            if let Some((module, actual_mtime)) = parse_file_to_module(&rel, &path, &metadata) {
                data.modules.insert(rel.clone(), module);
                data.file_mtimes.insert(rel.clone(), actual_mtime);
            } else {
                data.modules.remove(&rel);
                data.file_mtimes.remove(&rel);
            }
        }
    }

    let stale: Vec<String> = data
        .modules
        .keys()
        .filter(|path| !current_files.contains(*path))
        .cloned()
        .collect();
    for path in stale {
        data.modules.remove(&path);
        data.file_mtimes.remove(&path);
    }

    build_dependencies(&mut data.modules);
    save_code_index(workspace, &data)?;
    Ok(data)
}

/// Persist the code index to `.encre/code_index.json`.
pub fn save_code_index(workspace: &str, data: &CodeIndexData) -> Result<(), String> {
    let path = storage_path(workspace);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let json = serde_json::to_string_pretty(data).map_err(|e| e.to_string())?;
    fs::write(path, json).map_err(|e| e.to_string())
}

/// Load a previously built code index from disk.
pub fn load_code_index(workspace: &str) -> Result<CodeIndexData, String> {
    let path = storage_path(workspace);
    let raw = fs::read_to_string(path).map_err(|e| e.to_string())?;
    serde_json::from_str::<CodeIndexData>(&raw).map_err(|e| e.to_string())
}

/// BM25-rank files in the index for a free-text query.
pub fn search_code_index(workspace: &str, query: &str, limit: usize) -> Result<Vec<(String, f64)>, String> {
    let data = load_code_index(workspace)?;
    let workspace_path = Path::new(workspace);
    let mut files: Vec<(String, String)> = Vec::new();
    for mod_info in data.modules.values() {
        let full = workspace_path.join(&mod_info.path);
        let raw = match fs::read(&full) {
            Ok(v) => v,
            Err(_) => continue,
        };
        if is_binary(&raw) {
            continue;
        }
        let content = String::from_utf8_lossy(&raw).to_lowercase();
        files.push((mod_info.path.clone(), content));
    }
    let mut idx = Bm25Index::new();
    idx.build(files);
    Ok(idx.search(query, limit, 1.5, 0.75, 2.0))
}

/// Build a textual context block (source + imports/exports) for a file.
pub fn build_code_context(workspace: &str, file_path: &str) -> Result<String, String> {
    let mut data = load_code_index(workspace)?;
    build_dependencies(&mut data.modules);
    let rel = if Path::new(file_path).is_absolute() {
        let workspace_path = Path::new(workspace)
            .canonicalize()
            .map_err(|e| e.to_string())?;
        let full = Path::new(file_path).canonicalize().map_err(|e| e.to_string())?;
        rel_path(&full, &workspace_path).unwrap_or_else(|| file_path.replace('\\', "/"))
    } else {
        file_path.replace('\\', "/")
    };
    let mod_info = data
        .modules
        .get(&rel)
        .ok_or_else(|| "file not found in code index".to_string())?;
    let full_path = Path::new(workspace).join(&mod_info.path);
    let source = fs::read_to_string(full_path).unwrap_or_default();
    let mut parts = vec![format!("[{}] ({}, {} loc)", mod_info.path, mod_info.language, mod_info.loc)];
    if !source.is_empty() {
        parts.push(source);
    }
    if !mod_info.imports.is_empty() {
        parts.push(format!(
            "Imports: {}",
            mod_info.imports.iter().take(30).cloned().collect::<Vec<_>>().join(", ")
        ));
    }
    if !mod_info.imported_by.is_empty() {
        parts.push(format!(
            "Imported by: {}",
            mod_info
                .imported_by
                .iter()
                .take(30)
                .cloned()
                .collect::<Vec<_>>()
                .join(", ")
        ));
    }
    if !mod_info.exports.is_empty() {
        parts.push(format!(
            "Exports: {}",
            mod_info.exports.iter().take(30).cloned().collect::<Vec<_>>().join(", ")
        ));
    }
    Ok(parts.join("\n\n"))
}
