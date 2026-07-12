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

//! Heuristic tokenizer that estimates LLM token counts for mixed
//! natural-language, source-code, numeric, and CJK text.
use regex::Regex;
use std::sync::OnceLock;

/// Average characters per token assumed for natural-language English text.
const ENGLISH_CHARS_PER_TOKEN: f64 = 4.0;
/// Average characters per token assumed for source code and identifiers.
const CODE_CHARS_PER_TOKEN: f64 = 3.5;
/// Tokens charged per CJK (Chinese/Japanese/Korean) character.
const CJK_TOKENS_PER_CHAR: f64 = 2.0;
/// Digits consumed per token for numeric literals.
const DIGITS_PER_TOKEN: f64 = 2.0;
/// Token cost charged for a single punctuation-only word.
const PUNCTUATION_TOKEN_COST: usize = 1;

/// Lazily-compiled regex matching a maximal non-whitespace word.
fn word_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"[^\s]+").unwrap())
}

/// Lazily-compiled regex matching a standalone numeric literal.
fn number_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^\d[\d,.]*\d$|^\d$").unwrap())
}

/// Lazily-compiled regex matching a hexadecimal literal such as `0x1F`.
fn hex_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^0x[0-9a-fA-F]+$").unwrap())
}

/// Lazily-compiled regex matching a pure ASCII word (letters, `_`, `-`).
fn all_ascii_alpha_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^[A-Za-z_\-]+$").unwrap())
}

/// Lazily-compiled regex matching any ASCII word character.
fn mixed_ascii_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"[A-Za-z0-9_]").unwrap())
}

/// Lazily-compiled regex matching a single Han (CJK) character.
fn cjk_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"\p{Han}").unwrap())
}

/// Lazily-compiled regex matching a single punctuation character.
fn single_punctuation_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^[^\w\s]$").unwrap())
}

/// Estimate the number of tokens a string would consume in an LLM
/// context window, using per-category heuristics.
pub fn count_tokens(text: &str) -> usize {
    let text = text.trim();
    if text.is_empty() {
        return 0;
    }

    // Accumulate the estimated token count across every word.
    let mut tokens: f64 = 0.0;

    for m in word_re().find_iter(text) {
        let w = m.as_str();
        let char_count = w.chars().count();

        if number_re().is_match(w) || hex_re().is_match(w) {
            tokens += (char_count as f64 / DIGITS_PER_TOKEN).ceil();
        } else if all_ascii_alpha_re().is_match(w) {
            if char_count <= 4 {
                tokens += 1.0;
            } else if char_count <= 8 {
                tokens += 2.0;
            } else {
                tokens += (char_count as f64 / ENGLISH_CHARS_PER_TOKEN).ceil();
            }
        } else if mixed_ascii_re().is_match(w) {
            tokens += (char_count as f64 / CODE_CHARS_PER_TOKEN).ceil();
        } else if single_punctuation_re().is_match(w) {
            tokens += PUNCTUATION_TOKEN_COST as f64;
        } else {
            let cjk_chars: usize = cjk_re().find_iter(w).count();
            let non_cjk = char_count.saturating_sub(cjk_chars);
            tokens += cjk_chars as f64 * CJK_TOKENS_PER_CHAR;
            if non_cjk > 0 {
                tokens += (non_cjk as f64 / CODE_CHARS_PER_TOKEN).ceil();
            }
        }
    }

    // Add a small penalty for the whitespace between words.
    let whitespace_segments = text.split_whitespace().count();
    if whitespace_segments > 1 {
        tokens += (whitespace_segments as f64 * 0.25).ceil();
    }

    std::cmp::max(1, tokens as usize)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty() {
        assert_eq!(count_tokens(""), 0);
        assert_eq!(count_tokens("   "), 0);
    }

    #[test]
    fn test_single_word() {
        assert!(count_tokens("hello") >= 1);
    }

    #[test]
    fn test_short_phrase() {
        let count = count_tokens("hello world");
        assert!(count >= 2);
    }

    #[test]
    fn test_cjk() {
        let count = count_tokens("你好世界");
        assert!(count >= 4);
    }

    #[test]
    fn test_code_snippet() {
        let code = "def hello():\n    return 'world'";
        let count = count_tokens(code);
        assert!(count >= 5);
    }

    #[test]
    fn test_numbers() {
        let count = count_tokens("123456");
        assert!(count >= 1);
    }

    #[test]
    fn test_mixed_content() {
        let count = count_tokens("hello 你好 world 世界 123");
        assert!(count >= 5);
    }

    #[test]
    fn test_token_ratio() {
        let short = count_tokens("a");
        let long = count_tokens("Hello, this is a longer English sentence with many words");
        assert!(long > short);
    }
}