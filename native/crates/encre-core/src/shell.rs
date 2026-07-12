//! Shell execution — cross-platform with automatic encoding detection.
//!
//! On Windows, ``cmd /U /C`` produces UTF-16LE output which preserves
//! Chinese, Japanese, Korean, emoji, and all Unicode characters.
//!
//! On Unix, ``sh -c`` always produces UTF-8.

use serde::{Deserialize, Serialize};
use std::sync::mpsc;
use std::thread;
use std::time::Duration;

/// Result of running a shell command: captured streams and exit code.
#[derive(Serialize, Deserialize, Debug)]
    /// Captured standard output (decoded to UTF-8 / UTF-16 as needed).
pub struct ShellResult {
    /// Captured standard error.
    pub stdout: String,
    /// Process exit code (or -1 if the process could not be waited on).
    pub stderr: String,
    pub exit_code: i32,
}

/// Run `command` in a shell with an optional working directory and
/// timeout, returning captured output. Cross-platform with automatic
/// Unicode decoding.
pub fn execute_shell(
    command: &str,
    cwd: Option<&str>,
    timeout_secs: u64,
) -> Result<ShellResult, String> {
    #[cfg(target_os = "windows")]
    {
        let mut cmd = std::process::Command::new("cmd.exe");
        cmd.arg("/U");  // UTF-16LE output — preserves all Unicode
        cmd.arg("/C");
        cmd.arg(command);
        use std::os::windows::process::CommandExt as _;
        cmd.creation_flags(0x08000000);
        cmd.stdout(std::process::Stdio::piped());
        cmd.stderr(std::process::Stdio::piped());
        if let Some(dir) = cwd {
            cmd.current_dir(dir);
        }
        let (tx, rx) = mpsc::channel();
        thread::spawn(move || {
            let _ = tx.send(cmd.output());
        });
        let output = rx
            .recv_timeout(Duration::from_secs(timeout_secs))
            .map_err(|_| format!("Timed out after {timeout_secs}s"))?
            .map_err(|e| format!("{e}"))?;
        return Ok(ShellResult {
            stdout: decode_win(&output.stdout),
            stderr: decode_win(&output.stderr),
            exit_code: output.status.code().unwrap_or(-1),
        });
    }

    #[cfg(not(target_os = "windows"))]
    {
        let mut cmd = std::process::Command::new("sh");
        cmd.arg("-c");
        cmd.arg(command);
        cmd.stdout(std::process::Stdio::piped());
        cmd.stderr(std::process::Stdio::piped());
        if let Some(dir) = cwd {
            cmd.current_dir(dir);
        }
        let (tx, rx) = mpsc::channel();
        thread::spawn(move || {
            let _ = tx.send(cmd.output());
        });
        let output = rx
            .recv_timeout(Duration::from_secs(timeout_secs))
            .map_err(|_| format!("Timed out after {timeout_secs}s"))?
            .map_err(|e| format!("{e}"))?;
        Ok(ShellResult {
            stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
            stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
            exit_code: output.status.code().unwrap_or(-1),
        })
    }
}

/// Decode raw command output on Windows, detecting UTF-16LE produced
/// by `cmd /U` and falling back to UTF-8.
#[cfg(target_os = "windows")]
fn decode_win(raw: &[u8]) -> String {
    // ``cmd /U`` produces UTF-16LE for built-in commands (echo, dir, etc.)
    // but external programs (git, python, node) output their own encoding,
    // typically ASCII or UTF-8.  Detect UTF-16LE by checking whether every
    // other byte is zero — the hallmark of ASCII in UTF-16LE encoding.
    let looks_utf16 = raw.len() >= 2 && raw.len() % 2 == 0 && {
        // Check the first ~40 u16 values: if every high byte is zero,
        // this is ASCII output from cmd /U (which produces UTF-16LE).
        // External tools (git, python) ignore /U and produce UTF-8/ASCII,
        // where the first 40 bytes won't have this alternating-zero pattern.
        let min_len = raw.len().min(80);
        (0..min_len).step_by(2).all(|i| raw[i + 1] == 0)
    };

    if looks_utf16 {
        let u16: Vec<u16> = raw
            .windows(2)
            .step_by(2)
            .map(|c| u16::from_le_bytes([c[0], c[1]]))
            .collect();
        String::from_utf16_lossy(&u16)
    } else {
        String::from_utf8_lossy(raw).into_owned()
    }
}
