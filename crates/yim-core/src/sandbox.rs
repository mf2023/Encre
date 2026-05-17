//! Copyright © 2025-2026 Wenze Wei. All Rights Reserved.
//!
//! This file is part of Yim.
//! The Yim project belongs to the Dunimd Team.
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

use serde::{Deserialize, Serialize};
use std::path::Path;
use std::process::Command;
use std::sync::mpsc;
use std::thread;
use std::time::Duration;

#[derive(Serialize, Deserialize, Debug)]
pub struct SandboxResult {
    pub stdout: String,
    pub stderr: String,
    pub exit_code: i32,
}

pub fn sandbox_execute(command: &str, timeout: u64) -> Result<SandboxResult, String> {
    let mut cmd = if cfg!(target_os = "windows") {
        let mut c = Command::new("cmd");
        c.args(["/C", command]);
        c
    } else {
        let mut c = Command::new("sh");
        c.args(["-c", command]);
        c
    };

    let (tx, rx) = mpsc::channel();
    let cmd_str = command.to_owned();

    thread::spawn(move || {
        let result = cmd.output().map_err(|e| format!("Sandbox error: {}", e));
        let _ = tx.send(result);
    });

    match rx.recv_timeout(Duration::from_secs(timeout)) {
        Ok(output_result) => {
            let output = output_result?;
            Ok(SandboxResult {
                stdout: String::from_utf8_lossy(&output.stdout).to_string(),
                stderr: String::from_utf8_lossy(&output.stderr).to_string(),
                exit_code: output.status.code().unwrap_or(-1),
            })
        }
        Err(_) => Err(format!("Command timed out after {} seconds: {}", timeout, cmd_str)),
    }
}

pub fn sandbox_read_file(path: &str) -> Result<String, String> {
    let p = Path::new(path);
    if !p.exists() {
        return Err(format!("File not found: {}", path));
    }
    std::fs::read_to_string(p).map_err(|e| format!("Sandbox read error: {}", e))
}

pub fn sandbox_write_file(path: &str, content: &str) -> Result<bool, String> {
    let p = Path::new(path);
    if let Some(parent) = p.parent() {
        std::fs::create_dir_all(parent).map_err(|e| format!("Sandbox mkdir error: {}", e))?;
    }
    std::fs::write(p, content).map_err(|e| format!("Sandbox write error: {}", e))?;
    Ok(true)
}